# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for JSONL snapshot restore."""

import typing
from pathlib import Path

import pytest

from pygrafito import (
    ConstraintViolationError,
    Graph,
    GraphClosedError,
    InteropSummary,
    ReadOnlyError,
    TransactionError,
    ValidationError,
)


class Fixtures:
    """Build the themed graph and snapshot used by restore tests."""

    @staticmethod
    def populate(graph: Graph) -> None:
        """Create the canonical TRON graph.

        Parameters
        ----------
        graph : Graph
            Graph to populate.
        """
        kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        quorra = graph.add_node("Program", "ISO", designation="Quorra", cycles=37)
        tron = graph.add_node("Program", designation="Tron", cycles=40)
        graph.add_node(cycles=37)
        graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
        graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2021)
        graph.add_relationship(tron, "GUARDS", tron)

    @staticmethod
    def snapshot(tmp_path: Path) -> Path:
        """Export the canonical graph and return the snapshot path.

        Parameters
        ----------
        tmp_path : Path
            Temporary directory.

        Returns
        -------
        Path
            Written snapshot.
        """
        source = tmp_path / "source.db"
        destination = tmp_path / "snapshot.jsonl"
        with Graph.open(source) as graph:
            Fixtures.populate(graph)
            graph.export_jsonl(destination)
        return destination


class TestRestore:
    """Verify round-trip, replacement, and failure isolation."""

    def test_round_trip(self, tmp_path: Path) -> None:
        """A snapshot restores labels, types, endpoints, and properties."""
        snapshot = Fixtures.snapshot(tmp_path)
        with Graph.open(":memory:") as graph:
            summary = graph.restore_jsonl(snapshot)

            assert summary == InteropSummary(nodes=4, relationships=3)
            nodes = list(graph.find_nodes())
            by_designation = {
                str(node["designation"]): node for node in nodes if "designation" in node
            }
            assert set(by_designation) == {"Kevin Flynn", "Quorra", "Tron"}
            assert by_designation["Quorra"].labels == frozenset({"Program", "ISO"})
            assert by_designation["Kevin Flynn"]["cycles"] == 36
            assert any(not node.labels for node in nodes)

            relationships = list(graph.find_relationships())
            assert len(relationships) == 3
            assert {relationship.labels for relationship in relationships} == {
                ("ALLIES_WITH",),
                ("GUARDS",),
            }
            assert all(relationship.directed for relationship in relationships)
            self_loop = next(
                relationship for relationship in relationships if relationship.labels == ("GUARDS",)
            )
            assert self_loop.start_id == self_loop.end_id
            assert graph.node(self_loop.start_id)["designation"] == "Tron"

    def test_empty_snapshot(self, tmp_path: Path) -> None:
        """A header-only snapshot restores an empty graph."""
        source = tmp_path / "empty.db"
        destination = tmp_path / "empty.jsonl"
        with Graph.open(source) as graph:
            graph.export_jsonl(destination)
        with Graph.open(":memory:") as graph:
            summary = graph.restore_jsonl(destination)
            assert summary == InteropSummary(nodes=0, relationships=0)
            assert list(graph.find_nodes()) == []

    def test_version_one_snapshot_is_refused(self, tmp_path: Path) -> None:
        """A version 1 snapshot is not converted."""
        destination = tmp_path / "old.jsonl"
        destination.write_text(
            '{"kind":"header","format":"pygrafito-jsonl","version":1,'
            '"nodes":0,"relationships":0}\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="unsupported snapshot version 1; expected 2",
            ),
        ):
            graph.restore_jsonl(destination)

    def test_non_empty_target_is_refused(self, tmp_path: Path) -> None:
        """Without replace, a populated target is left alone."""
        snapshot = Fixtures.snapshot(tmp_path)
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Rinzler")
            with pytest.raises(ValidationError, match="not empty"):
                graph.restore_jsonl(snapshot)
            assert [node["designation"] for node in graph.find_nodes()] == ["Rinzler"]

    def test_atomic_replace(self, tmp_path: Path) -> None:
        """Replace removes the old graph and loads the snapshot."""
        snapshot = Fixtures.snapshot(tmp_path)
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Rinzler")
            summary = graph.restore_jsonl(snapshot, replace=True)
            assert summary == InteropSummary(nodes=4, relationships=3)
            designations = {
                node["designation"] for node in graph.find_nodes() if "designation" in node
            }
            assert "Rinzler" not in designations
            assert {"Kevin Flynn", "Quorra", "Tron"} <= designations

    def test_replace_rolls_back(self, tmp_path: Path) -> None:
        """A failed replace leaves the original graph intact."""
        snapshot = Fixtures.snapshot(tmp_path)
        lines = snapshot.read_text(encoding="utf-8").splitlines()
        lines[-1] = lines[-1].replace('"start_id":3', '"start_id":99', 1)
        invalid = tmp_path / "invalid.jsonl"
        invalid.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Rinzler")
            with pytest.raises(ValidationError, match="unknown node id"):
                graph.restore_jsonl(invalid, replace=True)
            assert [node["designation"] for node in graph.find_nodes()] == ["Rinzler"]

    def test_read_only_handle_is_refused(self, tmp_path: Path) -> None:
        """A read-only handle is refused before the snapshot is opened."""
        target = tmp_path / "target.db"
        with Graph.open(target) as graph:
            graph.add_node("Program", designation="Tron")
        with Graph.open(target, readonly=True) as graph, pytest.raises(ReadOnlyError):
            graph.restore_jsonl(tmp_path / "missing.jsonl")

    def test_active_transaction_is_refused(self, tmp_path: Path) -> None:
        """Restore cannot run inside an explicit transaction."""
        with Graph.open(":memory:") as graph:
            active = graph.transaction().begin()
            with pytest.raises(TransactionError):
                graph.restore_jsonl(tmp_path / "missing.jsonl")
            active.rollback()

    def test_closed_handle(self, tmp_path: Path) -> None:
        """A closed handle cannot restore."""
        graph = Graph.open(":memory:")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.restore_jsonl(tmp_path / "snapshot.jsonl")

    def test_replace_must_be_boolean(self, tmp_path: Path) -> None:
        """The replace flag is validated at runtime."""
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="replace must be a boolean",
            ),
        ):
            graph.restore_jsonl(
                tmp_path / "snapshot.jsonl",
                replace=typing.cast(bool, 1),
            )

    def test_missing_file(self, tmp_path: Path) -> None:
        """A missing snapshot is a validation error."""
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="could not read snapshot",
            ),
        ):
            graph.restore_jsonl(tmp_path / "missing.jsonl")

    def test_malformed_header(self, tmp_path: Path) -> None:
        """A first record that is not a header is refused."""
        snapshot = tmp_path / "bad.jsonl"
        snapshot.write_text(
            '{"kind":"node","id":1,"labels":[],"properties":{}}\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="line 1",
            ),
        ):
            graph.restore_jsonl(snapshot)
        with Graph.open(":memory:") as graph:
            assert list(graph.find_nodes()) == []

    def test_count_mismatch(self, tmp_path: Path) -> None:
        """A truncated node phase is rejected at EOF."""
        snapshot = tmp_path / "short.jsonl"
        snapshot.write_text(
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":2,"relationships":0}\n'
            '{"kind":"node","id":1,"labels":["Program"],"properties":{}}\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="header declares 2 nodes",
            ),
        ):
            graph.restore_jsonl(snapshot)
        with Graph.open(":memory:") as graph:
            assert list(graph.find_nodes()) == []

    def test_truncated_record(self, tmp_path: Path) -> None:
        """An incomplete final record is rejected with its line number."""
        snapshot = tmp_path / "truncated.jsonl"
        snapshot.write_text(
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":1,"relationships":0}\n'
            '{"kind":"node"\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="line 2: invalid JSON",
            ),
        ):
            graph.restore_jsonl(snapshot)

    def test_unknown_endpoint(self, tmp_path: Path) -> None:
        """A relationship must reference a node from the node phase."""
        snapshot = tmp_path / "endpoint.jsonl"
        snapshot.write_text(
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":1,"relationships":1}\n'
            '{"kind":"node","id":1,"labels":["Program"],"properties":{}}\n'
            '{"kind":"relationship","id":1,"labels":["ALLIES_WITH"],"directed":true,'
            '"start_id":1,"end_id":2,"properties":{}}\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="unknown node id 2",
            ),
        ):
            graph.restore_jsonl(snapshot)

    def test_duplicate_node_id(self, tmp_path: Path) -> None:
        """Two node records cannot share a source id."""
        snapshot = tmp_path / "duplicate.jsonl"
        snapshot.write_text(
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":2,"relationships":0}\n'
            '{"kind":"node","id":1,"labels":["Program"],"properties":{}}\n'
            '{"kind":"node","id":1,"labels":["Program"],"properties":{}}\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="duplicate node id 1",
            ),
        ):
            graph.restore_jsonl(snapshot)

    def test_phase_violation(self, tmp_path: Path) -> None:
        """A node record after a relationship record is rejected."""
        snapshot = tmp_path / "phase.jsonl"
        snapshot.write_text(
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":2,"relationships":1}\n'
            '{"kind":"node","id":1,"labels":["Program"],"properties":{}}\n'
            '{"kind":"relationship","id":1,"labels":["GUARDS"],"directed":true,'
            '"start_id":1,"end_id":1,"properties":{}}\n'
            '{"kind":"node","id":2,"labels":["Program"],"properties":{}}\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="node records must precede",
            ),
        ):
            graph.restore_jsonl(snapshot)

    def test_line_number(self, tmp_path: Path) -> None:
        """An invalid record reports its one-based line."""
        snapshot = tmp_path / "line.jsonl"
        snapshot.write_text(
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":2,"relationships":0}\n'
            '{"kind":"node","id":1,"labels":["Program"],"properties":{}}\n'
            '{"kind":"node","id":2,"labels":["Program"],"properties":{},'
            '"extra":true}\n',
            encoding="utf-8",
        )
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match="line 3: unknown field",
            ),
        ):
            graph.restore_jsonl(snapshot)

    def test_constraint_violation_rolls_back(self, tmp_path: Path) -> None:
        """A uniqueness violation leaves the target empty."""
        source = tmp_path / "duplicate-source.db"
        snapshot = tmp_path / "duplicate.jsonl"
        with Graph.open(source) as graph:
            graph.add_node("Program", designation="Tron")
            graph.add_node("Program", designation="Tron")
            graph.export_jsonl(snapshot)

        with Graph.open(":memory:") as graph:
            graph.create_node_uniqueness_constraint("Program", "designation")
            with pytest.raises(ConstraintViolationError):
                graph.restore_jsonl(snapshot)
            assert list(graph.find_nodes("Program")) == []

    def test_preserves_target_schema(self, tmp_path: Path) -> None:
        """Indexes and constraints stay in place through a restore."""
        snapshot = Fixtures.snapshot(tmp_path)
        with Graph.open(":memory:") as graph:
            index = graph.create_node_index("cycles")
            constraint = graph.create_node_uniqueness_constraint(
                "Program",
                "designation",
            )
            graph.restore_jsonl(snapshot)
            assert graph.indexes() == (index,)
            assert graph.constraints() == (constraint,)

    def test_sparse_ids_are_remapped(self, tmp_path: Path) -> None:
        """Restore assigns dense ids and rewrites relationship endpoints."""
        source = tmp_path / "sparse.db"
        snapshot = tmp_path / "sparse.jsonl"
        with Graph.open(source) as graph:
            tron = graph.add_node("Program", designation="Tron")
            removable = graph.add_node("Program", designation="Clu")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(tron, "ALLIES_WITH", quorra)
            graph.delete(removable)
            graph.export_jsonl(snapshot)

        with Graph.open(":memory:") as graph:
            graph.restore_jsonl(snapshot)
            nodes = list(graph.find_nodes())
            assert [node.id for node in nodes] == [1, 2]
            assert [node["designation"] for node in nodes] == ["Tron", "Quorra"]
            relationship = next(iter(graph.find_relationships()))
            assert relationship.start_id == 1
            assert relationship.end_id == 2

    def test_re_export_is_stable(self, tmp_path: Path) -> None:
        """A dense snapshot round-trips to byte-identical output."""
        snapshot = Fixtures.snapshot(tmp_path)
        second = tmp_path / "second.jsonl"
        with Graph.open(":memory:") as graph:
            graph.restore_jsonl(snapshot)
            graph.export_jsonl(second)
        assert snapshot.read_bytes() == second.read_bytes()
