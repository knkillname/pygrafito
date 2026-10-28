# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the public graph facade."""

import threading
import typing
from pathlib import Path

import pytest

from pygrafito import (
    Graph,
    GraphClosedError,
    HandleAffinityError,
    Relationship,
    Transaction,
)
from pygrafito.model import (
    ConnectedNodeError,
    Node,
    NotFoundError,
    TransactionError,
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


class _CrossThreadTransaction:
    """Begin a transaction from another thread and record the failure."""

    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        self.error: Exception | None = None

    def __call__(self) -> None:
        """Begin the transaction, recording any error."""
        try:
            self._transaction.begin()
        except Exception as error:
            self.error = error


class TestOpenAndClose:
    """Verify file persistence and handle lifecycle."""

    def test_reopen_file_database(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.db"
        graph = Graph.open(path)
        node = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        graph.close()
        reopened = Graph.open(path)
        try:
            loaded = reopened.node(node.id)
            assert loaded == node
            assert loaded["designation"] == "Kevin Flynn"
            assert loaded.labels == frozenset({"Program"})
        finally:
            reopened.close()

    def test_second_graph_handle_sees_committed_data(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.db"
        with Graph.open(path) as first:
            node = first.add_node(designation="Kevin Flynn")
        with Graph.open(path) as second:
            assert second.node(node.id)["designation"] == "Kevin Flynn"

    def test_in_memory_graph(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node("Program")
            assert graph.node(node.id) == node

    def test_context_manager_closes(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node()
        with pytest.raises(GraphClosedError):
            graph.node(node.id)

    def test_close_is_idempotent(self) -> None:
        graph = Graph.open(":memory:")
        graph.close()
        graph.close()

    def test_read_after_close_rejected(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node("Program", designation="Tron")
            second = graph.add_node("Program", designation="Clu")
            relationship = graph.add_relationship(first, "ALLIES_WITH", second)
        with pytest.raises(GraphClosedError):
            graph.node(first.id)
        with pytest.raises(GraphClosedError):
            graph.relationship(relationship.id)
        with pytest.raises(GraphClosedError):
            graph.find_nodes()
        with pytest.raises(GraphClosedError):
            graph.find_relationships()

    def test_write_after_close_rejected(self) -> None:
        graph = Graph.open(":memory:")
        node = graph.add_node("Program", designation="Tron")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.add_node("Program", designation="Clu")
        with pytest.raises(GraphClosedError):
            graph.delete(node)
        with pytest.raises(GraphClosedError):
            graph.transaction()

    def test_traversal_after_close_rejected(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node("Program", designation="Tron")
        with pytest.raises(GraphClosedError):
            graph.traverse(node, max_depth=1)
        with pytest.raises(GraphClosedError):
            graph.shortest_path(node, node)
        with pytest.raises(GraphClosedError):
            graph.paths(node, node, max_depth=1)

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
            assert isinstance(reader.error, HandleAffinityError)

    def test_cross_thread_transaction_rejected(self) -> None:
        with Graph.open(":memory:") as graph:
            transaction = graph.transaction()
            reader = _CrossThreadTransaction(transaction)
            thread = threading.Thread(target=reader)
            thread.start()
            thread.join()
            assert isinstance(reader.error, HandleAffinityError)
            assert not graph._database.connection.in_transaction


class TestConvenienceWrites:
    """Verify one-shot atomic writes and reads."""

    def test_node_and_relationship_round_trip(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node("Program", designation="Kevin Flynn")
            second = graph.add_node("Program", designation="Quorra")
            relationship = graph.add_relationship(first, "ALLIES_WITH", second, since_cycle=2020)
            assert graph.relationship(relationship.id)["since_cycle"] == 2020
            assert dict(graph.node(first.id)) == {"designation": "Kevin Flynn"}

    def test_invalid_node_write_is_atomic(self) -> None:
        with Graph.open(":memory:") as graph:
            with pytest.raises(ValidationError):
                graph.add_node(bad=typing.cast(Value, {"mapping": 1}))
            assert list(graph.find_nodes()) == []

    def test_invalid_relationship_write_is_atomic(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node()
            with pytest.raises(NotFoundError):
                graph.add_relationship(node, "ALLIES_WITH", node.id + 1)
            assert list(graph.find_relationships()) == []

    def test_label_and_property_updates(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node("Program", designation="Kevin Flynn")
            node = graph.add_labels(node, "ISO")
            node = graph.remove_labels(node, "Program")
            updated = graph.set_properties(node, cycles=36)
            assert isinstance(updated, Node)
            assert updated.labels == frozenset({"ISO"})
            assert dict(updated) == {"designation": "Kevin Flynn", "cycles": 36}
            stripped = graph.remove_properties(updated, "cycles")
            assert isinstance(stripped, Node)
            assert dict(stripped) == {"designation": "Kevin Flynn"}

    def test_arbitrary_property_keys(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node(**{"a.b": 1, "a b": 2})
            found = list(graph.find_nodes(**{"a.b": 1}))
            assert [item.id for item in found] == [node.id]

    def test_find_relationships(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            knows = graph.add_relationship(first, "ALLIES_WITH", second, since_cycle=2020)
            graph.add_relationship(first, "TRUSTS", second, since_cycle=2020)
            found = list(graph.find_relationships("ALLIES_WITH", since_cycle=2020))
            assert [item.id for item in found] == [knows.id]

    def test_add_relationship_with_labels_and_direction(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node("Program")
            second = graph.add_node("Program")
            relationship = graph.add_relationship(
                first,
                ["TRUSTS", "ALLIES_WITH"],
                second,
                directed=False,
                since_cycle=2020,
            )
            assert relationship.labels == ("ALLIES_WITH", "TRUSTS")
            assert relationship.directed is False
            assert graph.relationship(relationship.id) == relationship

    def test_add_relationship_without_labels(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            relationship = graph.add_relationship(first, (), second)
            assert relationship.labels == ()
            assert relationship.directed is True

    def test_find_relationships_by_labels_and_direction(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            both = graph.add_relationship(
                first,
                ["ALLIES_WITH", "TRUSTS"],
                second,
                directed=False,
            )
            graph.add_relationship(first, "ALLIES_WITH", second)
            found = list(graph.find_relationships("ALLIES_WITH", "TRUSTS", directed=False))
            assert [item.id for item in found] == [both.id]
            assert list(graph.find_relationships(directed=True))

    def test_add_and_remove_relationship_labels(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            relationship = graph.add_relationship(first, "ALLIES_WITH", second)
            updated = graph.add_labels(relationship, "TRUSTS", "ISO")
            assert isinstance(updated, Relationship)
            assert updated.labels == ("ALLIES_WITH", "ISO", "TRUSTS")
            removed = graph.remove_labels(updated, "TRUSTS")
            assert removed.labels == ("ALLIES_WITH", "ISO")

    def test_relationship_ids_are_not_reused(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            relationship = graph.add_relationship(first, "ALLIES_WITH", second)
            graph.delete(relationship)
            replacement = graph.add_relationship(first, "ALLIES_WITH", second)
            assert replacement.id > relationship.id

    def test_delete_relationship(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            relationship = graph.add_relationship(first, "ALLIES_WITH", second)
            graph.delete(relationship)
            with pytest.raises(NotFoundError):
                graph.relationship(relationship.id)

    def test_connected_node_requires_detach(self) -> None:
        with Graph.open(":memory:") as graph:
            first = graph.add_node()
            second = graph.add_node()
            relationship = graph.add_relationship(first, "ALLIES_WITH", second)
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
            active.add_node(designation="Kevin Flynn")
            message = "boom"
            raise RuntimeError(message)

    def test_transaction_commits(self) -> None:
        with Graph.open(":memory:") as graph:
            with graph.transaction() as active:
                first = active.add_node("Program")
                second = active.add_node("Program")
                relationship = active.add_relationship(first, "ALLIES_WITH", second)
            assert graph.node(first.id) == first
            assert graph.relationship(relationship.id) == relationship

    def test_convenience_write_inside_transaction_rejected(self) -> None:
        with Graph.open(":memory:") as graph:
            with graph.transaction() as active:
                first = active.add_node("Program", designation="Tron")
                with pytest.raises(TransactionError, match="already active"):
                    graph.add_node("Program", designation="Clu")
                second = active.add_node("Program", designation="Rinzler")
            assert graph.node(first.id)["designation"] == "Tron"
            assert graph.node(second.id)["designation"] == "Rinzler"
