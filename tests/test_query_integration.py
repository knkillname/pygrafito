# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""End-to-end persistence and schema-compatibility tests for queries."""

import sqlite3
from pathlib import Path

from pygrafito import Graph
from pygrafito.storage.schema import Schema


class TestQueryIntegration:
    """Verify queries across persistence, transactions, and later writes."""

    def test_file_persistence_with_prepared_queries(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            with graph.transaction() as transaction:
                kevin = transaction.add_node(
                    "Program",
                    designation="Kevin Flynn",
                    cycles=36,
                )
                quorra = transaction.add_node(
                    "Program",
                    designation="Quorra",
                    cycles=37,
                )
                transaction.add_relationship(kevin, "ALLIES_WITH", quorra)
            prepared = graph.prepare(
                "MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles "
                "ORDER BY n.cycles DESC"
            )
            result = prepared.execute()
            assert [tuple(row.values()) for row in result] == [
                ("Quorra", 37),
                ("Kevin Flynn", 36),
            ]
            graph.add_node("Program", designation="Tron", cycles=40)
            assert [tuple(row.values()) for row in result] == [
                ("Quorra", 37),
                ("Kevin Flynn", 36),
            ]
            assert graph.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"] == 3

        with Graph.open(path) as reopened:
            ordered = reopened.query(
                "MATCH (n:Program) RETURN n.designation ORDER BY n.cycles DESC"
            )
            assert [row["n.designation"] for row in ordered] == [
                "Tron",
                "Quorra",
                "Kevin Flynn",
            ]
            aggregate = reopened.query(
                "MATCH (a:Program)-[:ALLIES_WITH]->(b:Program) "
                "RETURN a.designation AS start, b.designation AS end, count(*) AS total"
            )
            assert [tuple(row.values()) for row in aggregate] == [("Kevin Flynn", "Quorra", 1)]

    def test_pre_change_schema_opens_without_migration(self, tmp_path: Path) -> None:
        path = tmp_path / "legacy.db"
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                """
                CREATE TABLE nodes (
                    id    INTEGER PRIMARY KEY,
                    props TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(props))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE node_labels (
                    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                    label   TEXT NOT NULL,
                    PRIMARY KEY (node_id, label)
                ) WITHOUT ROWID
                """
            )
            connection.execute("CREATE INDEX node_labels_by_label ON node_labels (label, node_id)")
            connection.execute(
                """
                CREATE TABLE relationships (
                    id       INTEGER PRIMARY KEY,
                    src      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE RESTRICT,
                    dst      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE RESTRICT,
                    rel_type TEXT NOT NULL,
                    props    TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(props))
                )
                """
            )
            connection.execute("CREATE INDEX rel_by_src ON relationships (src, rel_type, dst)")
            connection.execute("CREATE INDEX rel_by_dst ON relationships (dst, rel_type, src)")
            connection.execute(
                "INSERT INTO nodes (id, props) VALUES (?, ?)",
                (1, '{"cycles":36,"designation":"Kevin Flynn"}'),
            )
            connection.execute(
                "INSERT INTO node_labels (node_id, label) VALUES (?, ?)",
                (1, "Program"),
            )
            connection.execute("PRAGMA user_version = 1")
            connection.commit()
        finally:
            connection.close()

        with Graph.open(path) as graph:
            result = graph.query(
                "MATCH (n:Program) WHERE n.cycles = 36 RETURN n.designation AS name"
            )
            assert result.rows[0]["name"] == "Kevin Flynn"
            assert Schema.VERSION == 1
            version = graph._database.connection.execute("PRAGMA user_version").fetchone()
            assert version == (1,)
