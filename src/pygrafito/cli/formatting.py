# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Result rendering for the graph shell."""

import csv
import enum
import json
import typing
import unicodedata
from collections.abc import Mapping, Sequence

from pygrafito import Node, Path, QueryResult, Relationship, ValidationError

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class OutputMode(enum.Enum):
    """Result rendering mode selected for a shell session."""

    TABLE = "table"
    JSON = "json"
    JSONL = "jsonl"
    CSV = "csv"
    LINE = "line"

    @classmethod
    def from_name(cls, name: str) -> OutputMode:
        """Resolve a rendering mode by its command-line name.

        Parameters
        ----------
        name : str
            Mode name.

        Returns
        -------
        OutputMode
            Matching mode.

        Raises
        ------
        ValidationError
            If no mode has that name.
        """
        try:
            return cls(name.lower())
        except ValueError:
            valid = ", ".join(mode.value for mode in cls)
            message = f"unknown output mode {name!r}; expected one of: {valid}"
            raise ValidationError(message) from None


class ValueFormatter:
    """Render one query value for one output mode.

    Parameters
    ----------
    mode : OutputMode
        Rendering mode.
    """

    ESCAPES: typing.ClassVar[Mapping[str, str]] = {
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
    }
    WIDE: typing.ClassVar[frozenset[str]] = frozenset({"W", "F"})

    def __init__(self, mode: OutputMode) -> None:
        self._mode = mode

    def cell(self, value: object) -> str:
        """Render one value as a table, line, or CSV field.

        Parameters
        ----------
        value : object
            Query value to render.

        Returns
        -------
        str
            Field text.
        """
        if value is None:
            return "" if self._mode is OutputMode.CSV else "NULL"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return value if self._mode is OutputMode.CSV else self._escape(value)
        if isinstance(value, (int, float)):
            return str(value)
        return self._complex_cell(value)

    def _complex_cell(self, value: object) -> str:
        """Render a container, entity, or unknown value as a field.

        Parameters
        ----------
        value : object
            Value to render.

        Returns
        -------
        str
            Field text.
        """
        if isinstance(value, (Node, Relationship, Path)):
            return self._entity_text(value)
        if isinstance(value, Mapping):
            return self._mapping_text(value)
        if isinstance(value, (list, tuple)):
            return self._list_text(value)
        return self._escape(str(value))

    def json_value(self, value: object) -> JsonValue:
        """Render one value as a JSON-compatible object.

        Parameters
        ----------
        value : object
            Query value to render.

        Returns
        -------
        JsonValue
            JSON value with graph entities as tagged objects.
        """
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, Node):
            node: dict[str, JsonValue] = {
                "kind": "node",
                "id": value.id,
                "labels": typing.cast(list[JsonValue], sorted(value.labels)),
                "properties": self._json_mapping(value),
            }
            return node
        if isinstance(value, Relationship):
            relationship: dict[str, JsonValue] = {
                "kind": "relationship",
                "id": value.id,
                "type": value.rel_type,
                "start": value.start_id,
                "end": value.end_id,
                "properties": self._json_mapping(value),
            }
            return relationship
        if isinstance(value, Path):
            path: dict[str, JsonValue] = {
                "kind": "path",
                "nodes": [self.json_value(node) for node in value.nodes],
                "relationships": [
                    self.json_value(relationship) for relationship in value.relationships
                ],
            }
            return path
        return self._json_complex(value)

    def _json_complex(self, value: object) -> JsonValue:
        """Render a container or unknown value for JSON output.

        Parameters
        ----------
        value : object
            Value to render.

        Returns
        -------
        JsonValue
            JSON value.
        """
        if isinstance(value, Mapping):
            return self._json_mapping(value)
        if isinstance(value, (list, tuple)):
            return [self.json_value(item) for item in value]
        return str(value)

    @staticmethod
    def width(text: str) -> int:
        """Measure the display width of rendered text.

        Parameters
        ----------
        text : str
            Rendered field text.

        Returns
        -------
        int
            Terminal columns the text occupies.
        """
        total = 0
        for character in text:
            if unicodedata.combining(character):
                continue
            total += 2 if unicodedata.east_asian_width(character) in ValueFormatter.WIDE else 1
        return total

    @classmethod
    def _escape(cls, text: str) -> str:
        """Escape control characters that would break a text row.

        Parameters
        ----------
        text : str
            Raw string value.

        Returns
        -------
        str
            Text with newlines, carriage returns, and tabs escaped.
        """
        result = text
        for character, replacement in cls.ESCAPES.items():
            result = result.replace(character, replacement)
        return result

    def _entity_text(self, value: Node | Relationship | Path) -> str:
        """Render a graph entity in graph-shaped text.

        Parameters
        ----------
        value : Node | Relationship | Path
            Entity to render.

        Returns
        -------
        str
            Entity text.
        """
        if isinstance(value, Node):
            labels = "".join(f":{label}" for label in sorted(value.labels))
            prefix = f"{labels} " if labels else ""
            return f"({prefix}{self._properties_text(value, value.id)})"
        if isinstance(value, Relationship):
            properties = self._properties_text(value, value.id)
            return f"({value.start_id})-[:{value.rel_type} {properties}]->({value.end_id})"
        parts = [f"({value.nodes[0].id})"] if value.nodes else []
        current = value.nodes[0] if value.nodes else None
        for relationship, node in zip(value.relationships, value.nodes[1:], strict=True):
            if current is not None and relationship.start_id == current.id:
                parts.append(f"-[:{relationship.rel_type}]->({node.id})")
            else:
                parts.append(f"<-[:{relationship.rel_type}]-({node.id})")
            current = node
        return "".join(parts)

    def _properties_text(self, properties: Mapping[str, object], entity_id: int) -> str:
        """Render an entity id and its properties.

        Parameters
        ----------
        properties : Mapping[str, object]
            Property mapping.
        entity_id : int
            Element id to show first.

        Returns
        -------
        str
            Text inside braces.
        """
        items = [f"id: {entity_id}"]
        items.extend(
            f"{key}: {self._element_text(value)}" for key, value in sorted(properties.items())
        )
        return "{" + ", ".join(items) + "}"

    def _element_text(self, value: object) -> str:
        """Render one value inside a container or property list.

        Parameters
        ----------
        value : object
            Value to render.

        Returns
        -------
        str
            Text fragment.
        """
        if isinstance(value, (Node, Relationship, Path)):
            return self._entity_text(value)
        if isinstance(value, Mapping):
            return self._mapping_text(value)
        if isinstance(value, (list, tuple)):
            return self._list_text(value)
        return json.dumps(value, ensure_ascii=False)

    def _mapping_text(self, value: Mapping[str, object]) -> str:
        """Render a mapping as JSON-shaped text.

        Parameters
        ----------
        value : Mapping[str, object]
            Mapping to render.

        Returns
        -------
        str
            Mapping text.
        """
        items = [
            f"{json.dumps(key, ensure_ascii=False)}: {self._element_text(item)}"
            for key, item in value.items()
        ]
        return "{" + ", ".join(items) + "}"

    def _list_text(self, value: Sequence[object]) -> str:
        """Render a list as JSON-shaped text.

        Parameters
        ----------
        value : Sequence[object]
            List to render.

        Returns
        -------
        str
            List text.
        """
        return "[" + ", ".join(self._element_text(item) for item in value) + "]"

    def _json_mapping(self, value: Mapping[str, object]) -> dict[str, JsonValue]:
        """Render a mapping for JSON output.

        Parameters
        ----------
        value : Mapping[str, object]
            Mapping to render.

        Returns
        -------
        dict[str, JsonValue]
            JSON object with rendered values.
        """
        return {str(key): self.json_value(item) for key, item in value.items()}


class ResultWriter:
    """Write a materialized result in the selected output mode.

    Parameters
    ----------
    mode : OutputMode
        Rendering mode.
    headers : bool
        Whether table and CSV output include a header row.
    """

    def __init__(self, mode: OutputMode, *, headers: bool = True) -> None:
        self._mode = mode
        self._headers = headers
        self._formatter = ValueFormatter(mode)

    def write(self, result: QueryResult, stream: typing.TextIO) -> int:
        """Write one result and return its row count.

        Parameters
        ----------
        result : QueryResult
            Materialized result to render.
        stream : typing.TextIO
            Destination stream.

        Returns
        -------
        int
            Number of rows rendered.
        """
        if not result.columns:
            return 0
        rows = [[self._formatter.cell(value) for value in row.row_values] for row in result.rows]
        if self._mode is OutputMode.TABLE:
            self._write_table(result.columns, rows, stream)
        elif self._mode is OutputMode.LINE:
            self._write_line(result.columns, rows, stream)
        elif self._mode is OutputMode.CSV:
            self._write_csv(result.columns, rows, stream)
        elif self._mode is OutputMode.JSONL:
            self._write_jsonl(result, stream)
        else:
            self._write_json(result, stream)
        return len(result.rows)

    def _write_table(
        self,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        stream: typing.TextIO,
    ) -> None:
        """Write a bordered ASCII table.

        Parameters
        ----------
        columns : Sequence[str]
            Column names.
        rows : Sequence[Sequence[str]]
            Rendered cells.
        stream : typing.TextIO
            Destination stream.
        """
        widths = [
            max(
                [
                    ValueFormatter.width(column),
                    *(ValueFormatter.width(row[index]) for row in rows),
                ]
            )
            for index, column in enumerate(columns)
        ]
        border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
        if not rows and not self._headers:
            return
        stream.write(border + "\n")
        if self._headers:
            stream.write(self._table_row(columns, widths) + "\n")
            stream.write(border + "\n")
        for row in rows:
            stream.write(self._table_row(row, widths) + "\n")
        if rows:
            stream.write(border + "\n")

    @classmethod
    def _table_row(cls, cells: Sequence[str], widths: Sequence[int]) -> str:
        """Pad one table row to the column widths.

        Parameters
        ----------
        cells : Sequence[str]
            Rendered cells.
        widths : Sequence[int]
            Column display widths.

        Returns
        -------
        str
            Row line without a trailing newline.
        """
        padded = (
            cell + " " * (width - ValueFormatter.width(cell))
            for cell, width in zip(cells, widths, strict=True)
        )
        return "| " + " | ".join(padded) + " |"

    @staticmethod
    def _write_line(
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        stream: typing.TextIO,
    ) -> None:
        """Write one field per line, separated by a blank line.

        Parameters
        ----------
        columns : Sequence[str]
            Column names.
        rows : Sequence[Sequence[str]]
            Rendered cells.
        stream : typing.TextIO
            Destination stream.
        """
        for position, row in enumerate(rows):
            if position:
                stream.write("\n")
            for column, cell in zip(columns, row, strict=True):
                stream.write(f"{column} = {cell}\n")

    def _write_csv(
        self,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        stream: typing.TextIO,
    ) -> None:
        """Write CSV with minimal quoting.

        Parameters
        ----------
        columns : Sequence[str]
            Column names.
        rows : Sequence[Sequence[str]]
            Rendered cells.
        stream : typing.TextIO
            Destination stream.
        """
        writer = csv.writer(stream, lineterminator="\n")
        if self._headers:
            writer.writerow(columns)
        writer.writerows(rows)

    def _write_json(self, result: QueryResult, stream: typing.TextIO) -> None:
        """Write an indented JSON array of row objects.

        Parameters
        ----------
        result : QueryResult
            Materialized result.
        stream : typing.TextIO
            Destination stream.
        """
        payload = [
            {
                column: self._formatter.json_value(value)
                for column, value in zip(result.columns, row.row_values, strict=True)
            }
            for row in result.rows
        ]
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    def _write_jsonl(self, result: QueryResult, stream: typing.TextIO) -> None:
        """Write one compact JSON object per row.

        Parameters
        ----------
        result : QueryResult
            Materialized result.
        stream : typing.TextIO
            Destination stream.
        """
        for row in result.rows:
            payload = {
                column: self._formatter.json_value(value)
                for column, value in zip(result.columns, row.row_values, strict=True)
            }
            stream.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
            stream.write("\n")
