# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""End-to-end persistence and schema-compatibility tests for queries."""

import sqlite3
import typing
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


class TestWriteStatementIntegration:
    """Verify read and write statements through both public entry points."""

    def test_graph_query_read_and_write(self) -> None:
        with Graph.open(":memory:") as graph:
            created = graph.query(
                "CREATE (n:Program {designation: 'Kevin Flynn', cycles: 36}) "
                "RETURN n.cycles AS cycles"
            )
            assert [row["cycles"] for row in created] == [36]
            read = graph.query("MATCH (n:Program) RETURN n.designation AS name")
            assert [row["name"] for row in read] == ["Kevin Flynn"]

    def test_transaction_query_read_and_write(self) -> None:
        with Graph.open(":memory:") as graph:
            with graph.transaction() as transaction:
                transaction.query("CREATE (n:Program {designation: 'Quorra'})")
                result = transaction.query("MATCH (n:Program) RETURN n.designation AS name")
                assert [row["name"] for row in result] == ["Quorra"]
            assert len(list(graph.find_nodes("Program", designation="Quorra"))) == 1

    def test_write_end_to_end_across_reopen(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            graph.query("CREATE (k:Program {designation: 'Kevin Flynn', cycles: 36})")
            graph.query("CREATE (q:Program {designation: 'Quorra', cycles: 37})")
            kevin = next(iter(graph.find_nodes("Program", designation="Kevin Flynn")))
            quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = 38")
            graph.query("MATCH (n:Program {designation: 'Kevin Flynn'}) DETACH DELETE n")
        with Graph.open(path) as graph:
            quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
            assert quorra["cycles"] == 38
            assert list(graph.find_nodes("Program", designation="Kevin Flynn")) == []
            assert list(graph.find_relationships("ALLIES_WITH")) == []


class TestKeyInjectionSafety:
    """Verify SQL-shaped property keys are matched literally."""

    HOSTILE_KEY: typing.ClassVar[str] = "'); DROP TABLE nodes; --"
    OR_KEY: typing.ClassVar[str] = "x' OR '1'='1"

    def test_query_matches_hostile_key_literally(self) -> None:
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", **{self.HOSTILE_KEY: 1})
            graph.add_node("Program", designation="Quorra")
            result = graph.query(
                f"MATCH (n:Program {{`{self.HOSTILE_KEY}`: 1}}) RETURN n.designation AS name"
            )
            assert [row["name"] for row in result] == [None]

    def test_query_keeps_the_store_intact(self) -> None:
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", **{self.HOSTILE_KEY: 1})
            graph.add_node("Program", designation="Tron")
            graph.query(f"MATCH (n {{`{self.HOSTILE_KEY}`: 1}}) RETURN n")
            assert graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"] == 2

    def test_or_shaped_key_does_not_widen_match(self) -> None:
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", **{self.OR_KEY: 1})
            graph.add_node("Program", **{self.OR_KEY: 2})
            result = graph.query(f"MATCH (n:Program {{`{self.OR_KEY}`: 1}}) RETURN n")
            assert len(result.rows) == 1

    def test_lookup_matches_hostile_key_literally(self) -> None:
        with Graph.open(":memory:") as graph:
            matched = graph.add_node("Program", **{self.HOSTILE_KEY: 7})
            graph.add_node("Program", **{self.HOSTILE_KEY: 8})
            found = list(graph.find_nodes("Program", **{self.HOSTILE_KEY: 7}))
            assert [node.id for node in found] == [matched.id]
            assert graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"] == 2

    def test_relationship_query_matches_hostile_key_literally(self) -> None:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, **{self.HOSTILE_KEY: 2020})
            result = graph.query(
                f"MATCH (a)-[r:ALLIES_WITH {{`{self.HOSTILE_KEY}`: 2020}}]->(b) "
                f"RETURN b.designation AS name"
            )
            assert [row["name"] for row in result] == ["Quorra"]
