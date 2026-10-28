# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Strict JSONL snapshots for graph export and restore."""

import dataclasses
import itertools
import json
import operator
import os
import sqlite3
import typing
from collections.abc import Iterator, Mapping
from pathlib import Path
from sqlite3 import Connection
from types import TracebackType
from typing import Self

from pygrafito.engine.transaction import Transaction
from pygrafito.model import Node, PygrafitoError, Relationship, ValidationError, Value
from pygrafito.storage.codec import PropertyCodec


@dataclasses.dataclass(frozen=True, slots=True)
class InteropSummary:
    """Counts of the nodes and relationships in an interop operation.

    Parameters
    ----------
    nodes : int
        Number of nodes exported or restored.
    relationships : int
        Number of relationships exported or restored.
    """

    nodes: int
    relationships: int

    def __post_init__(self) -> None:
        """Validate the counts.

        Raises
        ------
        ValidationError
            If a count is not a non-negative integer.
        """
        for field, value in (("nodes", self.nodes), ("relationships", self.relationships)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                message = f"{field} must be a non-negative integer"
                raise ValidationError(message)


@dataclasses.dataclass(frozen=True, slots=True)
class SnapshotHeader:
    """Metadata carried by the first record of a snapshot.

    Parameters
    ----------
    nodes : int
        Number of node records that follow.
    relationships : int
        Number of relationship records that follow.
    """

    nodes: int
    relationships: int

    def __post_init__(self) -> None:
        """Validate the declared counts.

        Raises
        ------
        ValidationError
            If a count is not a non-negative integer.
        """
        for field, value in (("nodes", self.nodes), ("relationships", self.relationships)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                message = f"{field} must be a non-negative integer"
                raise ValidationError(message)


class JsonLinesCodec:
    """Encode and decode strict JSONL snapshot records.

    Parameters
    ----------
    property_codec : PropertyCodec
        Codec used to validate labels, types, keys, and property values.
    """

    FORMAT: typing.ClassVar[str] = "pygrafito-jsonl"
    VERSION: typing.ClassVar[int] = 2
    HEADER_FIELDS: typing.ClassVar[frozenset[str]] = frozenset(
        {"kind", "format", "version", "nodes", "relationships"}
    )
    NODE_FIELDS: typing.ClassVar[frozenset[str]] = frozenset({"kind", "id", "labels", "properties"})
    RELATIONSHIP_FIELDS: typing.ClassVar[frozenset[str]] = frozenset(
        {"kind", "id", "labels", "directed", "start_id", "end_id", "properties"}
    )

    def __init__(self, property_codec: PropertyCodec) -> None:
        self._codec = property_codec

    def encode_header(self, header: SnapshotHeader) -> str:
        """Encode one snapshot header.

        Parameters
        ----------
        header : SnapshotHeader
            Header counts to encode.

        Returns
        -------
        str
            One compact JSON line terminated by a newline.
        """
        record: dict[str, object] = {
            "kind": "header",
            "format": self.FORMAT,
            "version": self.VERSION,
            "nodes": header.nodes,
            "relationships": header.relationships,
        }
        return f"{self._dumps(record)}\n"

    def decode_header(self, payload: str) -> SnapshotHeader:
        """Decode and validate one snapshot header.

        Parameters
        ----------
        payload : str
            JSON object text.

        Returns
        -------
        SnapshotHeader
            Validated header counts.

        Raises
        ------
        ValidationError
            If the object is not a supported header.
        """
        record = self._decode_object(payload)
        if record.get("kind") != "header":
            message = "the first record must be a snapshot header"
            raise ValidationError(message)
        self._require_fields(record, self.HEADER_FIELDS)
        if record["format"] != self.FORMAT:
            message = f"unsupported snapshot format {record['format']!r}"
            raise ValidationError(message)
        version = record["version"]
        if isinstance(version, bool) or not isinstance(version, int):
            message = "snapshot version must be an integer"
            raise ValidationError(message)
        if version != self.VERSION:
            message = f"unsupported snapshot version {version}; expected {self.VERSION}"
            raise ValidationError(message)
        return SnapshotHeader(
            nodes=self._non_negative_int(record["nodes"], "nodes"),
            relationships=self._non_negative_int(record["relationships"], "relationships"),
        )

    def encode_node(self, node: Node) -> str:
        """Encode one node record.

        Parameters
        ----------
        node : Node
            Node to encode.

        Returns
        -------
        str
            One compact JSON line terminated by a newline.
        """
        properties = {key: node.properties[key] for key in sorted(node.properties)}
        record: dict[str, object] = {
            "kind": "node",
            "id": node.id,
            "labels": sorted(node.labels),
            "properties": properties,
        }
        return f"{self._dumps(record)}\n"

    def encode_relationship(self, relationship: Relationship) -> str:
        """Encode one relationship record.

        Parameters
        ----------
        relationship : Relationship
            Relationship to encode.

        Returns
        -------
        str
            One compact JSON line terminated by a newline.
        """
        properties = {key: relationship.properties[key] for key in sorted(relationship.properties)}
        record: dict[str, object] = {
            "kind": "relationship",
            "id": relationship.id,
            "labels": sorted(relationship.labels),
            "directed": relationship.directed,
            "start_id": relationship.start_id,
            "end_id": relationship.end_id,
            "properties": properties,
        }
        return f"{self._dumps(record)}\n"

    def decode_record(self, payload: str) -> Node | Relationship:
        """Decode and validate one node or relationship record.

        Parameters
        ----------
        payload : str
            JSON object text.

        Returns
        -------
        Node | Relationship
            Validated record using source identifiers.

        Raises
        ------
        ValidationError
            If the object is not a valid node or relationship record.
        """
        record = self._decode_object(payload)
        kind = record.get("kind")
        if kind == "node":
            self._require_fields(record, self.NODE_FIELDS)
            return Node(
                id=self._positive_int(record["id"], "id"),
                labels=frozenset(self._labels(record["labels"])),
                properties=self._properties(record["properties"]),
            )
        if kind == "relationship":
            self._require_fields(record, self.RELATIONSHIP_FIELDS)
            return Relationship(
                id=self._positive_int(record["id"], "id"),
                start_id=self._positive_int(record["start_id"], "start_id"),
                end_id=self._positive_int(record["end_id"], "end_id"),
                labels=self._labels(record["labels"]),
                directed=self._boolean(record["directed"], "directed"),
                properties=self._properties(record["properties"]),
            )
        message = "record kind must be 'node' or 'relationship'"
        raise ValidationError(message)

    def _decode_object(self, payload: str) -> dict[str, object]:
        """Decode one JSON object with duplicate-key and constant checks.

        Parameters
        ----------
        payload : str
            JSON object text.

        Returns
        -------
        dict[str, object]
            Decoded object.

        Raises
        ------
        ValidationError
            If the text is not a JSON object or contains invalid values.
        """
        try:
            decoded: object = json.loads(
                payload,
                object_pairs_hook=self._pairs,
                parse_constant=self._reject_constant,
            )
        except json.JSONDecodeError as error:
            message = f"invalid JSON: {error.msg}"
            raise ValidationError(message) from error
        except RecursionError as error:
            message = "JSON nesting is too deep"
            raise ValidationError(message) from error
        except ValueError as error:
            raise ValidationError(str(error)) from error
        if not isinstance(decoded, dict):
            message = "a snapshot line must be a JSON object"
            raise ValidationError(message)
        return typing.cast(dict[str, object], decoded)

    @staticmethod
    def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        """Build one JSON object while rejecting duplicate fields.

        Parameters
        ----------
        pairs : list[tuple[str, object]]
            Key and value pairs supplied by the JSON decoder.

        Returns
        -------
        dict[str, object]
            Decoded object.

        Raises
        ------
        ValidationError
            If a field appears more than once.
        """
        record: dict[str, object] = {}
        for key, value in pairs:
            if key in record:
                message = f"duplicate JSON field {key!r}"
                raise ValidationError(message)
            record[key] = value
        return record

    @staticmethod
    def _reject_constant(value: str) -> typing.Never:
        """Reject a non-finite JSON constant.

        Parameters
        ----------
        value : str
            Constant spelling.

        Raises
        ------
        ValueError
            Always, for ``NaN`` and infinity spellings.
        """
        message = f"{value} is not a finite number"
        raise ValueError(message)

    @staticmethod
    def _require_fields(
        record: Mapping[str, object],
        expected: frozenset[str],
    ) -> None:
        """Require exactly one set of record fields.

        Parameters
        ----------
        record : Mapping[str, object]
            Decoded record.
        expected : frozenset[str]
            Acceptable field names.

        Raises
        ------
        ValidationError
            If a field is missing or unknown.
        """
        missing = expected.difference(record)
        if missing:
            message = f"missing field(s): {', '.join(sorted(missing))}"
            raise ValidationError(message)
        unexpected = set(record).difference(expected)
        if unexpected:
            message = f"unknown field(s): {', '.join(sorted(unexpected))}"
            raise ValidationError(message)

    @staticmethod
    def _positive_int(value: object, field: str) -> int:
        """Validate one positive integer field.

        Parameters
        ----------
        value : object
            Candidate value.
        field : str
            Field name used in error messages.

        Returns
        -------
        int
            Validated positive integer.

        Raises
        ------
        ValidationError
            If the value is not a positive integer.
        """
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            message = f"{field} must be a positive integer"
            raise ValidationError(message)
        return value

    @staticmethod
    def _non_negative_int(value: object, field: str) -> int:
        """Validate one non-negative integer field.

        Parameters
        ----------
        value : object
            Candidate value.
        field : str
            Field name used in error messages.

        Returns
        -------
        int
            Validated non-negative integer.

        Raises
        ------
        ValidationError
            If the value is not a non-negative integer.
        """
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            message = f"{field} must be a non-negative integer"
            raise ValidationError(message)
        return value

    @staticmethod
    def _boolean(value: object, field: str) -> bool:
        """Validate one boolean field.

        Parameters
        ----------
        value : object
            Candidate value.
        field : str
            Field name used in error messages.

        Returns
        -------
        bool
            Validated boolean.

        Raises
        ------
        ValidationError
            If the value is not a boolean.
        """
        if not isinstance(value, bool):
            message = f"{field} must be a boolean"
            raise ValidationError(message)
        return value

    def _labels(self, value: object) -> tuple[str, ...]:
        """Validate one label array.

        Parameters
        ----------
        value : object
            Candidate label array.

        Returns
        -------
        tuple[str, ...]
            Validated labels.

        Raises
        ------
        ValidationError
            If the value is not an array of unique non-empty strings.
        """
        if not isinstance(value, list):
            message = "labels must be an array"
            raise ValidationError(message)
        labels: list[str] = []
        seen: set[str] = set()
        for item in value:
            label = self._codec.validate_identifier(item, "label")
            if label in seen:
                message = f"duplicate label {label!r}"
                raise ValidationError(message)
            seen.add(label)
            labels.append(label)
        return tuple(labels)

    def _properties(self, value: object) -> dict[str, Value]:
        """Validate one property object.

        Parameters
        ----------
        value : object
            Candidate property object.

        Returns
        -------
        dict[str, Value]
            Validated properties.

        Raises
        ------
        ValidationError
            If the object or a key or value is invalid.
        """
        if not isinstance(value, dict):
            message = "properties must be an object"
            raise ValidationError(message)
        record = typing.cast(dict[object, object], value)
        properties: dict[str, Value] = {}
        for key, item in record.items():
            property_key = self._codec.validate_identifier(key, "property key")
            if property_key in properties:
                message = f"duplicate property key {property_key!r}"
                raise ValidationError(message)
            properties[property_key] = self._codec.validate_value(item)
        return properties

    @staticmethod
    def _dumps(record: Mapping[str, object]) -> str:
        """Serialize one record with canonical JSON settings.

        Parameters
        ----------
        record : Mapping[str, object]
            Record to serialize.

        Returns
        -------
        str
            Compact JSON text without a newline.
        """
        return json.dumps(
            record,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


class SnapshotReader:
    """Read a snapshot file one record at a time.

    Parameters
    ----------
    path : Path
        Snapshot file to read.
    codec : JsonLinesCodec
        Codec used to decode lines.
    """

    def __init__(self, path: Path, codec: JsonLinesCodec) -> None:
        self._path = path
        self._codec = codec
        self._handle: typing.BinaryIO | None = None
        self._line = 0

    def __enter__(self) -> Self:
        """Open the snapshot file.

        Returns
        -------
        Self
            This reader.
        """
        self._handle = self._path.open("rb")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Close the snapshot file.

        Parameters
        ----------
        exc_type : type[BaseException] | None
            Exception type raised inside the block, if any.
        _exc_value : BaseException | None
            Exception instance raised inside the block, if any.
        _traceback : TracebackType | None
            Traceback raised inside the block, if any.
        """
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def header(self) -> SnapshotHeader:
        """Read the first non-blank line as the snapshot header.

        Returns
        -------
        SnapshotHeader
            Decoded header counts.

        Raises
        ------
        ValidationError
            If the file has no header or the header is invalid.
        """
        handle = self._require_handle()
        for raw in handle:
            self._line += 1
            text = self._text(raw)
            if not text.strip():
                continue
            try:
                return self._codec.decode_header(text)
            except ValidationError as error:
                message = f"{self._path}: line {self._line}: {error}"
                raise ValidationError(message) from error
        message = f"{self._path}: missing snapshot header"
        raise ValidationError(message)

    def records(self) -> Iterator[tuple[int, Node | Relationship]]:
        """Yield records after the header.

        Yields
        ------
        tuple[int, Node | Relationship]
            One-based line number and the decoded record.

        Raises
        ------
        ValidationError
            If a line is invalid.
        """
        handle = self._require_handle()
        for raw in handle:
            self._line += 1
            text = self._text(raw)
            if not text.strip():
                continue
            try:
                record = self._codec.decode_record(text)
            except ValidationError as error:
                message = f"{self._path}: line {self._line}: {error}"
                raise ValidationError(message) from error
            yield (self._line, record)

    def _require_handle(self) -> typing.BinaryIO:
        """Return the open file handle.

        Returns
        -------
        typing.BinaryIO
            Open snapshot file.

        Raises
        ------
        ValidationError
            If the reader is not open.
        """
        if self._handle is None:
            message = "snapshot reader is not open"
            raise ValidationError(message)
        return self._handle

    def _text(self, raw: bytes) -> str:
        """Decode one line as UTF-8.

        Parameters
        ----------
        raw : bytes
            Encoded line.

        Returns
        -------
        str
            Decoded text.

        Raises
        ------
        ValidationError
            If the line is not valid UTF-8.
        """
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as error:
            message = f"{self._path}: line {self._line}: not valid UTF-8"
            raise ValidationError(message) from error


class SnapshotExporter:
    """Stream one graph into a snapshot file.

    Parameters
    ----------
    connection : Connection
        Connection that belongs to the active read snapshot.
    property_codec : PropertyCodec
        Codec used to validate stored values.
    """

    def __init__(self, connection: Connection, property_codec: PropertyCodec) -> None:
        self._connection = connection
        self._property_codec = property_codec
        self._codec = JsonLinesCodec(property_codec)

    def export(self, destination: Path) -> InteropSummary:
        """Write one snapshot through a sibling temporary file.

        Parameters
        ----------
        destination : Path
            Destination path. It may already exist; the caller decides whether
            replacement is allowed.

        Returns
        -------
        InteropSummary
            Counts written to the snapshot.

        Raises
        ------
        ValidationError
            If the destination cannot be written or stored data is invalid.
        """
        header = self._counts()
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(self._codec.encode_header(header))
                for node in self._nodes():
                    handle.write(self._codec.encode_node(node))
                for relationship in self._relationships():
                    handle.write(self._codec.encode_relationship(relationship))
            temporary.replace(destination)
        except (OSError, sqlite3.Error) as error:
            message = f"could not write snapshot: {destination}"
            raise ValidationError(message) from error
        finally:
            temporary.unlink(missing_ok=True)
        return InteropSummary(nodes=header.nodes, relationships=header.relationships)

    def _counts(self) -> SnapshotHeader:
        """Count the nodes and relationships in the snapshot.

        Returns
        -------
        SnapshotHeader
            Counts for the header record.
        """
        return SnapshotHeader(
            nodes=self._count("nodes"),
            relationships=self._count("relationships"),
        )

    def _count(self, table: str) -> int:
        """Count the rows of one graph table.

        Parameters
        ----------
        table : str
            Internal table name.

        Returns
        -------
        int
            Number of rows.
        """
        row = self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if row is None:
            return 0
        return int(row[0])

    def _nodes(self) -> Iterator[Node]:
        """Stream nodes and their labels in id order.

        Yields
        ------
        Node
            One validated node.
        """
        rows = self._connection.execute(
            "SELECT n.id, n.props, l.label "
            "FROM nodes AS n "
            "LEFT JOIN node_labels AS l ON l.node_id = n.id "
            "ORDER BY n.id, l.label"
        )
        for node_id, group in itertools.groupby(rows, key=operator.itemgetter(0)):
            labels: set[str] = set()
            payload = "{}"
            for offset, row in enumerate(group):
                if offset == 0:
                    payload = str(row[1])
                if row[2] is not None:
                    labels.add(self._property_codec.validate_identifier(row[2], "label"))
            yield Node(
                id=int(node_id),
                labels=frozenset(labels),
                properties=self._property_codec.decode_properties(payload),
            )

    def _relationships(self) -> Iterator[Relationship]:
        """Stream relationships in id order.

        Yields
        ------
        Relationship
            One validated relationship.
        """
        rows = self._connection.execute(
            "SELECT r.id, r.src, r.dst, r.directed, "
            "(SELECT json_group_array(label) FROM (SELECT label FROM relationship_labels "
            "WHERE relationship_id = r.id ORDER BY label)), r.props "
            "FROM relationships AS r ORDER BY r.id"
        )
        for row in rows:
            labels = () if row[4] is None else tuple(json.loads(str(row[4])))
            yield Relationship(
                id=int(row[0]),
                start_id=int(row[1]),
                end_id=int(row[2]),
                labels=tuple(
                    self._property_codec.validate_identifier(label, "label") for label in labels
                ),
                directed=bool(row[3]),
                properties=self._property_codec.decode_properties(str(row[5])),
            )


class GraphHandle(typing.Protocol):
    """Minimal graph surface used by the restore runner."""

    def transaction(self) -> Transaction:
        """Start an explicit transaction.

        Returns
        -------
        Transaction
            Transaction handle.
        """
        ...


class SnapshotRestorer:
    """Load one snapshot into an empty or replaced graph.

    Parameters
    ----------
    graph : GraphHandle
        Graph that owns the transaction.
    connection : Connection
        Connection shared with the graph.
    property_codec : PropertyCodec
        Codec used to validate stored values.
    path : Path
        Snapshot file to read.
    """

    def __init__(
        self,
        graph: GraphHandle,
        connection: Connection,
        property_codec: PropertyCodec,
        path: Path,
    ) -> None:
        self._graph = graph
        self._connection = connection
        self._codec = JsonLinesCodec(property_codec)
        self._path = path

    def restore(self, *, replace: bool) -> InteropSummary:
        """Restore the snapshot in one transaction.

        Parameters
        ----------
        replace : bool
            Whether a non-empty target may be cleared before loading.

        Returns
        -------
        InteropSummary
            Counts restored from the snapshot.

        Raises
        ------
        ValidationError
            If the target is not empty, the snapshot is invalid, or the counts
            do not match.
        ReadOnlyError
            If the graph handle is read-only.
        TransactionError
            If a transaction cannot be started or another is active.
        """
        try:
            with SnapshotReader(self._path, self._codec) as reader:
                header = reader.header()
                with self._graph.transaction() as transaction:
                    self._prepare_target(replace=replace)
                    return self._load(reader, header, transaction)
        except OSError as error:
            message = f"could not read snapshot: {self._path}"
            raise ValidationError(message) from error

    def _prepare_target(self, *, replace: bool) -> None:
        """Refuse a non-empty target or clear it when replacing.

        Parameters
        ----------
        replace : bool
            Whether to clear a non-empty target.

        Raises
        ------
        ValidationError
            If the target is non-empty and replacement was not requested.
        """
        row = self._connection.execute(
            "SELECT EXISTS(SELECT 1 FROM nodes) OR EXISTS(SELECT 1 FROM relationships)"
        ).fetchone()
        non_empty = row is not None and int(row[0]) == 1
        if not non_empty:
            return
        if not replace:
            message = (
                "restore target is not empty; pass replace=True or use "
                ".restore PATH --replace to replace it"
            )
            raise ValidationError(message)
        self._connection.execute("DELETE FROM relationships")
        self._connection.execute("DELETE FROM nodes")

    def _load(
        self,
        reader: SnapshotReader,
        header: SnapshotHeader,
        transaction: Transaction,
    ) -> InteropSummary:
        """Insert every record and verify the header counts.

        Parameters
        ----------
        reader : SnapshotReader
            Reader positioned after the header.
        header : SnapshotHeader
            Declared counts.
        transaction : Transaction
            Active transaction used for writes.

        Returns
        -------
        InteropSummary
            Restored counts.

        Raises
        ------
        ValidationError
            If a record is invalid or the counts do not match.
        """
        mapping: dict[int, int] = {}
        nodes = 0
        relationships = 0
        in_relationships = False
        for number, record in reader.records():
            if isinstance(record, Node):
                if in_relationships:
                    message = (
                        f"{self._path}: line {number}: node records must precede "
                        "relationship records"
                    )
                    raise ValidationError(message)
                if record.id in mapping:
                    message = f"{self._path}: line {number}: duplicate node id {record.id}"
                    raise ValidationError(message)
                try:
                    created = transaction.add_node(
                        *sorted(record.labels),
                        **dict(record.properties),
                    )
                except PygrafitoError as error:
                    error.add_note(f"while restoring {self._path} line {number}")
                    raise
                mapping[record.id] = created.id
                nodes += 1
                continue
            in_relationships = True
            relationship = typing.cast(Relationship, record)
            start = mapping.get(relationship.start_id)
            end = mapping.get(relationship.end_id)
            if start is None or end is None:
                missing = relationship.start_id if start is None else relationship.end_id
                message = (
                    f"{self._path}: line {number}: relationship references "
                    f"unknown node id {missing}"
                )
                raise ValidationError(message)
            try:
                transaction.add_relationship(
                    start,
                    relationship.labels,
                    end,
                    directed=relationship.directed,
                    **dict(relationship.properties),
                )
            except PygrafitoError as error:
                error.add_note(f"while restoring {self._path} line {number}")
                raise
            relationships += 1
        if nodes != header.nodes or relationships != header.relationships:
            message = (
                f"{self._path}: header declares {header.nodes} nodes and "
                f"{header.relationships} relationships; restored {nodes} and "
                f"{relationships}"
            )
            raise ValidationError(message)
        return InteropSummary(nodes=nodes, relationships=relationships)


__all__ = [
    "GraphHandle",
    "InteropSummary",
    "JsonLinesCodec",
    "SnapshotExporter",
    "SnapshotHeader",
    "SnapshotReader",
    "SnapshotRestorer",
]
