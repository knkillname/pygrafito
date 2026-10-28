# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Property tests for canonical snapshot encoding and restore rejection."""

import pathlib
import tempfile
import typing

import hypothesis
import hypothesis.strategies
import pytest

from pygrafito import Graph, ValidationError
from pygrafito.engine.interop import JsonLinesCodec, SnapshotHeader
from pygrafito.model import Node, Relationship, Value
from pygrafito.storage.codec import PropertyCodec

ALPHABET = "abcXYZ019_\"'\\\n\t$.[]{}: ,éΩ☃"


class TestSnapshotProperties:
    """Verify round-trip stability and strict rejection behavior."""

    GOLDEN: typing.ClassVar[pathlib.Path] = (
        pathlib.Path(__file__).resolve().parent / "fixtures" / "golden-v2.jsonl"
    )
    DATA: typing.ClassVar[bytes] = GOLDEN.read_bytes()
    LABELS: typing.ClassVar[hypothesis.strategies.SearchStrategy[list[str]]] = (
        hypothesis.strategies.lists(
            hypothesis.strategies.text(alphabet=ALPHABET, min_size=1, max_size=10),
            max_size=3,
            unique=True,
        )
    )
    VALUES: typing.ClassVar[hypothesis.strategies.SearchStrategy[Value]] = typing.cast(
        hypothesis.strategies.SearchStrategy[Value],
        hypothesis.strategies.one_of(
            hypothesis.strategies.booleans(),
            hypothesis.strategies.integers(min_value=-(2**63), max_value=2**63 - 1),
            hypothesis.strategies.floats(allow_nan=False, allow_infinity=False),
            hypothesis.strategies.text(alphabet=ALPHABET, max_size=10),
            hypothesis.strategies.lists(hypothesis.strategies.booleans(), max_size=3),
            hypothesis.strategies.lists(
                hypothesis.strategies.integers(min_value=-(2**63), max_value=2**63 - 1),
                max_size=3,
            ),
            hypothesis.strategies.lists(
                hypothesis.strategies.floats(allow_nan=False, allow_infinity=False),
                max_size=3,
            ),
            hypothesis.strategies.lists(
                hypothesis.strategies.text(alphabet=ALPHABET, max_size=8),
                max_size=3,
            ),
        ),
    )
    PROPERTIES: typing.ClassVar[hypothesis.strategies.SearchStrategy[dict[str, Value]]] = (
        hypothesis.strategies.dictionaries(
            keys=hypothesis.strategies.text(alphabet=ALPHABET, min_size=1, max_size=8),
            values=VALUES,
            max_size=3,
        )
    )

    @hypothesis.given(labels=LABELS, properties=PROPERTIES)
    def test_node_round_trip_is_stable(
        self,
        labels: list[str],
        properties: dict[str, Value],
    ) -> None:
        """Encode, decode, and re-encode a node to identical bytes."""
        codec = JsonLinesCodec(PropertyCodec())
        node = Node(id=1, labels=frozenset(labels), properties=properties)
        line = codec.encode_node(node)
        decoded = codec.decode_record(line)
        assert isinstance(decoded, Node)
        assert decoded.labels == node.labels
        assert dict(decoded.properties) == dict(node.properties)
        assert codec.encode_node(decoded) == line

    @hypothesis.given(
        labels=LABELS,
        properties=PROPERTIES,
        directed=hypothesis.strategies.booleans(),
    )
    def test_relationship_round_trip_is_stable(
        self,
        labels: list[str],
        properties: dict[str, Value],
        directed: bool,
    ) -> None:
        """Encode, decode, and re-encode a relationship to identical bytes."""
        codec = JsonLinesCodec(PropertyCodec())
        relationship = Relationship(
            id=1,
            start_id=1,
            end_id=2,
            labels=tuple(labels),
            directed=directed,
            properties=properties,
        )
        line = codec.encode_relationship(relationship)
        decoded = codec.decode_record(line)
        assert isinstance(decoded, Relationship)
        assert decoded.labels == relationship.labels
        assert decoded.directed is directed
        assert decoded.start_id == relationship.start_id
        assert decoded.end_id == relationship.end_id
        assert dict(decoded.properties) == dict(relationship.properties)
        assert codec.encode_relationship(decoded) == line

    @hypothesis.given(
        nodes=hypothesis.strategies.integers(min_value=0, max_value=1000),
        relationships=hypothesis.strategies.integers(min_value=0, max_value=1000),
    )
    def test_header_round_trip_is_stable(self, nodes: int, relationships: int) -> None:
        """Encode and decode a header with canonical counts."""
        codec = JsonLinesCodec(PropertyCodec())
        header = SnapshotHeader(nodes=nodes, relationships=relationships)
        line = codec.encode_header(header)
        assert codec.decode_header(line) == header
        assert line == (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            f'"nodes":{nodes},"relationships":{relationships}}}\n'
        )

    @hypothesis.given(
        nodes=hypothesis.strategies.integers(max_value=-1),
        relationships=hypothesis.strategies.integers(min_value=0, max_value=10),
    )
    def test_negative_header_counts_are_rejected(
        self,
        nodes: int,
        relationships: int,
    ) -> None:
        """Reject a header with a negative count."""
        line = (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,'
            f'"nodes":{nodes},"relationships":{relationships}}}'
        )
        with pytest.raises(ValidationError, match="non-negative integer"):
            JsonLinesCodec(PropertyCodec()).decode_header(line)

    @hypothesis.given(
        cut=hypothesis.strategies.integers(min_value=0, max_value=len(DATA)),
    )
    def test_truncated_snapshot_is_rejected(self, cut: int) -> None:
        """Reject every truncation that removes record content."""
        if cut >= len(self.DATA) - 1:
            return
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "truncated.jsonl"
            path.write_bytes(self.DATA[:cut])
            with Graph.open(":memory:") as graph:
                with pytest.raises(ValidationError):
                    graph.restore_jsonl(path)
                assert list(graph.find_nodes()) == []

    def test_extra_record_is_rejected(self) -> None:
        """Reject a record beyond the header count and roll back."""
        extra = (
            b'{"kind":"relationship","id":99,"labels":["TRUSTS"],"directed":true,'
            b'"start_id":1,"end_id":3,"properties":{}}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "extra.jsonl"
            path.write_bytes(self.DATA + extra)
            with Graph.open(":memory:") as graph:
                with pytest.raises(ValidationError, match="header declares"):
                    graph.restore_jsonl(path)
                assert list(graph.find_nodes()) == []
                assert graph.check_integrity() == ()
