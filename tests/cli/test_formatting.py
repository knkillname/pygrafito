# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for result rendering in every output mode."""

import csv
import io
import json

import pytest

from pygrafito import Graph, QueryResult, Row
from pygrafito.cli.formatting import OutputMode, ResultWriter, ValueFormatter
from pygrafito.engine.query.values import QueryValue


class _Rendering:
    """Build query results for rendering tests."""

    @staticmethod
    def result(
        columns: tuple[str, ...],
        rows: tuple[tuple[QueryValue, ...], ...],
    ) -> QueryResult:
        return QueryResult(
            columns=columns,
            rows=tuple(Row(columns=columns, row_values=row) for row in rows),
        )

    @classmethod
    def render(
        cls,
        result: QueryResult,
        mode: OutputMode,
        *,
        headers: bool = True,
    ) -> str:
        stream = io.StringIO()
        ResultWriter(mode, headers=headers).write(result, stream)
        return stream.getvalue()

    @staticmethod
    def display_width(text: str) -> int:
        return ValueFormatter.width(text)


class TestTable(_Rendering):
    """Verify the bordered table renderer."""

    def test_table_with_headers(self) -> None:
        result = self.result(("name", "cycles"), (("Kevin Flynn", 36),))
        expected = (
            "+-------------+--------+\n"
            "| name        | cycles |\n"
            "+-------------+--------+\n"
            "| Kevin Flynn | 36     |\n"
            "+-------------+--------+\n"
        )
        assert self.render(result, OutputMode.TABLE) == expected

    def test_headers_off(self) -> None:
        result = self.result(("name",), (("Tron",),))
        expected = "+------+\n| Tron |\n+------+\n"
        assert self.render(result, OutputMode.TABLE, headers=False) == expected

    def test_empty_result_with_headers(self) -> None:
        result = self.result(("name",), ())
        expected = "+------+\n| name |\n+------+\n"
        assert self.render(result, OutputMode.TABLE) == expected

    def test_empty_result_without_headers(self) -> None:
        result = self.result(("name",), ())
        assert self.render(result, OutputMode.TABLE, headers=False) == ""

    def test_control_characters_are_escaped(self) -> None:
        result = self.result(("note",), (("a\nb\tc",),))
        rendered = self.render(result, OutputMode.TABLE)
        assert "a\\nb\\tc" in rendered
        assert "a\nb" not in rendered

    def test_wide_characters_align(self) -> None:
        result = self.result(("name",), (("東京",), ("Tron",)))
        rendered = self.render(result, OutputMode.TABLE)
        widths = {
            self.display_width(line) for line in rendered.splitlines() if line.startswith("|")
        }
        assert len(widths) == 1

    def test_null_and_boolean(self) -> None:
        result = self.result(("value",), ((None,), (True,)))
        rendered = self.render(result, OutputMode.TABLE)
        assert "NULL" in rendered
        assert "true" in rendered

    def test_list_and_mapping_render_as_json(self) -> None:
        result = self.result(("value",), (([1, 2],),))
        assert "[1, 2]" in self.render(result, OutputMode.TABLE)


class TestLine(_Rendering):
    """Verify the line renderer."""

    def test_line_rows(self) -> None:
        result = self.result(("name", "cycles"), (("Quorra", 37), ("Tron", 40)))
        expected = "name = Quorra\ncycles = 37\n\nname = Tron\ncycles = 40\n"
        assert self.render(result, OutputMode.LINE) == expected

    def test_empty_line_result(self) -> None:
        result = self.result(("name",), ())
        assert self.render(result, OutputMode.LINE) == ""


class TestCsv(_Rendering):
    """Verify CSV quoting and round-tripping."""

    def test_header_and_rows(self) -> None:
        result = self.result(("name", "cycles"), (("Quorra", 37),))
        assert self.render(result, OutputMode.CSV) == "name,cycles\nQuorra,37\n"

    def test_headers_off(self) -> None:
        result = self.result(("name",), (("Quorra",),))
        assert self.render(result, OutputMode.CSV, headers=False) == "Quorra\n"

    def test_quoting_round_trip(self) -> None:
        value = 'a,b"c\nd'
        result = self.result(("note",), ((value,),))
        rendered = self.render(result, OutputMode.CSV)
        parsed = list(csv.reader(io.StringIO(rendered)))
        assert parsed == [["note"], [value]]

    def test_null_is_empty_field(self) -> None:
        result = self.result(("note",), ((None,),))
        rendered = self.render(result, OutputMode.CSV)
        assert list(csv.reader(io.StringIO(rendered))) == [["note"], [""]]

    def test_empty_result(self) -> None:
        result = self.result(("name",), ())
        assert self.render(result, OutputMode.CSV) == "name\n"


class TestJson(_Rendering):
    """Verify JSON and JSON-lines rendering."""

    def test_json_array_of_objects(self) -> None:
        result = self.result(("name", "cycles"), (("Quorra", 37),))
        payload = json.loads(self.render(result, OutputMode.JSON))
        assert payload == [{"name": "Quorra", "cycles": 37}]
        assert list(payload[0]) == ["name", "cycles"]

    def test_json_empty(self) -> None:
        result = self.result(("name",), ())
        assert json.loads(self.render(result, OutputMode.JSON)) == []

    def test_jsonl_one_object_per_line(self) -> None:
        result = self.result(("name", "cycles"), (("Quorra", 37), ("Tron", 40)))
        lines = self.render(result, OutputMode.JSONL).splitlines()
        assert [json.loads(line) for line in lines] == [
            {"name": "Quorra", "cycles": 37},
            {"name": "Tron", "cycles": 40},
        ]

    def test_json_null_and_boolean(self) -> None:
        result = self.result(("a", "b"), ((None, True),))
        payload = json.loads(self.render(result, OutputMode.JSON))
        assert payload == [{"a": None, "b": True}]


class TestEntities(_Rendering):
    """Verify graph entity rendering in text and JSON modes."""

    @pytest.fixture
    def entities(self) -> QueryResult:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn")
            graph.add_node("Program", designation="Quorra")
            graph.add_relationship(kevin, "ALLIES_WITH", 2, since_cycle=2020)
            result = graph.query(
                "MATCH p=(a:Program {designation: 'Kevin Flynn'})-[r:ALLIES_WITH]->(b) "
                "RETURN a, r, p"
            )
        return result

    def test_node_text(self, entities: QueryResult) -> None:
        rendered = self.render(entities, OutputMode.TABLE)
        assert '(:Program {id: 1, designation: "Kevin Flynn"})' in rendered

    def test_relationship_text(self, entities: QueryResult) -> None:
        rendered = self.render(entities, OutputMode.TABLE)
        assert "(1)-[:ALLIES_WITH {id: 1, since_cycle: 2020}]->(2)" in rendered

    def test_path_text(self, entities: QueryResult) -> None:
        rendered = self.render(entities, OutputMode.TABLE)
        assert "(1)-[:ALLIES_WITH]->(2)" in rendered

    def test_json_entities(self, entities: QueryResult) -> None:
        payload = json.loads(self.render(entities, OutputMode.JSON))
        row = payload[0]
        assert row["a"]["kind"] == "node"
        assert row["a"]["labels"] == ["Program"]
        assert row["a"]["properties"] == {"designation": "Kevin Flynn"}
        assert row["r"]["kind"] == "relationship"
        assert row["r"]["type"] == "ALLIES_WITH"
        assert row["r"]["start"] == 1
        assert row["r"]["end"] == 2
        assert row["p"]["kind"] == "path"
        assert [node["id"] for node in row["p"]["nodes"]] == [1, 2]


class TestEmptyColumns(_Rendering):
    """Verify a write statement with no projection renders nothing."""

    def test_no_columns_renders_nothing(self) -> None:
        result = QueryResult(columns=(), rows=())
        for mode in OutputMode:
            stream = io.StringIO()
            ResultWriter(mode).write(result, stream)
            assert stream.getvalue() == ""
