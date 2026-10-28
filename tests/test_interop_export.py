# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for JSONL snapshot export."""

import json
import os
import sqlite3
import typing
from pathlib import Path

import pytest

from pygrafito import (
    Graph,
    GraphClosedError,
    InteropSummary,
    TransactionError,
    ValidationError,
)


class TestExport:
    """Verify snapshot contents, determinism, and destination safety."""

    @pytest.fixture
    def populated(self, tmp_path: Path) -> Path:
        """Create a file-backed graph with the canonical TRON fixture."""
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node("Program", "ISO", designation="Quorra", cycles=37)
            tron = graph.add_node("Program", designation="Tron", cycles=40)
            graph.add_node(cycles=37)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2021)
            graph.add_relationship(tron, "GUARDS", tron)
        return path

    def test_canonical_snapshot(self, populated: Path, tmp_path: Path) -> None:
        """Export emits the documented header and tagged records."""
        destination = tmp_path / "snapshot.jsonl"
        with Graph.open(populated) as graph:
            summary = graph.export_jsonl(destination)

        expected = (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":4,"relationships":3}\n'
            '{"kind":"node","id":1,"labels":["Program"],'
            '"properties":{"cycles":36,"designation":"Kevin Flynn"}}\n'
            '{"kind":"node","id":2,"labels":["ISO","Program"],'
            '"properties":{"cycles":37,"designation":"Quorra"}}\n'
            '{"kind":"node","id":3,"labels":["Program"],'
            '"properties":{"cycles":40,"designation":"Tron"}}\n'
            '{"kind":"node","id":4,"labels":[],"properties":{"cycles":37}}\n'
            '{"kind":"relationship","id":1,"labels":["ALLIES_WITH"],"directed":true,'
            '"start_id":1,"end_id":2,"properties":{"since_cycle":2020}}\n'
            '{"kind":"relationship","id":2,"labels":["ALLIES_WITH"],"directed":true,'
            '"start_id":1,"end_id":2,"properties":{"since_cycle":2021}}\n'
            '{"kind":"relationship","id":3,"labels":["GUARDS"],"directed":true,'
            '"start_id":3,"end_id":3,"properties":{}}\n'
        )
        assert destination.read_text(encoding="utf-8") == expected
        assert summary == InteropSummary(nodes=4, relationships=3)

    def test_export_is_deterministic(self, populated: Path, tmp_path: Path) -> None:
        """Two exports of the same committed graph are byte-identical."""
        first = tmp_path / "first.jsonl"
        second = tmp_path / "second.jsonl"
        with Graph.open(populated) as graph:
            graph.export_jsonl(first)
            graph.export_jsonl(second)

        assert first.read_bytes() == second.read_bytes()

    def test_empty_graph(self, tmp_path: Path) -> None:
        """An empty graph exports a header-only snapshot."""
        destination = tmp_path / "empty.jsonl"
        with Graph.open(":memory:") as graph:
            summary = graph.export_jsonl(destination)

        assert summary == InteropSummary(nodes=0, relationships=0)
        assert destination.read_text(encoding="utf-8") == (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,"nodes":0,"relationships":0}\n'
        )

    def test_read_only_handle(self, populated: Path, tmp_path: Path) -> None:
        """A read-only handle can write a snapshot."""
        destination = tmp_path / "snapshot.jsonl"
        with Graph.open(populated, readonly=True) as graph:
            summary = graph.export_jsonl(destination)

        assert summary == InteropSummary(nodes=4, relationships=3)
        assert destination.exists()

    def test_active_transaction_is_refused(self, populated: Path, tmp_path: Path) -> None:
        """Export cannot run inside an explicit transaction."""
        destination = tmp_path / "snapshot.jsonl"
        with Graph.open(populated) as graph:
            active = graph.transaction().begin()
            with pytest.raises(TransactionError):
                graph.export_jsonl(destination)
            active.rollback()

        assert not destination.exists()

    def test_existing_destination_is_refused(self, populated: Path, tmp_path: Path) -> None:
        """An existing destination is left untouched without overwrite."""
        destination = tmp_path / "snapshot.jsonl"
        destination.write_text("keep me", encoding="utf-8")
        with Graph.open(populated) as graph, pytest.raises(ValidationError):
            graph.export_jsonl(destination)

        assert destination.read_text(encoding="utf-8") == "keep me"

    def test_explicit_overwrite(self, populated: Path, tmp_path: Path) -> None:
        """An explicit overwrite replaces the destination."""
        destination = tmp_path / "snapshot.jsonl"
        destination.write_text("old", encoding="utf-8")
        with Graph.open(populated) as graph:
            summary = graph.export_jsonl(destination, overwrite=True)

        assert summary == InteropSummary(nodes=4, relationships=3)
        assert destination.read_text(encoding="utf-8").startswith(
            '{"kind":"header","format":"pygrafito-jsonl"'
        )

    def test_live_database_path_is_refused(self, populated: Path) -> None:
        """The open database and its journal sidecars are never export targets."""
        with Graph.open(populated) as graph:
            with pytest.raises(ValidationError, match="open database"):
                graph.export_jsonl(populated)
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = populated.with_name(f"{populated.name}{suffix}")
                with pytest.raises(ValidationError, match="open database"):
                    graph.export_jsonl(sidecar, overwrite=True)

    def test_missing_parent_is_reported(self, populated: Path, tmp_path: Path) -> None:
        """A destination that cannot be written is a validation error."""
        destination = tmp_path / "missing" / "snapshot.jsonl"
        with Graph.open(populated) as graph, pytest.raises(ValidationError):
            graph.export_jsonl(destination)

        assert not destination.exists()

    def test_failed_export_keeps_existing_destination(
        self,
        populated: Path,
        tmp_path: Path,
    ) -> None:
        """A failure partway through an overwrite leaves the old file intact."""
        destination = tmp_path / "snapshot.jsonl"
        with Graph.open(populated) as graph:
            graph.export_jsonl(destination)
        baseline = destination.read_text(encoding="utf-8")

        connection = sqlite3.connect(populated)
        try:
            cursor = connection.execute("INSERT INTO nodes (props) VALUES ('{}')")
            node_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO node_labels (node_id, label) VALUES (?, '')",
                (node_id,),
            )
            connection.commit()
        finally:
            connection.close()

        with Graph.open(populated) as graph, pytest.raises(ValidationError):
            graph.export_jsonl(destination, overwrite=True)

        assert destination.read_text(encoding="utf-8") == baseline
        temporary = tmp_path / f".{destination.name}.{os.getpid()}.tmp"
        assert not temporary.exists()

    def test_closed_handle(self, tmp_path: Path) -> None:
        """A closed handle cannot export."""
        graph = Graph.open(":memory:")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.export_jsonl(tmp_path / "snapshot.jsonl")

    def test_overwrite_must_be_boolean(self, populated: Path, tmp_path: Path) -> None:
        """The overwrite flag is validated at runtime."""
        with (
            Graph.open(populated) as graph,
            pytest.raises(
                ValidationError,
                match="overwrite must be a boolean",
            ),
        ):
            graph.export_jsonl(
                tmp_path / "snapshot.jsonl",
                overwrite=typing.cast(bool, 1),
            )

    def test_snapshot_contains_data_only(self, populated: Path, tmp_path: Path) -> None:
        """Indexes and constraints are not written to a snapshot."""
        destination = tmp_path / "snapshot.jsonl"
        with Graph.open(populated) as graph:
            graph.create_node_index("designation")
            graph.create_node_uniqueness_constraint("Program", "designation")
            graph.export_jsonl(destination)

        kinds = [
            json.loads(line)["kind"]
            for line in destination.read_text(encoding="utf-8").splitlines()
        ]
        assert kinds[0] == "header"
        assert set(kinds[1:]) == {"node", "relationship"}
        text = destination.read_text(encoding="utf-8").lower()
        assert "constraint" not in text
        assert "index" not in text
