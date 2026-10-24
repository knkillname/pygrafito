# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""End-to-end tests for statement-driven import and reopen."""

import pathlib

from pygrafito import Graph


class TestImportIntegration:
    """Verify imports compose with queries and survive a reopen."""

    def test_jsonl_import_then_reopen(self, tmp_path: pathlib.Path) -> None:
        database = tmp_path / "grid.db"
        rows = tmp_path / "programs.jsonl"
        rows.write_text(
            '{"designation": "Kevin Flynn", "cycles": 36}\n'
            '{"designation": "Quorra", "cycles": 37}\n'
            '{"designation": "Tron", "cycles": 40}\n',
            encoding="utf-8",
        )
        with Graph.open(database) as graph:
            summary = graph.import_file(
                rows,
                "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
                "ON CREATE SET n.cycles = row.cycles",
            )
            assert summary.rows == 3
            assert summary.mutations.created_nodes == 3

        with Graph.open(database) as graph:
            result = graph.query(
                "MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles ORDER BY name"
            )
            assert [tuple(row.values()) for row in result] == [
                ("Kevin Flynn", 36),
                ("Quorra", 37),
                ("Tron", 40),
            ]

    def test_relationship_import_between_imported_nodes(self, tmp_path: pathlib.Path) -> None:
        database = tmp_path / "grid.db"
        programs = tmp_path / "programs.jsonl"
        programs.write_text(
            '{"designation": "Kevin Flynn"}\n{"designation": "Quorra"}\n',
            encoding="utf-8",
        )
        alliances = tmp_path / "alliances.jsonl"
        alliances.write_text(
            '{"source": "Kevin Flynn", "target": "Quorra"}\n'
            '{"source": "Kevin Flynn", "target": "Quorra"}\n',
            encoding="utf-8",
        )
        with Graph.open(database) as graph:
            graph.import_file(
                programs,
                "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})",
            )
            summary = graph.import_file(
                alliances,
                "UNWIND $rows AS row "
                "MATCH (a:Program {designation: row.source}), "
                "(b:Program {designation: row.target}) "
                "MERGE (a)-[r:ALLIES_WITH]->(b)",
            )
            assert summary.rows == 2
            assert summary.mutations.created_relationships == 1

        with Graph.open(database) as graph:
            result = graph.query(
                "MATCH (a:Program)-[r:ALLIES_WITH]->(b:Program) "
                "RETURN a.designation AS source, b.designation AS target"
            )
            assert [tuple(row.values()) for row in result] == [("Kevin Flynn", "Quorra")]

    def test_conditional_update_after_reopen(self, tmp_path: pathlib.Path) -> None:
        database = tmp_path / "grid.db"
        with Graph.open(database) as graph:
            graph.import_rows(
                "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
                "ON CREATE SET n.cycles = row.cycles",
                [{"designation": "Tron", "cycles": 40}],
            )

        with Graph.open(database) as graph:
            graph.import_rows(
                "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
                "ON MATCH SET n.cycles = n.cycles + 1",
                [{"designation": "Tron"}],
            )

        with Graph.open(database) as graph:
            result = graph.query(
                "MATCH (n:Program {designation: 'Tron'}) RETURN n.cycles AS cycles"
            )
            assert [tuple(row.values()) for row in result] == [(41,)]

    def test_in_memory_import_reports_summary(self) -> None:
        with Graph.open(":memory:") as graph:
            summary = graph.import_rows(
                "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})",
                [{"designation": "Quorra"}, {"designation": "Quorra"}],
                batch_size=1,
            )
            assert summary.rows == 2
            assert summary.batches == 2
            assert summary.mutations.created_nodes == 1
