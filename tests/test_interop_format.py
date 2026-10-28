# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for strict JSONL snapshot encoding and decoding."""

from pathlib import Path

import pytest

from pygrafito.engine.interop import JsonLinesCodec, SnapshotHeader, SnapshotReader
from pygrafito.model import Node, Relationship, ValidationError
from pygrafito.storage.codec import PropertyCodec


class TestHeader:
    """Verify the snapshot header contract."""

    @pytest.fixture
    def codec(self) -> JsonLinesCodec:
        """Return a codec for the tests."""
        return JsonLinesCodec(PropertyCodec())

    def test_header_round_trip(self, codec: JsonLinesCodec) -> None:
        """A header encodes canonically and decodes to the same counts."""
        header = SnapshotHeader(nodes=3, relationships=2)
        line = codec.encode_header(header)
        assert line == (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,"nodes":3,"relationships":2}\n'
        )
        assert codec.decode_header(line) == header

    def test_missing_header(self, codec: JsonLinesCodec, tmp_path: Path) -> None:
        """A file with no lines has no header."""
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        with (
            SnapshotReader(path, codec) as reader,
            pytest.raises(
                ValidationError,
                match="missing snapshot header",
            ),
        ):
            reader.header()

    def test_unsupported_version(self, codec: JsonLinesCodec) -> None:
        """A version other than the supported one is refused."""
        line = (
            '{"kind":"header","format":"pygrafito-jsonl","version":1,"nodes":0,"relationships":0}'
        )
        with pytest.raises(ValidationError, match="unsupported snapshot version"):
            codec.decode_header(line)

    def test_unknown_field(self, codec: JsonLinesCodec) -> None:
        """An unknown header field is refused."""
        line = (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":0,"relationships":0,"extra":true}'
        )
        with pytest.raises(ValidationError, match="unknown field"):
            codec.decode_header(line)

    def test_duplicate_field(self, codec: JsonLinesCodec) -> None:
        """A duplicate header field is refused."""
        line = (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            '"nodes":0,"nodes":0,"relationships":0}'
        )
        with pytest.raises(ValidationError, match="duplicate JSON field"):
            codec.decode_header(line)

    @pytest.mark.parametrize("nodes", ["true", "-1", "1.0", '"1"'])
    def test_invalid_counts(self, codec: JsonLinesCodec, nodes: str) -> None:
        """Header counts must be non-negative integers."""
        line = (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            f'"nodes":{nodes},"relationships":0}}'
        )
        with pytest.raises(ValidationError, match="non-negative integer"):
            codec.decode_header(line)

    def test_blank_lines_before_header(
        self,
        codec: JsonLinesCodec,
        tmp_path: Path,
    ) -> None:
        """Blank lines before the header are ignored."""
        line = codec.encode_header(SnapshotHeader(nodes=0, relationships=0))
        path = tmp_path / "blank-header.jsonl"
        path.write_text(f"\n\n{line}", encoding="utf-8")
        with SnapshotReader(path, codec) as reader:
            assert reader.header() == SnapshotHeader(nodes=0, relationships=0)
            assert list(reader.records()) == []

    def test_node_is_not_a_header(self, codec: JsonLinesCodec) -> None:
        """The first record must be tagged as a header."""
        line = '{"kind":"node","id":1,"labels":[],"properties":{}}'
        with pytest.raises(ValidationError, match="first record must be a snapshot header"):
            codec.decode_header(line)


class TestRecords:
    """Verify node and relationship record decoding."""

    @pytest.fixture
    def codec(self) -> JsonLinesCodec:
        """Return a codec for the tests."""
        return JsonLinesCodec(PropertyCodec())

    def test_node_round_trip(self, codec: JsonLinesCodec) -> None:
        """A node keeps labels and typed properties through a round trip."""
        node = Node(
            id=1,
            labels=frozenset({"Program", "ISO"}),
            properties={
                "designation": "Quorra",
                "cycles": 37,
                "active": True,
                "ratings": [1, 2, 3],
            },
        )
        line = codec.encode_node(node)
        assert line == (
            '{"kind":"node","id":1,"labels":["ISO","Program"],'
            '"properties":{"active":true,"cycles":37,"designation":"Quorra",'
            '"ratings":[1,2,3]}}\n'
        )
        decoded = codec.decode_record(line)
        assert isinstance(decoded, Node)
        assert decoded.labels == node.labels
        assert dict(decoded.properties) == dict(node.properties)

    def test_relationship_round_trip(self, codec: JsonLinesCodec) -> None:
        """A relationship keeps its labels, direction, endpoints, and properties."""
        relationship = Relationship(
            id=1,
            start_id=1,
            end_id=2,
            labels=("ALLIES_WITH",),
            directed=False,
            properties={"since_cycle": 2020},
        )
        line = codec.encode_relationship(relationship)
        assert line == (
            '{"kind":"relationship","id":1,"labels":["ALLIES_WITH"],"directed":false,'
            '"start_id":1,"end_id":2,"properties":{"since_cycle":2020}}\n'
        )
        decoded = codec.decode_record(line)
        assert isinstance(decoded, Relationship)
        assert decoded.labels == relationship.labels
        assert decoded.directed is False
        assert decoded.start_id == relationship.start_id
        assert decoded.end_id == relationship.end_id
        assert dict(decoded.properties) == dict(relationship.properties)

    def test_unknown_field(self, codec: JsonLinesCodec) -> None:
        """Unknown record fields are refused."""
        line = '{"kind":"node","id":1,"labels":[],"properties":{},"extra":1}'
        with pytest.raises(ValidationError, match="unknown field"):
            codec.decode_record(line)

    def test_missing_field(self, codec: JsonLinesCodec) -> None:
        """Missing record fields are refused."""
        line = '{"kind":"node","id":1,"properties":{}}'
        with pytest.raises(ValidationError, match="missing field"):
            codec.decode_record(line)

    def test_duplicate_record_field(self, codec: JsonLinesCodec) -> None:
        """Duplicate record fields are refused."""
        line = '{"kind":"node","id":1,"labels":[],"labels":[],"properties":{}}'
        with pytest.raises(ValidationError, match="duplicate JSON field"):
            codec.decode_record(line)

    def test_unknown_kind(self, codec: JsonLinesCodec) -> None:
        """Only node and relationship records are accepted after the header."""
        line = (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,"nodes":0,"relationships":0}'
        )
        with pytest.raises(ValidationError, match="record kind"):
            codec.decode_record(line)

    def test_duplicate_label(self, codec: JsonLinesCodec) -> None:
        """A node cannot repeat a label."""
        line = '{"kind":"node","id":1,"labels":["Program","Program"],"properties":{}}'
        with pytest.raises(ValidationError, match="duplicate label"):
            codec.decode_record(line)

    def test_labels_must_be_an_array(self, codec: JsonLinesCodec) -> None:
        """Labels are always an array."""
        line = '{"kind":"node","id":1,"labels":"Program","properties":{}}'
        with pytest.raises(ValidationError, match="labels must be an array"):
            codec.decode_record(line)

    @pytest.mark.parametrize(
        "identifier",
        ["0", "-1", "true", "1.5", '"x"'],
    )
    def test_invalid_node_id(self, codec: JsonLinesCodec, identifier: str) -> None:
        """Node ids must be positive integers."""
        line = f'{{"kind":"node","id":{identifier},"labels":[],"properties":{{}}}}'
        with pytest.raises(ValidationError, match="id must be a positive integer"):
            codec.decode_record(line)

    def test_invalid_relationship_endpoint(self, codec: JsonLinesCodec) -> None:
        """Relationship endpoints must be positive integers."""
        line = (
            '{"kind":"relationship","id":1,"labels":["ALLIES_WITH"],"directed":true,'
            '"start_id":0,"end_id":2,"properties":{}}'
        )
        with pytest.raises(ValidationError, match="start_id must be a positive integer"):
            codec.decode_record(line)

    def test_invalid_relationship_label(self, codec: JsonLinesCodec) -> None:
        """Relationship labels must be non-empty strings."""
        line = (
            '{"kind":"relationship","id":1,"labels":[""],"directed":true,'
            '"start_id":1,"end_id":2,"properties":{}}'
        )
        with pytest.raises(ValidationError, match="label"):
            codec.decode_record(line)


class TestValues:
    """Verify the strict property value model."""

    @pytest.fixture
    def codec(self) -> JsonLinesCodec:
        """Return a codec for the tests."""
        return JsonLinesCodec(PropertyCodec())

    def test_empty_list_is_valid(self, codec: JsonLinesCodec) -> None:
        """An empty list is a valid homogeneous list."""
        line = '{"kind":"node","id":1,"labels":[],"properties":{"tags":[]}}'
        decoded = codec.decode_record(line)
        assert isinstance(decoded, Node)
        assert decoded.properties["tags"] == []

    @pytest.mark.parametrize(
        "properties",
        [
            '{"a":null}',
            '{"a":{"b":1}}',
            '{"a":[[1]]}',
            '{"a":[1,"x"]}',
            '{"a":NaN}',
            '{"a":Infinity}',
            '{"a":1e999}',
            '{"a":9223372036854775808}',
            '{"":1}',
        ],
    )
    def test_invalid_properties(self, codec: JsonLinesCodec, properties: str) -> None:
        """Strict values reject nulls, nesting, non-finite numbers, and overflow."""
        line = f'{{"kind":"node","id":1,"labels":[],"properties":{properties}}}'
        with pytest.raises(ValidationError):
            codec.decode_record(line)

    def test_property_key_with_dot(self, codec: JsonLinesCodec) -> None:
        """Property keys keep dots and spaces literally."""
        line = '{"kind":"node","id":1,"labels":[],"properties":{"a.b c":1}}'
        decoded = codec.decode_record(line)
        assert isinstance(decoded, Node)
        assert decoded.properties["a.b c"] == 1


class TestReader:
    """Verify line handling and line-numbered failures."""

    @pytest.fixture
    def codec(self) -> JsonLinesCodec:
        """Return a codec for the tests."""
        return JsonLinesCodec(PropertyCodec())

    def test_reader_skips_blank_lines(
        self,
        codec: JsonLinesCodec,
        tmp_path: Path,
    ) -> None:
        """Blank lines do not contribute records but keep line numbers."""
        path = tmp_path / "snapshot.jsonl"
        path.write_text(
            codec.encode_header(SnapshotHeader(nodes=1, relationships=1))
            + "\n"
            + codec.encode_node(Node(id=1, labels=frozenset({"Program"})))
            + codec.encode_relationship(
                Relationship(
                    id=1,
                    start_id=1,
                    end_id=1,
                    labels=("ALLIES_WITH",),
                )
            ),
            encoding="utf-8",
        )
        with SnapshotReader(path, codec) as reader:
            assert reader.header() == SnapshotHeader(nodes=1, relationships=1)
            records = list(reader.records())
        assert [number for number, _ in records] == [3, 4]
        assert isinstance(records[0][1], Node)
        assert isinstance(records[1][1], Relationship)

    def test_invalid_utf8(self, codec: JsonLinesCodec, tmp_path: Path) -> None:
        """Invalid UTF-8 is reported with the line number."""
        path = tmp_path / "snapshot.jsonl"
        path.write_bytes(b"\xff\n")
        with (
            SnapshotReader(path, codec) as reader,
            pytest.raises(
                ValidationError,
                match="line 1: not valid UTF-8",
            ),
        ):
            reader.header()

    def test_truncated_record(self, codec: JsonLinesCodec, tmp_path: Path) -> None:
        """An incomplete JSON line is reported with the line number."""
        path = tmp_path / "snapshot.jsonl"
        path.write_text(
            codec.encode_header(SnapshotHeader(nodes=1, relationships=0)) + '{"kind":"node"\n',
            encoding="utf-8",
        )
        with SnapshotReader(path, codec) as reader:
            reader.header()
            with pytest.raises(ValidationError, match="line 2: invalid JSON"):
                list(reader.records())

    def test_header_only(self, codec: JsonLinesCodec, tmp_path: Path) -> None:
        """A header-only file has no records."""
        path = tmp_path / "snapshot.jsonl"
        path.write_text(
            codec.encode_header(SnapshotHeader(nodes=0, relationships=0)),
            encoding="utf-8",
        )
        with SnapshotReader(path, codec) as reader:
            assert reader.header() == SnapshotHeader(nodes=0, relationships=0)
            assert list(reader.records()) == []

    def test_no_ambient_data(self, codec: JsonLinesCodec) -> None:
        """Encoded records carry no timestamp, path, or library version."""
        node = Node(id=1, labels=frozenset({"Program"}), properties={"designation": "Tron"})
        line = codec.encode_node(node)
        assert "202" not in line
        assert "pygrafito/" not in line
        assert line.endswith("\n")
