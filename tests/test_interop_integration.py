# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""End-to-end tests for snapshot export, restore, and SQL views."""

import contextlib
import sqlite3
from pathlib import Path

from pygrafito import Graph, InteropSummary
from tests.cli.support import Fixtures, Harness


class TestInteropIntegration:
    """Verify the snapshot and view surfaces compose."""

    def test_snapshot_then_views(self, tmp_path: Path) -> None:
        """Export, restore, and read every view through a separate connection."""
        source = tmp_path / "grid.db"
        snapshot = tmp_path / "grid.jsonl"
        target = tmp_path / "restored.db"
        with Graph.open(source) as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node(
                "Program",
                "ISO",
                designation="Quorra",
                cycles=37,
            )
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)

        with Graph.open(source, readonly=True) as graph:
            assert graph.export_jsonl(snapshot) == InteropSummary(
                nodes=2,
                relationships=1,
            )

        with Graph.open(target) as graph:
            assert graph.restore_jsonl(snapshot) == InteropSummary(
                nodes=2,
                relationships=1,
            )

        with contextlib.closing(sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True)) as reader:
            nodes = reader.execute(
                "SELECT id, labels, properties FROM graph_nodes ORDER BY id"
            ).fetchall()
            assert [row[0] for row in nodes] == [1, 2]
            assert nodes[0][1] == '["Program"]'
            assert nodes[1][1] == '["ISO","Program"]'

            labels = reader.execute(
                "SELECT node_id, label FROM graph_node_labels ORDER BY node_id, label"
            ).fetchall()
            assert labels == [(1, "Program"), (2, "ISO"), (2, "Program")]

            relationships = reader.execute(
                "SELECT id, start_id, end_id, labels, directed, properties "
                "FROM graph_relationships ORDER BY id"
            ).fetchall()
            assert relationships == [
                (1, 1, 2, '["ALLIES_WITH"]', 1, '{"since_cycle":2020}'),
            ]

            metadata = dict(reader.execute("SELECT key, value FROM graph_meta").fetchall())
            assert metadata == {"format": "pygrafito", "view_version": "2"}

    def test_shell_round_trip(self, tmp_path: Path) -> None:
        """The shell exports, replaces, and still exposes the views."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        snapshot = tmp_path / "grid.jsonl"
        harness = Harness(path)
        try:
            code, output, error = harness.run(
                f".export {snapshot}\n.restore {snapshot} --replace\n"
            )
            assert code == 0
            assert error == ""
            assert "exported 3 nodes and 3 relationships" in output
            assert "restored 3 nodes and 3 relationships" in output

            query_code, query_output, _ = harness.run("MATCH (n) RETURN count(*) AS total;\n")
        finally:
            harness.close()

        assert query_code == 0
        assert "3" in query_output
        with contextlib.closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as reader:
            assert reader.execute(
                "SELECT value FROM graph_meta WHERE key = 'view_version'"
            ).fetchone() == ("2",)
