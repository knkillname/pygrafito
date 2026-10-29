# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for CSV, JSONL, and in-memory import."""

import pathlib
from collections.abc import Iterator

import pytest

from pygrafito import (
    Graph,
    GraphClosedError,
    QueryExecutionError,
    ReadOnlyError,
    ValidationError,
)
from pygrafito.engine.importing import ImportRunner

MERGE = (
    "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
    "ON CREATE SET n.cycles = row.cycles"
)


class _ImportGraph:
    """Provide an in-memory graph for import tests."""

    @pytest.fixture
    def graph(self) -> Iterator[Graph]:
        with Graph.open(":memory:") as graph:
            yield graph

    @staticmethod
    def programs(graph: Graph) -> list[dict[str, object]]:
        return [dict(node) for node in graph.find_nodes("Program")]


class TestImportValidation(_ImportGraph):
    """Verify statement, row, and batch validation happens before writing."""

    def test_read_statement_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(ValidationError) as caught:
            graph.import_rows("MATCH (n) RETURN n", [{"designation": "Tron"}])
        assert "write clause" in str(caught.value)

    def test_statement_without_rows_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(ValidationError) as caught:
            graph.import_rows("CREATE (n:Program)", [{"designation": "Tron"}])
        assert "$rows" in str(caught.value)

    def test_invalid_batch_size_is_rejected(self, graph: Graph) -> None:
        for size in (0, -1):
            with pytest.raises(ValidationError):
                graph.import_rows(MERGE, [], batch_size=size)

    def test_non_mapping_row_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(ValidationError) as caught:
            graph.import_rows(MERGE, [{"designation": "Tron"}, "Clu"])  # type: ignore[list-item]
        assert "row 2" in str(caught.value)

    def test_non_string_key_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(ValidationError) as caught:
            graph.import_rows(MERGE, [{1: "Tron"}])  # type: ignore[dict-item]
        assert "keys must be strings" in str(caught.value)

    def test_read_only_graph_is_rejected(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            graph.add_node("Program", designation="Tron")
        with Graph.open(path, readonly=True) as graph, pytest.raises(ReadOnlyError):
            graph.import_rows(MERGE, [{"designation": "Clu"}])

    def test_closed_graph_is_rejected(self) -> None:
        graph = Graph.open(":memory:")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.import_rows(MERGE, [{"designation": "Tron"}])


class TestImportRows(_ImportGraph):
    """Verify in-memory row imports, batching, and summaries."""

    def test_imports_rows(self, graph: Graph) -> None:
        summary = graph.import_rows(
            MERGE,
            [
                {"designation": "Kevin Flynn", "cycles": 36},
                {"designation": "Quorra", "cycles": 37},
            ],
        )
        assert summary.rows == 2
        assert summary.batches == 1
        assert summary.mutations.created_nodes == 2
        assert summary.mutations.properties_set == 2
        assert len(self.programs(graph)) == 2

    def test_duplicate_keys_create_once(self, graph: Graph) -> None:
        summary = graph.import_rows(
            MERGE,
            [
                {"designation": "Marvin", "cycles": 1},
                {"designation": "Marvin", "cycles": 2},
            ],
        )
        assert summary.rows == 2
        assert summary.mutations.created_nodes == 1
        marvin = next(iter(graph.find_nodes("Program", designation="Marvin")))
        assert marvin["cycles"] == 1

    def test_batches_split_rows(self, graph: Graph) -> None:
        rows = [{"designation": f"Program {index}", "cycles": index} for index in range(5)]
        summary = graph.import_rows(MERGE, rows, batch_size=2)
        assert summary.rows == 5
        assert summary.batches == 3
        assert summary.mutations.created_nodes == 5

    def test_empty_input(self, graph: Graph) -> None:
        summary = graph.import_rows(MERGE, [])
        assert summary.rows == 0
        assert summary.batches == 0
        assert summary.mutations.created_nodes == 0

    def test_failure_reports_row_and_preserves_type(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError) as caught:
            graph.import_rows(
                "UNWIND $rows AS row CREATE (n:Program {designation: row.designation, "
                "cycles: row.cycles})",
                [
                    {"designation": "Tron", "cycles": 40},
                    {"designation": "Rinzler", "cycles": 41},
                    {"designation": "Clu", "cycles": {"bad": 1}},
                ],
                batch_size=10,
            )
        assert any("row 3" in note for note in caught.value.__notes__)
        assert any("batch 1" in note for note in caught.value.__notes__)
        assert graph.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"] == 0

    def test_non_atomic_failure_keeps_earlier_batches(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.import_rows(
                "UNWIND $rows AS row CREATE (n:Program {designation: row.designation, "
                "cycles: row.cycles})",
                [
                    {"designation": "Tron", "cycles": 40},
                    {"designation": "Clu", "cycles": {"bad": 1}},
                ],
                batch_size=1,
            )
        assert [item["designation"] for item in self.programs(graph)] == ["Tron"]

    def test_atomic_failure_rolls_back_everything(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.import_rows(
                "UNWIND $rows AS row CREATE (n:Program {designation: row.designation, "
                "cycles: row.cycles})",
                [
                    {"designation": "Tron", "cycles": 40},
                    {"designation": "Clu", "cycles": {"bad": 1}},
                ],
                batch_size=1,
                atomic=True,
            )
        assert self.programs(graph) == []


class TestImportFiles(_ImportGraph):
    """Verify CSV and JSONL readers through the file entry point."""

    def test_jsonl_preserves_types(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.jsonl"
        path.write_text(
            '{"designation": "Quorra", "cycles": 37, "active": true, "tags": ["ISO"]}\n',
            encoding="utf-8",
        )
        summary = graph.import_file(
            path,
            "UNWIND $rows AS row CREATE (n:Program {designation: row.designation, "
            "cycles: row.cycles, active: row.active, tags: row.tags})",
        )
        assert summary.rows == 1
        quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
        assert quorra["cycles"] == 37
        assert quorra["active"] is True
        assert quorra["tags"] == ["ISO"]

    def test_jsonl_skips_blank_lines(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.jsonl"
        path.write_text(
            '\n{"designation": "Tron", "cycles": 40}\n\n{"designation": "Clu", "cycles": 41}\n',
            encoding="utf-8",
        )
        summary = graph.import_file(path, MERGE)
        assert summary.rows == 2

    def test_jsonl_rejects_non_object_line(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.jsonl"
        path.write_text('["Tron"]\n', encoding="utf-8")
        with pytest.raises(ValidationError) as caught:
            graph.import_file(path, MERGE)
        assert "line 1" in str(caught.value)

    def test_jsonl_rejects_invalid_json(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.jsonl"
        path.write_text('{"designation": "Tron"\n', encoding="utf-8")
        with pytest.raises(ValidationError) as caught:
            graph.import_file(path, MERGE)
        assert "line 1" in str(caught.value)

    def test_jsonl_rejects_non_finite_numbers(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.jsonl"
        path.write_text('{"designation": "Tron", "cycles": NaN}\n', encoding="utf-8")
        with pytest.raises(ValidationError) as caught:
            graph.import_file(path, MERGE)
        assert "NaN" in str(caught.value)

    def test_csv_values_are_strings(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.csv"
        path.write_text("designation,cycles\nQuorra,37\n", encoding="utf-8")
        graph.import_file(
            path,
            "UNWIND $rows AS row CREATE (n:Program {designation: row.designation, "
            "cycles: toInteger(row.cycles)})",
        )
        quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
        assert quorra["cycles"] == 37

    @pytest.mark.parametrize(
        ("newline", "expected"),
        [
            (b"\n", "line one\nline two"),
            (b"\r\n", "line one\r\nline two"),
        ],
    )
    def test_csv_quoted_field_preserves_newlines(
        self,
        graph: Graph,
        tmp_path: pathlib.Path,
        newline: bytes,
        expected: str,
    ) -> None:
        path = tmp_path / "grid.csv"
        path.write_bytes(
            b"designation,notes"
            + newline
            + b'"Kevin Flynn","line one'
            + newline
            + b'line two"'
            + newline
        )
        graph.import_file(
            path,
            "UNWIND $rows AS row CREATE (n:Program {designation: row.designation, "
            "notes: row.notes})",
        )
        node = next(iter(graph.find_nodes("Program", designation="Kevin Flynn")))
        assert node["notes"] == expected

    def test_csv_header_only(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.csv"
        path.write_text("designation,cycles\n", encoding="utf-8")
        summary = graph.import_file(path, MERGE)
        assert summary.rows == 0

    def test_csv_missing_header(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.csv"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ValidationError) as caught:
            graph.import_file(path, MERGE)
        assert "header" in str(caught.value)

    def test_csv_duplicate_header(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.csv"
        path.write_text("designation,designation\nTron,Tron\n", encoding="utf-8")
        with pytest.raises(ValidationError) as caught:
            graph.import_file(path, MERGE)
        assert "unique" in str(caught.value)

    def test_csv_field_count_mismatch(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.csv"
        path.write_text("designation,cycles\nTron,40,extra\n", encoding="utf-8")
        with pytest.raises(ValidationError) as caught:
            graph.import_file(path, MERGE)
        assert "row 1" in str(caught.value)

    def test_explicit_format_overrides_suffix(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.txt"
        path.write_text("designation,cycles\nTron,40\n", encoding="utf-8")
        summary = graph.import_file(path, MERGE, format="csv")
        assert summary.rows == 1

    def test_ndjson_suffix(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.ndjson"
        path.write_text('{"designation": "Tron", "cycles": 40}\n', encoding="utf-8")
        summary = graph.import_file(path, MERGE)
        assert summary.rows == 1

    def test_unknown_suffix_is_rejected(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.data"
        path.write_text("designation,cycles\nTron,40\n", encoding="utf-8")
        with pytest.raises(ValidationError) as caught:
            graph.import_file(path, MERGE)
        assert "format" in str(caught.value)

    def test_invalid_explicit_format_is_rejected(
        self, graph: Graph, tmp_path: pathlib.Path
    ) -> None:
        path = tmp_path / "grid.csv"
        path.write_text("designation\nTron\n", encoding="utf-8")
        with pytest.raises(ValidationError):
            graph.import_file(path, MERGE, format="xml")

    def test_file_failure_reports_the_path(self, graph: Graph, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.jsonl"
        path.write_text(
            '{"designation": "Tron", "cycles": 40}\n{"designation": "Clu", "cycles": {"bad": 1}}\n',
            encoding="utf-8",
        )
        with pytest.raises(QueryExecutionError) as caught:
            graph.import_file(
                path,
                "UNWIND $rows AS row CREATE (n:Program {designation: row.designation, "
                "cycles: row.cycles})",
            )
        assert any(str(path) in note for note in caught.value.__notes__)
        assert any("row 2" in note for note in caught.value.__notes__)


def test_format_selection_is_case_insensitive() -> None:
    assert ImportRunner.select_format(pathlib.Path("grid.CSV"), None) == "csv"
    assert ImportRunner.select_format(pathlib.Path("grid.JSONL"), None) == "jsonl"
