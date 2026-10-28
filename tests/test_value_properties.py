# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Property tests for strict values and special property keys."""

import typing

import hypothesis
import hypothesis.strategies
import pytest

from pygrafito import Graph, ValidationError
from pygrafito.model import Value
from pygrafito.storage.codec import PropertyCodec


class TestValueProperties:
    """Verify the strict value codec and special-key predicate paths."""

    VALID: typing.ClassVar[hypothesis.strategies.SearchStrategy[object]] = (
        hypothesis.strategies.one_of(
            hypothesis.strategies.booleans(),
            hypothesis.strategies.integers(min_value=-(2**63), max_value=2**63 - 1),
            hypothesis.strategies.floats(allow_nan=False, allow_infinity=False),
            hypothesis.strategies.text(max_size=20),
            hypothesis.strategies.lists(hypothesis.strategies.booleans(), max_size=5),
            hypothesis.strategies.lists(
                hypothesis.strategies.integers(min_value=-(2**63), max_value=2**63 - 1),
                max_size=5,
            ),
            hypothesis.strategies.lists(
                hypothesis.strategies.floats(allow_nan=False, allow_infinity=False),
                max_size=5,
            ),
            hypothesis.strategies.lists(hypothesis.strategies.text(max_size=10), max_size=5),
        )
    )
    INVALID: typing.ClassVar[hypothesis.strategies.SearchStrategy[object]] = (
        hypothesis.strategies.sampled_from(
            [
                None,
                {"key": 1},
                [[1]],
                [1, "x"],
                [1, 1.0],
                [True, 1],
                float("nan"),
                float("inf"),
                2**63,
                -(2**63) - 1,
            ]
        )
    )
    SPECIAL_KEYS: typing.ClassVar[tuple[str, ...]] = (
        '"',
        'a"b',
        'a"b\nc',
        "a'b",
        "a\\b",
        "a\nb",
        "a\tb",
        "a$b",
        "a.b",
        "a[b]",
        "a{b}",
        "café",
        "Ω☃",
    )

    @hypothesis.given(value=VALID)
    def test_valid_values_round_trip(self, value: object) -> None:
        """Encode and decode every supported scalar or homogeneous list."""
        codec = PropertyCodec()
        payload = codec.encode_value(typing.cast(Value, value))
        assert codec.decode_value(payload) == value

    @hypothesis.given(value=INVALID)
    def test_invalid_values_raise_validation_error(self, value: object) -> None:
        """Reject nulls, maps, nesting, mixed lists, non-finite numbers, and overflow."""
        with pytest.raises(ValidationError):
            PropertyCodec().validate_value(value)

    @pytest.mark.parametrize("key", SPECIAL_KEYS)
    def test_special_keys_match_through_predicates(self, key: str) -> None:
        """Match quotes, newlines, tabs, unicode, dots, and ``$`` literally."""
        quoted = "`" + key.replace("`", "``") + "`"
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", **{key: "Tron"})
            found = list(graph.find_nodes("Program", **{key: "Tron"}))
            result = graph.query(
                f"MATCH (n:Program) WHERE n.{quoted} = $value RETURN n",
                {"value": "Tron"},
            )
        assert len(found) == 1
        assert len(result.rows) == 1
