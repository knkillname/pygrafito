# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Tests for the public graph facade."""

import threading
import typing
from pathlib import Path
from sqlite3 import ProgrammingError

import pytest

from pygrafito import Graph, Transaction
from pygrafito.model import (
    ConnectedNodeError,
    Node,
    NotFoundError,
    ValidationError,
    Value,
)


class _CrossThreadReader:
    """Attempt a read from another thread and record the failure."""

    def __init__(self, graph: Graph, node_id: int) -> None:
        self._graph = graph
        self._node_id = node_id
        self.error: Exception | None = None

    def __call__(self) -> None:
        """Read the node, recording any error."""
        try:
            self._graph.node(self._node_id)
        except Exception as error:
            self.error = error


class TestOpenAndClose:
    """Verify file persistence and handle lifecycle."""

    def test_reopen_file_database(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.db"
        graph = Graph.open(path)
        node = graph.add_node("Person", name="Ada", age=36)
        graph.close()
        reopened = Graph.open(path)
        try:
            loaded = reopened.node(node.id)
            assert loaded == node
            assert loaded["name"] == "Ada"
            assert loaded.labels == frozenset({"Person"})
        finally:
            reopened.close()

    def test_second_graph_handle_sees_committed_data(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.db"
        with Graph.open(path) as first:
            node = first.add_node(name="Ada")
        with Graph.open(path) as second:
            assert second.node(node.id)["name"] == "Ada"

    def test_in_memory_graph(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node("Person")
            assert graph.node(node.id) == node

    def test_context_manager_closes(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node()
        with pytest.raises(ProgrammingError):
            graph.node(node.id)

    def test_close_is_idempotent(self) -> None:
        graph = Graph.open(":memory:")
        graph.close()
        graph.close()

    def test_open_without_create_rejects_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(NotFoundError):
            Graph.open(tmp_path / "absent.db", create=False)

    def test_cross_thread_use_rejected(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node()
            reader = _CrossThreadReader(graph, node.id)
            thread = threading.Thread(target=reader)
            thread.start()
            thread.join()
            assert isinstance(reader.error, ProgrammingError)


class TestConvenienceWrites:
    """Verify one-shot atomic writes and reads."""

    def test_node_and_relationship_round_trip(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node("Person", name="Ada")
            second = graph.add_node("Person", name="Grace")
            relationship = graph.add_relationship(first, "KNOWS", second, since=2020)
            assert graph.relationship(relationship.id)["since"] == 2020
            assert dict(graph.node(first.id)) == {"name": "Ada"}

    def test_invalid_node_write_is_atomic(self) -> None:
        with Graph.open(":memory:") as graph:
            with pytest.raises(ValidationError):
                graph.add_node(bad=typing.cast(Value, {"mapping": 1}))
            assert list(graph.find_nodes()) == []

    def test_invalid_relationship_write_is_atomic(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node()
            with pytest.raises(NotFoundError):
                graph.add_relationship(node, "KNOWS", node.id + 1)
            assert list(graph.find_relationships()) == []

    def test_label_and_property_updates(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node("Person", name="Ada")
            node = graph.add_labels(node, "Employee")
            node = graph.remove_labels(node, "Person")
            updated = graph.set_properties(node, age=36)
            assert isinstance(updated, Node)
            assert updated.labels == frozenset({"Employee"})
            assert dict(updated) == {"name": "Ada", "age": 36}
            stripped = graph.remove_properties(updated, "age")
            assert isinstance(stripped, Node)
            assert dict(stripped) == {"name": "Ada"}

    def test_arbitrary_property_keys(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node(**{"a.b": 1, "a b": 2})
            found = list(graph.find_nodes(**{"a.b": 1}))
            assert [item.id for item in found] == [node.id]

    def test_find_relationships(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            knows = graph.add_relationship(first, "KNOWS", second, since=2020)
            graph.add_relationship(first, "LIKES", second, since=2020)
            found = list(graph.find_relationships("KNOWS", since=2020))
            assert [item.id for item in found] == [knows.id]

    def test_delete_relationship(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            relationship = graph.add_relationship(first, "KNOWS", second)
            graph.delete(relationship)
            with pytest.raises(NotFoundError):
                graph.relationship(relationship.id)

    def test_connected_node_requires_detach(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            relationship = graph.add_relationship(first, "KNOWS", second)
            with pytest.raises(ConnectedNodeError):
                graph.delete(first)
            graph.delete(first, detach=True)
            with pytest.raises(NotFoundError):
                graph.relationship(relationship.id)
            with pytest.raises(NotFoundError):
                graph.node(first.id)

    def test_transaction_rolls_back(self) -> None:
        with Graph.open(":memory:") as graph:
            active = graph.transaction()
            with pytest.raises(RuntimeError):
                self._write_and_fail(active)
            assert list(graph.find_nodes()) == []

    @staticmethod
    def _write_and_fail(active: Transaction) -> None:
        """Write a node inside a transaction, then fail.

        Parameters
        ----------
        active : Transaction
            Transaction that should roll back.

        Raises
        ------
        RuntimeError
            Always, to trigger rollback.
        """
        with active:
            active.add_node(name="Ada")
            message = "boom"
            raise RuntimeError(message)

    def test_transaction_commits(self) -> None:
        with Graph.open(":memory:") as graph:
            with graph.transaction() as active:
                first = active.add_node("Person")
                second = active.add_node("Person")
                relationship = active.add_relationship(first, "KNOWS", second)
            assert graph.node(first.id) == first
            assert graph.relationship(relationship.id) == relationship
