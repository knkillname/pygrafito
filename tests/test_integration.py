# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Cross-cutting tests for persistence, transactions, deletion, and traversal."""

import sqlite3
from pathlib import Path

import pytest

from pygrafito import Graph, InteropSummary, UnsupportedSqliteError
from pygrafito.model import (
    NotFoundError,
    ValidationError,
)


class TestGqlElementModelIntegration:
    """Exercise labels, direction, interop, and the version 2 break end to end."""

    def test_version_two_round_trip(self, tmp_path: Path) -> None:
        """Labels and direction survive reopen, read-only, backup, and snapshot."""
        path = tmp_path / "grid.db"
        backup = tmp_path / "backup.db"
        snapshot = tmp_path / "grid.jsonl"
        with Graph.open(path) as graph:
            first = graph.add_node("Program", designation="Tron")
            second = graph.add_node("Program", "ISO", designation="Quorra")
            graph.add_relationship(
                first,
                ["ALLIES_WITH", "TRUSTS"],
                second,
                directed=False,
                since=2020,
            )
            graph.backup_to(backup)
            assert graph.check_integrity() == ()
            assert graph.export_jsonl(snapshot) == InteropSummary(nodes=2, relationships=1)

        with Graph.open(path, readonly=True) as graph:
            relationship = next(iter(graph.find_relationships(directed=False)))
            assert relationship.labels == ("ALLIES_WITH", "TRUSTS")
            assert relationship.directed is False

        with Graph.open(backup) as copy:
            assert copy.check_integrity() == ()
            assert next(iter(copy.find_relationships("TRUSTS"))).labels == (
                "ALLIES_WITH",
                "TRUSTS",
            )

        with Graph.open(":memory:") as restored:
            assert restored.restore_jsonl(snapshot) == InteropSummary(
                nodes=2,
                relationships=1,
            )
            assert next(iter(restored.find_relationships(directed=False))).directed is False

    def test_version_one_database_and_snapshot_are_refused(self, tmp_path: Path) -> None:
        """The pre-1.0 break refuses both old files without changing them."""
        database = tmp_path / "old.db"
        connection = sqlite3.connect(database)
        try:
            connection.executescript(
                """
                CREATE TABLE nodes (id INTEGER PRIMARY KEY, props TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE node_labels (
                    node_id INTEGER NOT NULL REFERENCES nodes(id),
                    label TEXT NOT NULL,
                    PRIMARY KEY (node_id, label)
                ) WITHOUT ROWID;
                CREATE TABLE relationships (
                    id INTEGER PRIMARY KEY,
                    src INTEGER NOT NULL,
                    dst INTEGER NOT NULL,
                    rel_type TEXT NOT NULL,
                    props TEXT NOT NULL DEFAULT '{}'
                );
                PRAGMA user_version = 1;
                """
            )
            connection.commit()
        finally:
            connection.close()
        before = database.read_bytes()
        with pytest.raises(UnsupportedSqliteError, match="version 1"):
            Graph.open(database)
        assert database.read_bytes() == before

        snapshot = tmp_path / "old.jsonl"
        snapshot.write_text(
            '{"kind":"header","format":"pygrafito-jsonl","version":1,'
            '"nodes":0,"relationships":0}\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="unsupported snapshot version 1",
            ),
        ):
            graph.restore_jsonl(snapshot)


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
            active.add_node("Program", designation="Castor")
            message = "boom"
            raise RuntimeError(message)

    def test_full_lifecycle(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.db"
        with Graph.open(path) as graph:
            with graph.transaction() as active:
                ada = active.add_node("Program", designation="Kevin Flynn", cycles=36)
                grace = active.add_node("Program", designation="Quorra", cycles=37)
                bob = active.add_node("Program", designation="Sam Flynn", cycles=41)
                active.add_relationship(ada, "ALLIES_WITH", grace, since_cycle=2019)
                active.add_relationship(grace, "ALLIES_WITH", bob, since_cycle=2021)
                direct = active.add_relationship(ada, "ALLIES_WITH", bob, since_cycle=2020)

            with pytest.raises(RuntimeError):
                self._fail_after_write(graph)
            assert list(graph.find_nodes(designation="Castor")) == []

            assert [node["designation"] for node in graph.find_nodes("Program", cycles=36)] == [
                "Kevin Flynn"
            ]
            assert list(graph.find_nodes("Program", cycles="36")) == []

            steps = {
                step.node["designation"]: step.depth
                for step in graph.traverse(ada, max_depth=2, labels=["ALLIES_WITH"])
            }
            assert steps == {"Quorra": 1, "Sam Flynn": 1}

            shortest = graph.shortest_path(ada, bob, labels=["ALLIES_WITH"])
            assert shortest is not None
            assert shortest.length == 1
            assert shortest.relationships[0].id == direct.id

            paths = list(graph.paths(ada, bob, min_depth=1, max_depth=2))
            assert sorted(item.length for item in paths) == [1, 2]

            graph.delete(grace, detach=True)
            with pytest.raises(NotFoundError):
                graph.node(grace.id)
            assert list(graph.find_nodes(designation="Quorra")) == []
            assert [item.id for item in graph.find_relationships("ALLIES_WITH")] == [direct.id]
            assert graph.shortest_path(ada, bob) is not None

        reopened = Graph.open(path)
        try:
            loaded_ada = reopened.node(ada.id)
            loaded_bob = reopened.node(bob.id)
            assert loaded_ada["designation"] == "Kevin Flynn"
            assert loaded_ada.labels == frozenset({"Program"})
            assert loaded_bob["cycles"] == 41
            assert [node["designation"] for node in reopened.find_nodes("Program", cycles=36)] == [
                "Kevin Flynn"
            ]
            assert list(reopened.find_nodes(designation="Quorra")) == []
            assert [item.id for item in reopened.find_relationships("ALLIES_WITH")] == [direct.id]

            reopened_shortest = reopened.shortest_path(loaded_ada, loaded_bob)
            assert reopened_shortest is not None
            assert reopened_shortest.length == 1

            reopened_paths = list(reopened.paths(loaded_ada, loaded_bob, max_depth=2))
            assert [item.length for item in reopened_paths] == [1]

            reopened_steps = {
                step.node["designation"]: step.depth
                for step in reopened.traverse(loaded_ada, max_depth=2)
            }
            assert reopened_steps == {"Sam Flynn": 1}
        finally:
            reopened.close()

    def test_rollback_leaves_no_trace_in_lookups_or_traversal(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "rollback.db"
        with Graph.open(path) as graph:
            survivor = graph.add_node("Program", designation="Kevin Flynn")
            graph.add_relationship(survivor, "RECURSES", survivor)
            with pytest.raises(RuntimeError):
                self._fail_after_write(graph)
            assert list(graph.find_nodes("Program")) == [survivor]
            assert list(graph.find_nodes(designation="Castor")) == []
            steps = list(graph.traverse(survivor, max_depth=2))
            assert steps == []

    def test_detach_preserves_unrelated_routes(self, tmp_path: Path) -> None:
        path = tmp_path / "detach.db"
        with Graph.open(path) as graph:
            start = graph.add_node("Program", designation="Grid")
            left = graph.add_node("Program", designation="Safehouse")
            right = graph.add_node("Program", designation="Outlands")
            end = graph.add_node("Program", designation="Portal")
            graph.add_relationship(start, "GRID_LINK", left)
            graph.add_relationship(start, "GRID_LINK", right)
            graph.add_relationship(left, "GRID_LINK", end)
            graph.add_relationship(right, "GRID_LINK", end)
            assert sorted(path.length for path in graph.paths(start, end, max_depth=2)) == [
                2,
                2,
            ]
            graph.delete(left, detach=True)
            remaining = list(graph.paths(start, end, max_depth=2))
            assert len(remaining) == 1
            assert remaining[0].nodes == (start, right, end)
            assert [node["designation"] for node in graph.find_nodes("Program")] == [
                "Grid",
                "Outlands",
                "Portal",
            ]
