# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for strict property validation and canonical JSON encoding."""

import math
import sqlite3
import typing

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

    @pytest.mark.parametrize("key", ["null\x00key", "\x00"])
    def test_null_character_rejected(
        self,
        property_codec: PropertyCodec,
        key: str,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.json_path(key)

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("designation", "'$.\"designation\"'"),
            ("a.b", "'$.\"a.b\"'"),
            ("a b", "'$.\"a b\"'"),
            ('a"b', '\'$."a\\"b"\''),
            ("a\\b", "'$.\"a\\\\b\"'"),
            ("a'b", "'$.\"a''b\"'"),
            ("qu'\"\\x", "'$.\"qu''\\\"\\\\x\"'"),
            ("ñ✓", "'$.\"ñ✓\"'"),
            ("'; DROP TABLE nodes; --", "'$.\"''; DROP TABLE nodes; --\"'"),
        ],
    )
    def test_sql_path_literals(
        self,
        property_codec: PropertyCodec,
        key: str,
        expected: str,
    ) -> None:
        assert property_codec.sql_json_path(key) == expected

    def test_sql_path_literal_is_executable(self, property_codec: PropertyCodec) -> None:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE probes (props TEXT NOT NULL)")
        connection.execute("INSERT INTO probes VALUES (?)", ('{"a\'b": 7}',))
        literal = property_codec.sql_json_path("a'b")
        row = connection.execute(f"SELECT json_extract(props, {literal}) FROM probes").fetchone()
        assert row == (7,)
        connection.close()


class TestScannedProperties(_CodecTestCase):
    """Verify the scan fallback for keys without a portable JSON path."""

    @pytest.mark.parametrize("key", ['"', 'a"b', "a\nb", "a\tb", 'a"b\nc'])
    def test_keys_that_need_a_scan(self, property_codec: PropertyCodec, key: str) -> None:
        assert property_codec.needs_property_scan(key)

    @pytest.mark.parametrize("key", ["age", "a.b", "a b", "a\\b", "a'b", "café"])
    def test_keys_with_a_portable_path(self, property_codec: PropertyCodec, key: str) -> None:
        assert not property_codec.needs_property_scan(key)

    def test_type_expression_scans_the_stored_object(self, property_codec: PropertyCodec) -> None:
        expression = property_codec.property_type_expression("nodes.props", 'a"b')
        assert expression.startswith("(SELECT property.type FROM json_each(nodes.props)")
        assert "property.key = 'a\"b'" in expression

    def test_value_expression_scans_the_stored_object(self, property_codec: PropertyCodec) -> None:
        expression = property_codec.property_value_expression("NEW.props", "a\nb")
        assert expression.startswith("(SELECT property.value FROM json_each(NEW.props)")
        assert "property.key = 'a\nb'" in expression

    def test_portable_index_columns_use_the_json_path(self, property_codec: PropertyCodec) -> None:
        columns = property_codec.portable_index_columns("a.b")
        assert columns == ("(json_extract(props, '$.\"a.b\"'), json_type(props, '$.\"a.b\"'))")

    def test_portable_index_columns_refuse_a_scan_key(self, property_codec: PropertyCodec) -> None:
        assert property_codec.portable_index_columns('a"b') is None


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


class TestExactEquality(_CodecTestCase):
    """Verify exact real matching through canonical stored JSON text."""

    REGRESSION_VALUES: typing.ClassVar[tuple[float, ...]] = (
        2.7710821668887726e-173,
        3.277095539246836e-284,
        1.6287812207021506e-109,
    )

    def test_exact_expression_asks_for_the_path_twice(
        self,
        property_codec: PropertyCodec,
    ) -> None:
        expression = property_codec.exact_value_expression("nodes.props", "cycles")
        assert expression == "json_extract(nodes.props, '$.\"cycles\"', '$.\"cycles\"')"

    def test_exact_expression_falls_back_to_a_scanned_key(
        self,
        property_codec: PropertyCodec,
    ) -> None:
        key = 'a"b'
        expression = property_codec.exact_value_expression("nodes.props", key)
        fallback = property_codec.property_value_expression("nodes.props", key)
        assert expression == fallback

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1.5, "[1.5,1.5]"),
            (-0.0, "[-0.0,-0.0]"),
            (0.0, "[0.0,0.0]"),
            (True, "[true,true]"),
            (2, "[2,2]"),
            ("2", '["2","2"]'),
            ([1, 2], "[[1,2],[1,2]]"),
        ],
    )
    def test_exact_comparison_value(
        self,
        property_codec: PropertyCodec,
        value: Value,
        expected: str,
    ) -> None:
        assert property_codec.exact_comparison_value("cycles", value) == expected

    def test_exact_comparison_value_falls_back_to_a_scanned_key(
        self,
        property_codec: PropertyCodec,
    ) -> None:
        key = 'a"b'
        assert property_codec.exact_comparison_value(key, 2.5) == 2.5
        assert property_codec.exact_comparison_value(key, [1, 2]) == "[1,2]"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (36.0, (36.0, 36)),
            (36, (36, 36.0)),
            (0.0, (-0.0, 0.0, 0)),
            (-0.0, (-0.0, 0.0, 0)),
            (1e300, (1e300,)),
            (2.5, (2.5,)),
        ],
    )
    def test_numeric_match_values(
        self,
        property_codec: PropertyCodec,
        value: int | float,
        expected: tuple[int | float, ...],
    ) -> None:
        matched = property_codec.numeric_match_values(value)
        assert len(matched) == len(expected)
        assert [property_codec.encode_value(item) for item in matched] == [
            property_codec.encode_value(item) for item in expected
        ]

    def test_numeric_match_values_require_a_number(
        self,
        property_codec: PropertyCodec,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.numeric_match_values(typing.cast(int, True))
        with pytest.raises(ValidationError):
            property_codec.numeric_match_values(typing.cast(float, "36"))

    @pytest.mark.parametrize(
        "value",
        [2.5, -0.0, 0.0, True, False, 2, "", "Tron", [1, 2], ["ISO", "Grid"]],
    )
    def test_decode_exact_value_round_trips(
        self,
        property_codec: PropertyCodec,
        value: Value,
    ) -> None:
        exact = property_codec.exact_comparison_value("cycles", value)
        decoded = property_codec.decode_exact_value(typing.cast(str, exact))
        assert decoded == value
        assert type(decoded) is type(value)

    @pytest.mark.parametrize("payload", ["{", "1", '["a","b"]', "[]"])
    def test_decode_exact_value_rejects_malformed_text(
        self,
        property_codec: PropertyCodec,
        payload: str,
    ) -> None:
        with pytest.raises(ValidationError):
            property_codec.decode_exact_value(payload)

    def test_regression_values_survive_exact_text(self, property_codec: PropertyCodec) -> None:
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE TABLE probes (id INTEGER PRIMARY KEY, props TEXT)")
            values = [
                value
                for item in self.REGRESSION_VALUES
                for value in (item, math.nextafter(item, math.inf))
            ]
            for index, value in enumerate(values, start=1):
                connection.execute(
                    "INSERT INTO probes (id, props) VALUES (?, ?)",
                    (index, property_codec.encode_properties({"value": value})),
                )
            expression = property_codec.exact_value_expression("probes.props", "value")
            for index, value in enumerate(values, start=1):
                rows = connection.execute(
                    f"SELECT id FROM probes WHERE {expression} = ?",
                    (property_codec.exact_comparison_value("value", value),),
                ).fetchall()
                assert rows == [(index,)]

            stored = connection.execute(f"SELECT {expression} FROM probes WHERE id = 1").fetchone()
            assert stored is not None
            decoded = property_codec.decode_exact_value(str(stored[0]))
            assert decoded == self.REGRESSION_VALUES[0]
        finally:
            connection.close()
