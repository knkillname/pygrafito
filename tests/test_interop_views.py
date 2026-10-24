# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the read-only interop views."""

import contextlib
import json
import sqlite3
from pathlib import Path

import pytest

from pygrafito import Graph, InteropSummary, UnsupportedSqliteError


class Fixtures:
    """Build and inspect the themed graph used by view tests."""

    @staticmethod
    def seed(path: Path) -> None:
        """Create a graph with typed properties and relationships.

        Parameters
        ----------
        path : Path
            Database path.
        """
        with Graph.open(path) as graph:
            tron = graph.add_node(
                "Program",
                designation="Tron",
                cycles=40,
                active=True,
                **{"a.b": 1},
            )
            quorra = graph.add_node(
                "Program",
                "ISO",
                designation="Quorra",
                cycles=37,
                count=1,
            )
            graph.add_node(cycles=37)
            graph.add_relationship(tron, "ALLIES_WITH", quorra, since_cycle=2020)
            graph.add_relationship(tron, "GUARDS", tron)

    @staticmethod
    def connection(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
        """Open a raw SQLite connection to a graph file.

        Parameters
        ----------
        path : Path
            Database path.
        readonly : bool, optional
            Whether to open the file read-only, by default ``False``.

        Returns
        -------
        sqlite3.Connection
            Raw connection.
        """
        if readonly:
            return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        return sqlite3.connect(path)

    @staticmethod
    def drop_views(connection: sqlite3.Connection) -> None:
        """Drop every reserved view.

        Parameters
        ----------
        connection : sqlite3.Connection
            Raw connection.
        """
        for name in ("graph_nodes", "graph_node_labels", "graph_relationships", "graph_meta"):
            connection.execute(f"DROP VIEW IF EXISTS {name}")
        connection.commit()

    @staticmethod
    def view_names(connection: sqlite3.Connection) -> set[str]:
        """Return the view names in the database.

        Parameters
        ----------
        connection : sqlite3.Connection
            Raw connection.

        Returns
        -------
        set[str]
            Existing view names.
        """
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        }

    @staticmethod
    def columns(connection: sqlite3.Connection, name: str) -> list[tuple[str, str]]:
        """Return column names and reported types for a view.

        Parameters
        ----------
        connection : sqlite3.Connection
            Raw connection.
        name : str
            View name.

        Returns
        -------
        list[tuple[str, str]]
            Column name and SQLite type.
        """
        return [
            (str(row[1]), str(row[2])) for row in connection.execute(f"PRAGMA table_info({name})")
        ]


class TestViewSchema:
    """Verify publication, columns, and the external reader contract."""

    def test_writable_open_publishes_views(self, tmp_path: Path) -> None:
        """A write-capable open creates all four views."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with Graph.open(path) as graph:
            assert graph.view_version == 1
        with contextlib.closing(Fixtures.connection(path)) as connection:
            names = Fixtures.view_names(connection)
        assert {
            "graph_nodes",
            "graph_node_labels",
            "graph_relationships",
            "graph_meta",
        } <= names

    def test_view_columns_and_types(self, tmp_path: Path) -> None:
        """The public views expose the documented columns and types."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            assert Fixtures.columns(connection, "graph_nodes") == [
                ("id", "INTEGER"),
                ("labels", "TEXT"),
                ("properties", "TEXT"),
            ]
            assert Fixtures.columns(connection, "graph_node_labels") == [
                ("node_id", "INTEGER"),
                ("label", "TEXT"),
            ]
            assert Fixtures.columns(connection, "graph_relationships") == [
                ("id", "INTEGER"),
                ("start_id", "INTEGER"),
                ("end_id", "INTEGER"),
                ("type", "TEXT"),
                ("properties", "TEXT"),
            ]
            assert Fixtures.columns(connection, "graph_meta") == [
                ("key", "TEXT"),
                ("value", "TEXT"),
            ]

    def test_external_reader_values(self, tmp_path: Path) -> None:
        """A separate read-only connection sees labels, properties, and metadata."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path, readonly=True)) as connection:
            nodes = connection.execute(
                "SELECT id, labels, properties FROM graph_nodes ORDER BY id"
            ).fetchall()
            assert [row[0] for row in nodes] == [1, 2, 3]
            assert nodes[0][1] == '["Program"]'
            assert json.loads(nodes[0][2]) == {
                "a.b": 1,
                "active": True,
                "cycles": 40,
                "designation": "Tron",
            }
            assert nodes[1][1] == '["ISO","Program"]'
            assert json.loads(nodes[1][2]) == {
                "count": 1,
                "cycles": 37,
                "designation": "Quorra",
            }
            assert nodes[2][1] == "[]"
            assert json.loads(nodes[2][2]) == {"cycles": 37}

            labels = connection.execute(
                "SELECT node_id, label FROM graph_node_labels ORDER BY node_id, label"
            ).fetchall()
            assert labels == [(1, "Program"), (2, "ISO"), (2, "Program")]

            relationships = connection.execute(
                "SELECT id, start_id, end_id, type, properties FROM graph_relationships ORDER BY id"
            ).fetchall()
            assert relationships == [
                (1, 1, 2, "ALLIES_WITH", '{"since_cycle":2020}'),
                (2, 1, 1, "GUARDS", "{}"),
            ]

            assert connection.execute(
                "SELECT value FROM graph_meta WHERE key = 'format'"
            ).fetchone() == ("pygrafito",)
            assert connection.execute(
                "SELECT value FROM graph_meta WHERE key = 'view_version'"
            ).fetchone() == ("1",)

            active = connection.execute(
                "SELECT json_type(properties, '$.active'), "
                "json_extract(properties, '$.active') FROM graph_nodes WHERE id = 1"
            ).fetchone()
            assert active == ("true", 1)
            count = connection.execute(
                "SELECT json_type(properties, '$.count'), "
                "json_extract(properties, '$.count') FROM graph_nodes WHERE id = 2"
            ).fetchone()
            assert count == ("integer", 1)
            dotted = connection.execute(
                "SELECT json_extract(properties, '$.\"a.b\"') FROM graph_nodes WHERE id = 1"
            ).fetchone()
            assert dotted == (1,)

    def test_views_are_read_only(self, tmp_path: Path) -> None:
        """SQLite refuses writes through a view."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            with pytest.raises(sqlite3.OperationalError, match="cannot modify"):
                connection.execute("UPDATE graph_nodes SET properties = '{}'")
            with pytest.raises(sqlite3.OperationalError, match="cannot modify"):
                connection.execute("DELETE FROM graph_relationships")


class TestViewPublication:
    """Verify missing, older, newer, and colliding view states."""

    def test_read_only_open_without_views(self, tmp_path: Path) -> None:
        """A pre-view file opens read-only and is published by the next write."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            Fixtures.drop_views(connection)

        destination = tmp_path / "snapshot.jsonl"
        with Graph.open(path, readonly=True) as graph:
            assert graph.view_version == 0
            assert graph.node(1)["designation"] == "Tron"
            graph.export_jsonl(destination)
        assert destination.exists()

        with Graph.open(path) as graph:
            assert graph.view_version == 1
        with contextlib.closing(Fixtures.connection(path)) as connection:
            assert "graph_nodes" in Fixtures.view_names(connection)

    def test_older_view_version_is_upgraded(self, tmp_path: Path) -> None:
        """A write-capable open replaces an older view version."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            Fixtures.drop_views(connection)
            connection.execute(
                "CREATE VIEW graph_meta AS SELECT 'view_version' AS key, '0' AS value"
            )
            connection.execute("CREATE VIEW graph_nodes AS SELECT 1 AS marker")
            connection.commit()

        with Graph.open(path) as graph:
            assert graph.view_version == 1
        with contextlib.closing(Fixtures.connection(path)) as connection:
            assert Fixtures.columns(connection, "graph_nodes") == [
                ("id", "INTEGER"),
                ("labels", "TEXT"),
                ("properties", "TEXT"),
            ]

    def test_newer_view_version_is_left_alone(self, tmp_path: Path) -> None:
        """A newer view version is not downgraded."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            Fixtures.drop_views(connection)
            connection.execute(
                "CREATE VIEW graph_meta AS SELECT 'view_version' AS key, '2' AS value"
            )
            connection.execute("CREATE VIEW graph_nodes AS SELECT 1 AS marker")
            connection.commit()

        with Graph.open(path) as graph:
            assert graph.view_version == 2
        with contextlib.closing(Fixtures.connection(path)) as connection:
            assert Fixtures.columns(connection, "graph_nodes") == [("marker", "")]

    def test_missing_view_is_recreated(self, tmp_path: Path) -> None:
        """A current version with a missing view is repaired."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            connection.execute("DROP VIEW graph_nodes")
            connection.commit()

        with Graph.open(path) as graph:
            assert graph.view_version == 1
        with contextlib.closing(Fixtures.connection(path)) as connection:
            assert Fixtures.columns(connection, "graph_nodes") == [
                ("id", "INTEGER"),
                ("labels", "TEXT"),
                ("properties", "TEXT"),
            ]

    def test_table_collision_is_refused(self, tmp_path: Path) -> None:
        """A reserved name held by a table stops publication."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            connection.execute("DROP VIEW graph_nodes")
            connection.execute("CREATE TABLE graph_nodes (marker INTEGER)")
            connection.commit()

        with pytest.raises(UnsupportedSqliteError, match="is a table"):
            Graph.open(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            assert Fixtures.columns(connection, "graph_nodes") == [("marker", "INTEGER")]

        with Graph.open(path, readonly=True) as graph:
            assert graph.node(1)["designation"] == "Tron"

    def test_unidentified_view_is_refused(self, tmp_path: Path) -> None:
        """A reserved view without graph_meta is not replaced."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            Fixtures.drop_views(connection)
            connection.execute("CREATE VIEW graph_relationships AS SELECT 1 AS id")
            connection.commit()

        with pytest.raises(UnsupportedSqliteError, match="without graph_meta"):
            Graph.open(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            assert "graph_relationships" in Fixtures.view_names(connection)

    def test_malformed_meta_is_refused(self, tmp_path: Path) -> None:
        """graph_meta without a version record is not trusted."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            Fixtures.drop_views(connection)
            connection.execute("CREATE VIEW graph_meta AS SELECT 'other' AS key, '1' AS value")
            connection.commit()

        with pytest.raises(UnsupportedSqliteError, match="valid view_version"):
            Graph.open(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            assert "graph_meta" in Fixtures.view_names(connection)

    def test_engine_works_without_views(self, tmp_path: Path) -> None:
        """Reads, export, and restore do not depend on the views."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with contextlib.closing(Fixtures.connection(path)) as connection:
            Fixtures.drop_views(connection)

        destination = tmp_path / "snapshot.jsonl"
        with Graph.open(path, readonly=True) as graph:
            assert graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"] == 3
            graph.export_jsonl(destination)

        with Graph.open(":memory:") as graph:
            assert graph.restore_jsonl(destination) == InteropSummary(
                nodes=3,
                relationships=2,
            )
