# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for strict property validation and canonical JSON encoding."""

import math

import pytest

from pygrafito.model import (
    Scalar,
    ValidationError,
    Value,
)
from pygrafito.storage.codec import (
    PropertyCodec,
)


class _CodecTestCase:
    """Provide a shared codec instance for the test cases."""

    @pytest.fixture
    def property_codec(self) -> PropertyCodec:
        """Return a fresh property codec.

        Returns
        -------
        PropertyCodec
            A property codec instance.
        """
        return PropertyCodec()


class TestScalarValues(_CodecTestCase):
    """Verify accepted scalar values and their types."""

    @pytest.mark.parametrize(
        "value",
        [
            True,
            False,
            0,
            1,
            -1,
            (2**63) - 1,
            -(2**63),
            1.5,
            -0.25,
            "",
            "hello",
            "unicode ñ 🐍",
        ],
    )
    def test_round_trip(self, property_codec: PropertyCodec, value: Value) -> None:
        encoded = property_codec.encode_value(value)
        decoded = property_codec.decode_value(encoded)
        assert decoded == value
        assert type(decoded) is type(value)

    def test_integer_below_range_rejected(self, property_codec: PropertyCodec) -> None:
        with pytest.raises(ValidationError):
            property_codec.encode_value(-(2**63) - 1)

    def test_integer_above_range_rejected(self, property_codec: PropertyCodec) -> None:
        with pytest.raises(ValidationError):
            property_codec.encode_value(2**63)

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_float_rejected(
        self,
        property_codec: PropertyCodec,
        value: float,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.encode_value(value)

    def test_none_rejected(self, property_codec: PropertyCodec) -> None:
        with pytest.raises(ValidationError):
            property_codec.validate_value(None)

    @pytest.mark.parametrize("value", [{}, {"a": 1}, (1, 2), {1, 2}, b"bytes", object()])
    def test_unsupported_types_rejected(
        self,
        property_codec: PropertyCodec,
        value: object,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.validate_value(value)


class TestListValues(_CodecTestCase):
    """Verify homogeneous list handling."""

    def test_empty_list_accepted(self, property_codec: PropertyCodec) -> None:
        assert property_codec.decode_value(property_codec.encode_value([])) == []

    @pytest.mark.parametrize(
        "value",
        [
            [1, 2, 3],
            [True, False],
            [1.0, 2.5],
            ["a", "b"],
            [],
        ],
    )
    def test_homogeneous_lists_round_trip(
        self,
        property_codec: PropertyCodec,
        value: list[Scalar],
    ) -> None:
        encoded = property_codec.encode_value(value)
        assert property_codec.decode_value(encoded) == value

    @pytest.mark.parametrize(
        "value",
        [
            [1, "a"],
            ["a", 1],
            [True, 1],
            [1, 1.0],
            [[1], [2]],
            [{"a": 1}],
            [None],
        ],
    )
    def test_mixed_or_nested_lists_rejected(
        self,
        property_codec: PropertyCodec,
        value: list[object],
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.validate_value(value)

    def test_list_order_is_preserved(self, property_codec: PropertyCodec) -> None:
        assert property_codec.encode_value([1, 2]) != property_codec.encode_value([2, 1])

    def test_canonical_encoding(self, property_codec: PropertyCodec) -> None:
        assert property_codec.encode_value([1, 2]) == "[1,2]"
        assert property_codec.encode_value([True, False]) == "[true,false]"
        assert property_codec.encode_value(["ñ", "a"]) == '["ñ","a"]'


class TestPropertyMappings(_CodecTestCase):
    """Verify canonical object encoding and decoding."""

    def test_round_trip(self, property_codec: PropertyCodec) -> None:
        properties: dict[str, Value] = {
            "name": "Ada",
            "age": 36,
            "active": True,
            "score": 1.5,
            "tags": ["math", "code"],
        }
        decoded = property_codec.decode_properties(property_codec.encode_properties(properties))
        assert decoded == properties

    def test_keys_are_sorted(self, property_codec: PropertyCodec) -> None:
        encoded = property_codec.encode_properties({"b": 2, "a": 1})
        assert encoded == '{"a":1,"b":2}'

    @pytest.mark.parametrize("key", ["a.b", "a b", 'a"b', "a\\b", "$.x", ""])
    def test_arbitrary_keys_round_trip(
        self,
        property_codec: PropertyCodec,
        key: str,
    ) -> None:
        if not key:
            with pytest.raises(ValidationError):
                property_codec.encode_properties({key: 1})
            return
        encoded = property_codec.encode_properties({key: 1})
        assert property_codec.decode_properties(encoded) == {key: 1}

    def test_empty_properties(self, property_codec: PropertyCodec) -> None:
        assert property_codec.encode_properties({}) == "{}"
        assert property_codec.decode_properties("{}") == {}

    def test_invalid_json_properties_rejected(
        self,
        property_codec: PropertyCodec,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.decode_properties("{")

    @pytest.mark.parametrize("payload", ["[]", "1", '"text"', "null"])
    def test_non_object_properties_rejected(
        self,
        property_codec: PropertyCodec,
        payload: str,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.decode_properties(payload)

    def test_invalid_json_value_rejected(self, property_codec: PropertyCodec) -> None:
        with pytest.raises(ValidationError):
            property_codec.decode_value("{")


class TestJsonPaths(_CodecTestCase):
    """Verify quoted JSON path construction."""

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("age", '$."age"'),
            ("a.b", '$."a.b"'),
            ("a b", '$."a b"'),
            ('a"b', r'$."a\"b"'),
            ("a\\b", r'$."a\\b"'),
            ("$.x", '$."$.x"'),
        ],
    )
    def test_quoted_paths(
        self,
        property_codec: PropertyCodec,
        key: str,
        expected: str,
    ) -> None:
        assert property_codec.json_path(key) == expected

    @pytest.mark.parametrize("key", ["", None, 1])
    def test_invalid_keys_rejected(
        self,
        property_codec: PropertyCodec,
        key: object,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.json_path(key)  # type: ignore[arg-type]


class TestTypeMetadata(_CodecTestCase):
    """Verify SQLite type names and comparison values."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, "true"),
            (False, "false"),
            (1, "integer"),
            (1.0, "real"),
            ("1", "text"),
            ([1, 2], "array"),
            ([], "array"),
        ],
    )
    def test_json_type(
        self,
        property_codec: PropertyCodec,
        value: Value,
        expected: str,
    ) -> None:
        assert property_codec.json_type(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, 1),
            (False, 0),
            (2, 2),
            (2.5, 2.5),
            ("2", "2"),
            ([1, 2], "[1,2]"),
        ],
    )
    def test_comparison_value(
        self,
        property_codec: PropertyCodec,
        value: Value,
        expected: int | float | str,
    ) -> None:
        assert property_codec.comparison_value(value) == expected

    def test_identifier_requires_non_empty_string(
        self,
        property_codec: PropertyCodec,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.validate_identifier("", "label")
        with pytest.raises(ValidationError):
            property_codec.validate_identifier(3, "label")
        assert property_codec.validate_identifier("Person", "label") == "Person"
