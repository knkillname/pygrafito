# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Verify the example datasets, builder, front door, and tours."""

import json
import os
import pathlib
import re
import subprocess
import sys
import typing

import pytest
from benchmarks.run import Synthetic as BenchmarkSynthetic
from examples import Dataset
from examples.__main__ import Main
from examples.algorithms.direction import DirectionDemo
from examples.algorithms.reachability import Reachability
from examples.algorithms.scaling import Scaling
from examples.algorithms.shortest_path import ShortestPath
from examples.algorithms.trails_vs_walks import TrailsVersusWalks
from examples.analysis.aggregate_by_source import AggregateBySource
from examples.analysis.export_report import ExportReport
from examples.analysis.import_csv import ImportCsv
from examples.analysis.rank_by_degree import RankByDegree
from examples.analysis.sql_views import SqlViews
from examples.build import Build
from examples.extract.screenplay import (
    ExtractionError,
    PdfTranscript,
    Screenplay,
    Transcript,
)
from examples.extract.screenplay import Main as ExtractMain
from examples.support.dataset import DatasetError, Synthetic

from pygrafito import Graph
from tests.cli.support import Harness


class TestDatasetValidation:
    """Reject malformed datasets before creating any element."""

    @staticmethod
    def document(
        nodes: list[dict[str, object]],
        relationships: list[dict[str, object]],
    ) -> dict[str, object]:
        """Return a minimal document payload.

        Parameters
        ----------
        nodes : list[dict[str, object]]
            Node declarations.
        relationships : list[dict[str, object]]
            Relationship declarations.

        Returns
        -------
        dict[str, object]
            Decoded document.
        """
        return {"name": "test", "nodes": nodes, "relationships": relationships}

    def test_duplicate_handle_is_rejected(self) -> None:
        """Reject two nodes with the same handle."""
        payload = self.document(
            [
                {"key": "tron", "labels": ["Program"]},
                {"key": "tron", "labels": ["Program"]},
            ],
            [],
        )
        with pytest.raises(DatasetError, match="duplicate node handle: tron"):
            Dataset.parse(payload)

    def test_unknown_endpoint_is_rejected(self) -> None:
        """Reject a relationship that names a missing node."""
        payload = self.document(
            [{"key": "tron", "labels": ["Program"]}],
            [{"from": "tron", "to": "mcp", "labels": ["OPPOSES"]}],
        )
        with pytest.raises(DatasetError, match="unknown endpoint: mcp"):
            Dataset.parse(payload)

    def test_non_identifier_property_key_is_rejected(self) -> None:
        """Reject a property key that cannot become a keyword argument."""
        payload = self.document(
            [{"key": "tron", "labels": ["Program"], "properties": {"a.b": 1}}],
            [],
        )
        with pytest.raises(DatasetError, match="not an identifier"):
            Dataset.parse(payload)

    @pytest.mark.parametrize(
        "value",
        [None, {"nested": True}, [[1, 2]], [1, "two"], [True, 1]],
    )
    def test_invalid_property_values_are_rejected(self, value: object) -> None:
        """Reject unsupported property values.

        Parameters
        ----------
        value : object
            Invalid value.
        """
        payload = self.document(
            [{"key": "tron", "labels": ["Program"], "properties": {"value": value}}],
            [],
        )
        with pytest.raises(DatasetError):
            Dataset.parse(payload)

    def test_non_finite_float_is_rejected(self) -> None:
        """Reject NaN and infinity."""
        payload = self.document(
            [{"key": "tron", "labels": ["Program"], "properties": {"version": float("nan")}}],
            [],
        )
        with pytest.raises(DatasetError, match="must be finite"):
            Dataset.parse(payload)

    def test_merge_conflict_is_rejected(self) -> None:
        """Reject a shared handle with conflicting property values."""
        first = Dataset.parse(
            self.document(
                [{"key": "tron", "labels": ["Program"], "properties": {"cycles": 40}}],
                [],
            )
        )
        second = Dataset.parse(
            self.document(
                [{"key": "tron", "labels": ["Program"], "properties": {"cycles": 41}}],
                [],
            )
        )
        with pytest.raises(DatasetError, match="conflicting property 'cycles'"):
            Dataset.merge([first, second])

    def test_full_element_model_is_preserved(self) -> None:
        """Keep multi-label nodes and undirected multi-label edges."""
        document = Dataset.parse(
            self.document(
                [
                    {"key": "mcp", "labels": ["Program", "System"]},
                    {"key": "tron", "labels": ["Program"]},
                ],
                [
                    {
                        "from": "mcp",
                        "to": "tron",
                        "labels": ["OPPOSES", "MONITORS"],
                        "directed": False,
                    }
                ],
            )
        )
        with Graph.open(":memory:") as graph:
            Dataset.seed(document, graph)
            mcp = next(iter(graph.find_nodes("System")))
            assert mcp.labels == frozenset({"Program", "System"})
            relationship = next(iter(graph.find_relationships()))
            assert relationship.labels == ("MONITORS", "OPPOSES")
            assert relationship.directed is False


class TestCuratedDatasets:
    """Build the committed datasets and check their shape."""

    def test_grid_counts_and_shapes(self) -> None:
        """Build grid and check counts, provenance, and the element model."""
        document = Dataset.load("grid")
        with Graph.open(":memory:") as graph:
            summary = Dataset.seed(document, graph)
            assert summary.nodes == 78
            assert summary.relationships == 180
            mcp = next(iter(graph.find_nodes("System")))
            assert mcp.labels == frozenset({"Program", "System"})
            assert isinstance(mcp["sources"], list)
            alliance = next(iter(graph.find_relationships("TRUSTS")))
            assert alliance.directed is False
            assert alliance.labels == ("ALLIES_WITH", "TRUSTS")

    def test_all_merges_by_handle(self) -> None:
        """Build all and check merged nodes and deduplicated relationships."""
        with Graph.open(":memory:") as graph:
            summary = Dataset.seed(Dataset.load("all"), graph)
            assert summary.nodes == 78
            assert summary.relationships == 290
            assert len(list(graph.find_nodes("User", designation="Kevin Flynn"))) == 1

    def test_snapshot_is_deterministic(self, tmp_path: pathlib.Path) -> None:
        """Compare snapshots from two separate processes.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        root = pathlib.Path(__file__).resolve().parents[1]
        first = tmp_path / "first.jsonl"
        second = tmp_path / "second.jsonl"
        for destination, seed in ((first, "1"), (second, "987654")):
            environment = {
                **os.environ,
                "PYTHONHASHSEED": seed,
                "PYTHONPATH": str(root),
            }
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "examples",
                    "build",
                    "grid",
                    "--output",
                    str(destination),
                    "--format",
                    "jsonl",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
        assert first.read_bytes() == second.read_bytes()
        committed = root / "examples" / "data" / "grid.jsonl"
        assert first.read_bytes() == committed.read_bytes()

    def test_committed_snapshot_matches_a_fresh_build(self, tmp_path: pathlib.Path) -> None:
        """Keep the committed snapshot equal to a fresh build.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        rebuilt = tmp_path / "grid.jsonl"
        Build.build("grid", output=rebuilt, format="jsonl")
        committed = pathlib.Path(__file__).resolve().parents[1] / "examples" / "data" / "grid.jsonl"
        assert rebuilt.read_bytes() == committed.read_bytes()

    def test_snapshot_restores(self, tmp_path: pathlib.Path) -> None:
        """Restore a snapshot and compare labels, direction, and counts.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        snapshot = tmp_path / "grid.jsonl"
        Build.build("grid", output=snapshot, format="jsonl")
        with Graph.open(":memory:") as graph:
            summary = graph.restore_jsonl(snapshot)
            assert summary.nodes == 78
            assert summary.relationships == 180
            assert next(iter(graph.find_relationships("TRUSTS"))).directed is False

    def test_database_applies_schema(self, tmp_path: pathlib.Path) -> None:
        """Build a database and check its indexes and constraint.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        database = tmp_path / "grid.db"
        Build.build("grid", output=database)
        with Graph.open(database) as graph:
            assert len(list(graph.find_nodes())) == 78
            assert {index.key for index in graph.indexes()} == {"designation", "cycles"}
            assert [(item.scope, item.key) for item in graph.constraints()] == [
                ("User", "designation")
            ]


class TestFrontDoor:
    """Exercise the catalog and build actions."""

    def test_catalog_lists_datasets_and_lanes(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Print the catalog when no action is given.

        Parameters
        ----------
        capsys : pytest.CaptureFixture[str]
            Capture fixture.
        """
        assert Main.run([]) == 0
        output = capsys.readouterr().out
        assert "Datasets:" in output
        assert "tours/" in output
        assert "python -m examples build grid" in output

    @pytest.mark.parametrize("name", ["grid", "cast", "places", "all", "synthetic"])
    def test_every_dataset_builds_in_memory(
        self,
        name: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Build every catalogued dataset.

        Parameters
        ----------
        name : str
            Dataset name.
        capsys : pytest.CaptureFixture[str]
            Capture fixture.
        """
        assert Main.run(["build", name]) == 0
        output = capsys.readouterr().out
        assert f"built {name}" in output

    @pytest.mark.parametrize("format", ["db", "jsonl"])
    def test_both_output_formats(
        self,
        format: str,
        tmp_path: pathlib.Path,
    ) -> None:
        """Write both supported output formats.

        Parameters
        ----------
        format : str
            Output format.
        tmp_path : pathlib.Path
            Temporary directory.
        """
        destination = tmp_path / f"grid.{format}"
        result = Build.build("grid", output=destination, format=format)
        assert result.path == destination
        assert destination.stat().st_size > 0

    def test_invalid_dataset_is_rejected(self) -> None:
        """Reject an unknown dataset name."""
        with pytest.raises(DatasetError, match="unknown dataset"):
            Build.build("unknown")

    def test_invalid_format_is_rejected(self) -> None:
        """Reject an unknown output format."""
        with pytest.raises(DatasetError, match="unknown output format"):
            Build.build("grid", format="yaml")

    def test_overwrite_replaces_a_database(self, tmp_path: pathlib.Path) -> None:
        """Replace an existing database instead of appending.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        destination = tmp_path / "grid.db"
        Build.build("grid", output=destination)
        Build.build(
            "synthetic",
            output=destination,
            nodes=10,
            relationships=20,
            overwrite=True,
        )
        with Graph.open(destination) as graph:
            assert len(list(graph.find_nodes())) == 10
            assert len(list(graph.find_relationships())) == 20

    def test_existing_output_is_rejected(self, tmp_path: pathlib.Path) -> None:
        """Reject an existing destination without overwrite.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        destination = tmp_path / "grid.db"
        destination.write_text("occupied", encoding="utf-8")
        with pytest.raises(DatasetError, match="output already exists"):
            Build.build("grid", output=destination)


class TestSynthetic:
    """Check the seeded scale fixture."""

    def test_same_seed_is_deterministic(self) -> None:
        """Produce identical nodes and relationships for the same seed."""
        first = self._build(120, 400, 7)
        second = self._build(120, 400, 7)
        assert first == second

    def test_counts_are_honored(self) -> None:
        """Create the requested number of nodes and relationships."""
        with Graph.open(":memory:") as graph:
            created = Synthetic(120, 400, 3).build(graph)
            assert len(created) == 120
            assert len(list(graph.find_relationships())) == 400

    @staticmethod
    def _build(
        nodes: int,
        relationships: int,
        seed: int,
    ) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
        """Build one synthetic graph and return its stable shape.

        Parameters
        ----------
        nodes : int
            Node count.
        relationships : int
            Relationship count.
        seed : int
            Vocabulary seed.

        Returns
        -------
        tuple[list[tuple[object, ...]], list[tuple[object, ...]]]
            Node and relationship descriptions in id order.
        """
        with Graph.open(":memory:") as graph:
            created = Synthetic(nodes, relationships, seed).build(graph)
            return (
                [
                    (
                        node.id,
                        tuple(sorted(node.labels)),
                        json.dumps(dict(node.properties), sort_keys=True),
                    )
                    for node in created
                ],
                [
                    (
                        relationship.id,
                        relationship.start_id,
                        relationship.end_id,
                        relationship.labels,
                        relationship.directed,
                        json.dumps(dict(relationship.properties), sort_keys=True),
                    )
                    for relationship in graph.find_relationships()
                ],
            )


class TestTours:
    """Run and classify every shell tour."""

    DIRECTORY: typing.ClassVar[pathlib.Path] = (
        pathlib.Path(__file__).resolve().parents[1] / "examples" / "tours"
    )

    def test_every_tour_has_a_catalog_entry(self) -> None:
        """Require one catalog row per tour file."""
        catalog = (self.DIRECTORY / "README.md").read_text(encoding="utf-8")
        for path in sorted(self.DIRECTORY.glob("*.gql")):
            assert f"`{path.name}`" in catalog

    TIERS: typing.ClassVar[tuple[str, ...]] = (
        "canonical GQL",
        "synthetic alias",
        "compatibility",
        "pygrafito extension",
        "out of profile",
    )

    def test_extension_constructs_are_labelled(self) -> None:
        """Require every catalog row to declare tier, section, and owner."""
        catalog = (self.DIRECTORY / "README.md").read_text(encoding="utf-8")
        rows: dict[str, list[str]] = {}
        for line in catalog.splitlines():
            if not line.startswith("| `"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 5:
                continue
            rows[cells[0].strip("`")] = cells
        for path in sorted(self.DIRECTORY.glob("*.gql")):
            assert path.name in rows, path.name
            cells = rows[path.name]
            tier = cells[2].lower()
            assert any(name in tier for name in self.TIERS), path.name
            assert cells[3], path.name
            assert cells[4], path.name
        assert "pygrafito extension" in catalog
        for construct in ("MERGE", "WITH", "type()"):
            assert construct in catalog

    def test_target_only_syntax_is_absent(self) -> None:
        """Reject syntax that the current release cannot execute."""
        forbidden = re.compile(
            r"\b(?:LET|NEXT)\b|\bGROUP\s+BY\b|\bRETURN\s+NO\s+BINDINGS\b|"
            r"\bMATCH\s+(?:WALK|TRAIL|SIMPLE|ACYCLIC)\b|"
            r"\{\s*\d|<~|~>|<->",
            flags=re.MULTILINE,
        )
        for path in sorted(self.DIRECTORY.glob("*.gql")):
            source = "\n".join(
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if not line.strip().startswith("//")
            )
            assert not forbidden.search(source), path.name

    def test_every_tour_runs(self, tmp_path: pathlib.Path) -> None:
        """Execute every tour against a freshly built grid database.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        database = tmp_path / "grid.db"
        Build.build("grid", output=database)
        for path in sorted(self.DIRECTORY.glob("*.gql")):
            harness = Harness(database)
            try:
                code, _output, error = harness.run(path.read_text(encoding="utf-8"))
            finally:
                harness.close()
            assert code == 0, f"{path.name}: {error}"


class TestAnalysis:
    """Exercise the analysis lane entry points."""

    def test_rank_by_degree_returns_programs(self) -> None:
        """Rank the cast programs by weighted degree."""
        rows = RankByDegree.run(5)
        assert len(rows) == 5
        assert rows[0].name == "Ares"
        assert rows[0].degree > rows[-1].degree

    def test_aggregate_by_source_counts(self) -> None:
        """Count the 1981 users and programs."""
        rows = {(row.source, row.label): row.count for row in AggregateBySource.run()}
        assert rows[("tron-1981", "User")] == 5
        assert rows[("tron-1981", "Program")] == 9
        assert rows[("ares-2025", "User")] == 13

    def test_import_csv_converts_integers(self) -> None:
        """Import the bundled CSV and check typed values."""
        result = ImportCsv.run()
        assert result.summary.rows == 3
        assert result.summary.mutations.created_nodes == 3
        assert result.programs == (("Dumont", 39), ("Ram", 36), ("Yori", 37))

    def test_sql_views_are_readable(self) -> None:
        """Read node and relationship rows through SQLite."""
        snapshot = SqlViews.run()
        assert snapshot.nodes == 78
        assert snapshot.relationships == 180
        assert snapshot.node_labels == ("User",)
        assert snapshot.relationship_labels == ("APPEARS_IN",)
        assert snapshot.directed is True

    def test_export_report_writes_both_files(self, tmp_path: pathlib.Path) -> None:
        """Write a CSV report and a snapshot.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        report = ExportReport.run(tmp_path)
        assert report.csv_path.exists()
        assert report.snapshot_path.exists()
        lines = report.csv_path.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "designation,cycles"
        assert ("Tron", 40) in report.rows
        header = json.loads(report.snapshot_path.read_text(encoding="utf-8").splitlines()[0])
        assert header["nodes"] == 78
        assert header["relationships"] == 180


class TestAlgorithms:
    """Exercise the algorithm lane entry points."""

    def test_reachability_reports_depths_and_route(self) -> None:
        """Compare breadth-first depths with the shortest route."""
        report = Reachability.run()
        depths = dict(report.reachable)
        assert depths["The Grid"] == 1
        assert depths["I/O Tower"] == 2
        assert report.route == ("Real World", "The Grid", "I/O Tower")
        assert report.length == 2

    def test_trails_are_relationship_unique(self) -> None:
        """Enumerate one trail around a directed cycle."""
        report = TrailsVersusWalks.run()
        assert report.trails == 1
        assert report.lengths == (3,)
        module = (
            pathlib.Path(__file__).resolve().parents[1]
            / "examples"
            / "algorithms"
            / "trails_vs_walks.py"
        ).read_text(encoding="utf-8")
        assert "target" in module
        assert "gated" in module
        assert "WALK is implemented" not in module

    def test_shortest_path_uses_bidirectional_bfs(self) -> None:
        """Find a shortest route through the places network."""
        report = ShortestPath.run()
        assert report.length == 2
        assert report.route[0] == "Flynn's Arcade"
        assert report.route[-1] == "I/O Tower"
        assert report.routes >= 1

    def test_direction_changes_reachability(self) -> None:
        """Compare outgoing, incoming, and undirected traversal."""
        report = DirectionDemo.run()
        assert report.created_out == ("Clu",)
        assert report.created_in == ("Kevin Flynn",)
        assert report.created_out_from_target == ()
        assert "Tron" in report.alliance_from_ram

    def test_scaling_reports_counts_and_time(self) -> None:
        """Measure a small synthetic traversal."""
        row = Scaling.run(nodes=120, seed=1, depth=2)
        assert row.nodes == 120
        assert row.relationships == 360
        assert row.reached > 0
        assert row.milliseconds >= 0


class TestBenchmarkFixture:
    """Keep the benchmark on the shared synthetic generator."""

    def test_benchmark_imports_the_shared_generator(self) -> None:
        """Use the same Synthetic class in the benchmark and the examples."""
        assert BenchmarkSynthetic is Synthetic


class TestExtraction:
    """Exercise the local-only extractor with an invented fixture."""

    FIXTURE: typing.ClassVar[pathlib.Path] = (
        pathlib.Path(__file__).resolve().parent / "fixtures" / "mini_screenplay.txt"
    )

    def test_screenplay_extracts_scene_aggregates(self) -> None:
        """Read cues, scenes, turns, and place transitions."""
        extraction = Screenplay.extract(self.FIXTURE)
        assert extraction.characters == ("alpha", "beta", "gamma")
        assert (("alpha", "beta"), 1) in {
            ((pair.source, pair.target), pair.weight) for pair in extraction.co_occurrence
        }
        assert extraction.places == ("video-arcade", "game-grid", "io-tower")
        transitions = {
            (transition.source, transition.target) for transition in extraction.transitions
        }
        assert transitions == {
            ("video-arcade", "game-grid"),
            ("game-grid", "io-tower"),
        }

    def test_output_contains_no_dialogue(self) -> None:
        """Keep dialogue and action text out of the aggregate documents."""
        extraction = Screenplay.extract(self.FIXTURE)
        payload = json.dumps(extraction.cast_document()) + json.dumps(extraction.places_document())
        assert "We should go" not in payload
        assert "Ready?" not in payload
        assert "We made it" not in payload

    def test_missing_file_is_rejected(self, tmp_path: pathlib.Path) -> None:
        """Reject a missing screenplay path.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        with pytest.raises(ExtractionError, match="does not exist"):
            Screenplay.extract(tmp_path / "missing.txt")

    def test_transcript_extracts_speaker_turns(self, tmp_path: pathlib.Path) -> None:
        """Read speaker-prefixed transcript lines.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        source = tmp_path / "transcript.txt"
        source.write_text(
            "Tron: Ready?\nDumont: Always.\nTron: Then move.\n",
            encoding="utf-8",
        )
        extraction = Transcript.extract(source)
        assert extraction.characters == ("tron", "dumont")
        assert extraction.basis == "dialogue_window"
        assert any(pair.weight == 1 for pair in extraction.turns)

    def test_pdf_adapter_explains_missing_tool(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """Explain how to export text when pdftotext is unavailable.

        Parameters
        ----------
        monkeypatch : pytest.MonkeyPatch
            Fixture used to hide the tool.
        tmp_path : pathlib.Path
            Temporary directory.
        """
        source = tmp_path / "script.pdf"
        source.write_bytes(b"%PDF-1.7")
        monkeypatch.setattr("examples.extract.screenplay.shutil.which", lambda _name: None)
        with pytest.raises(ExtractionError, match="pdftotext is required"):
            PdfTranscript.extract(source)

    def test_cli_writes_places_document(self, tmp_path: pathlib.Path) -> None:
        """Write a places-shaped aggregate document.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        """
        destination = tmp_path / "places.json"
        assert (
            ExtractMain.run(
                [
                    str(self.FIXTURE),
                    "--format",
                    "screenplay",
                    "--kind",
                    "places",
                    "--output",
                    str(destination),
                ]
            )
            == 0
        )
        document = json.loads(destination.read_text(encoding="utf-8"))
        assert {node["key"] for node in document["nodes"]} == {
            "video-arcade",
            "game-grid",
            "io-tower",
        }
