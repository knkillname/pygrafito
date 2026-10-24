# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the embedding contract of file-backed graphs."""

import sqlite3
from pathlib import Path

import pytest

from pygrafito import Graph, GraphClosedError, UnsupportedSqliteError, ValidationError


class TestJournalMode:
    """Verify the reported journal mode matches what the file obtained."""

    def test_in_memory_reports_memory(self) -> None:
        with Graph.open(":memory:") as graph:
            assert graph.journal_mode == "memory"

    def test_file_reports_write_ahead_logging(self, tmp_path: Path) -> None:
        with Graph.open(tmp_path / "grid.db") as graph:
            assert graph.journal_mode == "wal"

    def test_read_only_file_reports_write_ahead_logging(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path):
            pass
        with Graph.open(path, readonly=True) as graph:
            assert graph.journal_mode == "wal"

    def test_journal_mode_rejects_a_closed_handle(self) -> None:
        graph = Graph.open(":memory:")
        graph.close()
        with pytest.raises(GraphClosedError):
            _ = graph.journal_mode


class TestReadSnapshots:
    """Verify each public read observes one state and leaves no transaction open."""

    def test_read_inside_transaction_sees_its_writes(self) -> None:
        with Graph.open(":memory:") as graph, graph.transaction() as transaction:
            node = transaction.add_node("Program", designation="Tron")
            assert graph.node(node.id) == node
            assert [item.id for item in graph.find_nodes("Program")] == [node.id]
            path = graph.shortest_path(node, node)
            assert path is not None
            assert path.start == node

    def test_traverse_iterator_does_not_hold_a_transaction(self) -> None:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            iterator = graph.traverse(kevin, max_depth=1)
            assert not graph._database.connection.in_transaction
            graph.add_node("Program", designation="Tron")
            assert [step.node.id for step in iterator] == [quorra.id]

    def test_paths_iterator_does_not_hold_a_transaction(self) -> None:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            iterator = graph.paths(kevin, quorra, max_depth=1)
            assert not graph._database.connection.in_transaction
            graph.add_node("Program", designation="Rinzler")
            assert [path.length for path in iterator] == [1]

    def test_abandoned_iterator_leaves_the_handle_usable(self) -> None:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            _ = graph.traverse(kevin, max_depth=2)
            _ = graph.paths(kevin, quorra, max_depth=2)
            graph.add_node("Program", designation="Tron")
            assert len(list(graph.find_nodes("Program"))) == 3


class TestBusyTimeout:
    """Verify the timeout knob is validated and applied."""

    def test_default_timeout_is_configured(self) -> None:
        with Graph.open(":memory:") as graph:
            row = graph._database.connection.execute("PRAGMA busy_timeout").fetchone()
        assert row == (5000,)

    def test_explicit_timeout_is_configured(self) -> None:
        with Graph.open(":memory:", busy_timeout=25) as graph:
            row = graph._database.connection.execute("PRAGMA busy_timeout").fetchone()
        assert row == (25,)

    def test_negative_timeout_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Graph.open(":memory:", busy_timeout=-1)

    def test_boolean_timeout_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Graph.open(":memory:", busy_timeout=True)


class TestForeignDatabaseRefusal:
    """Verify that opening never adopts an unrelated SQLite database."""

    @staticmethod
    def foreign_database(path: Path) -> None:
        """Create a database with one unrelated table.

        Parameters
        ----------
        path : Path
            Destination database file.
        """
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY, name TEXT)")
            connection.execute("INSERT INTO unrelated (name) VALUES ('Clu')")
            connection.commit()
        finally:
            connection.close()

    def test_writable_open_is_refused_and_leaves_the_file_untouched(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "plain.db"
        self.foreign_database(path)
        with pytest.raises(UnsupportedSqliteError):
            Graph.open(path)
        connection = sqlite3.connect(path)
        try:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert tables == {"unrelated"}
            assert connection.execute("PRAGMA user_version").fetchone() == (0,)
            assert connection.execute("SELECT name FROM unrelated").fetchall() == [("Clu",)]
        finally:
            connection.close()

    def test_read_only_open_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "plain.db"
        self.foreign_database(path)
        with pytest.raises(UnsupportedSqliteError):
            Graph.open(path, readonly=True)

    def test_fresh_file_is_accepted(self, tmp_path: Path) -> None:
        with Graph.open(tmp_path / "fresh.db") as graph:
            graph.add_node("Program", designation="Tron")

    def test_empty_file_is_accepted(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.db"
        sqlite3.connect(path).close()
        with Graph.open(path) as graph:
            graph.add_node("Program", designation="Rinzler")

    def test_graph_file_with_an_added_table_is_accepted(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            graph.add_node("Program", designation="Kevin Flynn")
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE external (id INTEGER PRIMARY KEY)")
            connection.execute("INSERT INTO external (id) VALUES (1)")
            connection.commit()
        finally:
            connection.close()
        with Graph.open(path) as graph:
            assert graph.node(1)["designation"] == "Kevin Flynn"
        connection = sqlite3.connect(path)
        try:
            assert connection.execute("SELECT id FROM external").fetchall() == [(1,)]
        finally:
            connection.close()

    def test_views_do_not_make_a_file_foreign(self, tmp_path: Path) -> None:
        path = tmp_path / "views.db"
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE VIEW visible AS SELECT 1 AS value")
        finally:
            connection.close()
        with Graph.open(path) as graph:
            graph.add_node("Program", designation="Quorra")
        connection = sqlite3.connect(path)
        try:
            assert connection.execute("SELECT value FROM visible").fetchall() == [(1,)]
        finally:
            connection.close()
