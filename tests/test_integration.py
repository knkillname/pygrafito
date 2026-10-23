# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Cross-cutting tests for persistence, transactions, deletion, and traversal."""

from pathlib import Path

import pytest

from pygrafito import Graph
from pygrafito.model import (
    NotFoundError,
)


class TestGraphLifecycle:
    """Exercise every subsystem against one file-backed graph."""

    @staticmethod
    def _fail_after_write(graph: Graph) -> None:
        """Add a node inside a transaction, then fail.

        Parameters
        ----------
        graph : Graph
            Graph that should roll back the write.

        Raises
        ------
        RuntimeError
            Always, to trigger rollback.
        """
        with graph.transaction() as active:
            active.add_node("Person", name="Charlie")
            message = "boom"
            raise RuntimeError(message)

    def test_full_lifecycle(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.db"
        with Graph.open(path) as graph:
            with graph.transaction() as active:
                ada = active.add_node("Person", name="Ada", age=36)
                grace = active.add_node("Person", name="Grace", age=37)
                bob = active.add_node("Person", name="Bob", age=41)
                active.add_relationship(ada, "KNOWS", grace, since=2019)
                active.add_relationship(grace, "KNOWS", bob, since=2021)
                direct = active.add_relationship(ada, "KNOWS", bob, since=2020)

            with pytest.raises(RuntimeError):
                self._fail_after_write(graph)
            assert list(graph.find_nodes(name="Charlie")) == []

            assert [node["name"] for node in graph.find_nodes("Person", age=36)] == ["Ada"]
            assert list(graph.find_nodes("Person", age="36")) == []

            steps = {
                step.node["name"]: step.depth
                for step in graph.traverse(ada, max_depth=2, types=["KNOWS"])
            }
            assert steps == {"Grace": 1, "Bob": 1}

            shortest = graph.shortest_path(ada, bob, types=["KNOWS"])
            assert shortest is not None
            assert shortest.length == 1
            assert shortest.relationships[0].id == direct.id

            paths = list(graph.paths(ada, bob, min_depth=1, max_depth=2))
            assert sorted(item.length for item in paths) == [1, 2]

            graph.delete(grace, detach=True)
            with pytest.raises(NotFoundError):
                graph.node(grace.id)
            assert list(graph.find_nodes(name="Grace")) == []
            assert [item.id for item in graph.find_relationships("KNOWS")] == [direct.id]
            assert graph.shortest_path(ada, bob) is not None

        reopened = Graph.open(path)
        try:
            loaded_ada = reopened.node(ada.id)
            loaded_bob = reopened.node(bob.id)
            assert loaded_ada["name"] == "Ada"
            assert loaded_ada.labels == frozenset({"Person"})
            assert loaded_bob["age"] == 41
            assert [node["name"] for node in reopened.find_nodes("Person", age=36)] == ["Ada"]
            assert list(reopened.find_nodes(name="Grace")) == []
            assert [item.id for item in reopened.find_relationships("KNOWS")] == [direct.id]

            reopened_shortest = reopened.shortest_path(loaded_ada, loaded_bob)
            assert reopened_shortest is not None
            assert reopened_shortest.length == 1

            reopened_paths = list(reopened.paths(loaded_ada, loaded_bob, max_depth=2))
            assert [item.length for item in reopened_paths] == [1]

            reopened_steps = {
                step.node["name"]: step.depth for step in reopened.traverse(loaded_ada, max_depth=2)
            }
            assert reopened_steps == {"Bob": 1}
        finally:
            reopened.close()

    def test_rollback_leaves_no_trace_in_lookups_or_traversal(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "rollback.db"
        with Graph.open(path) as graph:
            survivor = graph.add_node("Person", name="Ada")
            graph.add_relationship(survivor, "SELF", survivor)
            with pytest.raises(RuntimeError):
                self._fail_after_write(graph)
            assert list(graph.find_nodes("Person")) == [survivor]
            assert list(graph.find_nodes(name="Charlie")) == []
            steps = list(graph.traverse(survivor, max_depth=2))
            assert steps == []

    def test_detach_preserves_unrelated_routes(self, tmp_path: Path) -> None:
        path = tmp_path / "detach.db"
        with Graph.open(path) as graph:
            start = graph.add_node("Person", name="start")
            left = graph.add_node("Person", name="left")
            right = graph.add_node("Person", name="right")
            end = graph.add_node("Person", name="end")
            graph.add_relationship(start, "ROUTE", left)
            graph.add_relationship(start, "ROUTE", right)
            graph.add_relationship(left, "ROUTE", end)
            graph.add_relationship(right, "ROUTE", end)
            assert sorted(path.length for path in graph.paths(start, end, max_depth=2)) == [
                2,
                2,
            ]
            graph.delete(left, detach=True)
            remaining = list(graph.paths(start, end, max_depth=2))
            assert len(remaining) == 1
            assert remaining[0].nodes == (start, right, end)
            assert [node["name"] for node in graph.find_nodes("Person")] == [
                "start",
                "right",
                "end",
            ]
