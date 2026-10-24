# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for read-only graph handles."""

import sqlite3
from pathlib import Path

import pytest

import pygrafito
from pygrafito import (
    Graph,
    NotFoundError,
    QueryResult,
    ReadOnlyError,
    UnsupportedSqliteError,
    ValidationError,
)


class TestReadOnlyHandles:
    """Verify that a read-only handle keeps the graph immutable."""

    @pytest.fixture
    def populated(self, tmp_path: Path) -> Path:
        """Create a file-backed graph with one node and one relationship.

        Parameters
        ----------
        tmp_path : Path
            Temporary directory for the database file.

        Yields
        ------
        Path
            Path of the closed database.
        """
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
        return path

    def test_read_only_error_is_a_pygrafito_error(self) -> None:
        """ReadOnlyError belongs to the public error hierarchy."""
        assert issubclass(ReadOnlyError, pygrafito.PygrafitoError)
        assert "ReadOnlyError" in pygrafito.__all__

    def test_reads_succeed(self, populated: Path) -> None:
        """Reads, queries, and traversal work on a read-only handle."""
        with Graph.open(populated, readonly=True) as graph:
            node = graph.node(1)
            result = graph.query("MATCH (n:Program) RETURN n.designation AS name ORDER BY name")
            steps = list(graph.traverse(node, max_depth=1))

            assert node["designation"] == "Kevin Flynn"
            assert [row["name"] for row in result] == ["Kevin Flynn", "Quorra"]
            assert [step.node["designation"] for step in steps] == ["Quorra"]

    def test_convenience_write_is_rejected(self, populated: Path) -> None:
        """Adding a node on a read-only handle changes nothing."""
        with Graph.open(populated, readonly=True) as graph, pytest.raises(ReadOnlyError):
            graph.add_node("Program", designation="Tron")

        with Graph.open(populated) as graph:
            assert len(list(graph.find_nodes("Program"))) == 2

    def test_query_write_is_rejected(self, populated: Path) -> None:
        """A statement with a write clause raises before executing."""
        with Graph.open(populated, readonly=True) as graph, pytest.raises(ReadOnlyError):
            graph.query("CREATE (n:Program {designation: 'Tron'})")

        with Graph.open(populated) as graph:
            assert graph.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"] == 2

    def test_transaction_is_rejected(self, populated: Path) -> None:
        """An explicit transaction cannot start on a read-only handle."""
        with Graph.open(populated, readonly=True) as graph, pytest.raises(ReadOnlyError):
            graph.transaction()

    def test_index_change_is_rejected(self, populated: Path) -> None:
        """Index declarations and drops are writes."""
        with Graph.open(populated, readonly=True) as graph, pytest.raises(ReadOnlyError):
            graph.create_node_index("designation")

    def test_missing_file_is_not_created(self, tmp_path: Path) -> None:
        """A read-only open never creates a missing database."""
        path = tmp_path / "missing.db"

        with pytest.raises(NotFoundError):
            Graph.open(path, readonly=True)

        assert not path.exists()

    def test_in_memory_is_rejected(self) -> None:
        """Read-only is only meaningful for a file."""
        with pytest.raises(ValidationError):
            Graph.open(":memory:", readonly=True)

    def test_non_graph_sqlite_file_is_rejected(self, tmp_path: Path) -> None:
        """A read-only open cannot bootstrap a new schema."""
        path = tmp_path / "plain.db"
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        finally:
            connection.close()

        with pytest.raises(UnsupportedSqliteError):
            Graph.open(path, readonly=True)

        assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone() == (0,)

    def test_path_with_spaces(self, tmp_path: Path) -> None:
        """A read-only path is URI-encoded rather than interpreted as a query."""
        directory = tmp_path / "Grid Files"
        directory.mkdir()
        path = directory / "the grid.db"
        with Graph.open(path) as graph:
            graph.add_node("Program", designation="Rinzler")

        with Graph.open(path, readonly=True) as graph:
            assert (
                graph.query("MATCH (n:Program) RETURN n.designation AS name").rows[0]["name"]
                == "Rinzler"
            )

    def test_read_only_result_is_materialized(self, populated: Path) -> None:
        """A read-only query still returns an immutable materialized result."""
        with Graph.open(populated, readonly=True) as graph:
            result = graph.query("MATCH (n:Program) RETURN n.designation AS name")
            assert isinstance(result, QueryResult)
