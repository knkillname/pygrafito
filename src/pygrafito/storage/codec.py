# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Strict property value validation and canonical JSON encoding."""

import json
import math
import typing
from collections.abc import Mapping

from pygrafito.model import Scalar, ValidationError, Value


class PropertyCodec:
    """Validate property values and convert them to and from JSON text.

    The codec owns every rule about which Python values may be stored. It
    encodes with canonical separators so that equal lists always produce equal
    database text, and it builds quoted JSON paths so property keys may contain
    dots, spaces, or quotes.
    """

    INTEGER_MIN: int = -(2**63)
    INTEGER_MAX: int = 2**63 - 1

    def validate_value(self, value: object) -> Value:
        """Validate a scalar or homogeneous list of scalars.

        Parameters
        ----------
        value : object
            Candidate property value.

        Returns
        -------
        Value
            The validated value, with lists copied.

        Raises
        ------
        ValidationError
            If the value is of an unsupported type, out of range, non-finite,
            or a non-homogeneous list.
        """
        if isinstance(value, list):
            items: list[Scalar] = []
            kind: str | None = None
            for item in value:
                item_kind = self._scalar_kind(item)
                if kind is None:
                    kind = item_kind
                elif kind != item_kind:
                    message = "property lists must contain values of one scalar type"
                    raise ValidationError(message)
                items.append(typing.cast(Scalar, item))
            return items
        self._scalar_kind(value)
        return typing.cast(Value, value)

    def validate_identifier(self, value: object, field: str) -> str:
        """Validate a non-empty identifier such as a label or property key.

        Parameters
        ----------
        value : object
            Candidate identifier.
        field : str
            Human-readable name of the field, used in error messages.

        Returns
        -------
        str
            The validated identifier.

        Raises
        ------
        ValidationError
            If the value is not a non-empty string.
        """
        if not isinstance(value, str) or not value:
            message = f"{field} must be a non-empty string"
            raise ValidationError(message)
        return value

    def encode_value(self, value: Value) -> str:
        """Encode one property value as canonical JSON text.

        Parameters
        ----------
        value : Value
            Value to encode.

        Returns
        -------
        str
            Canonical JSON representation of the value.

        Raises
        ------
        ValidationError
            If the value is not storable.
        """
        validated = self.validate_value(value)
        return self._dumps(validated)

    def decode_value(self, payload: str) -> Value:
        """Decode canonical JSON text into a property value.

        Parameters
        ----------
        payload : str
            JSON text read from the database.

        Returns
        -------
        Value
            The decoded value.

        Raises
        ------
        ValidationError
            If the text is not valid JSON or not a storable value.
        """
        try:
            decoded: object = json.loads(payload)
        except json.JSONDecodeError as error:
            message = "stored property value is not valid JSON"
            raise ValidationError(message) from error
        return self.validate_value(decoded)

    def encode_properties(
        self,
        properties: Mapping[str, Value],
    ) -> str:
        """Encode a property mapping as canonical JSON text.

        Parameters
        ----------
        properties : Mapping[str, Value]
            Properties to encode.

        Returns
        -------
        str
            Canonical JSON object text with sorted keys.

        Raises
        ------
        ValidationError
            If a key or value is not storable.
        """
        encoded: dict[str, Value] = {}
        for key, value in properties.items():
            property_key = self.validate_identifier(key, "property key")
            encoded[property_key] = self.validate_value(value)
        return self._dumps(encoded)

    def decode_properties(self, payload: str) -> dict[str, Value]:
        """Decode canonical JSON object text into a property mapping.

        Parameters
        ----------
        payload : str
            JSON object text read from the database.

        Returns
        -------
        dict[str, Value]
            Decoded properties in stored key order.

        Raises
        ------
        ValidationError
            If the text is not a valid JSON object of storable values.
        """
        try:
            decoded: object = json.loads(payload)
        except json.JSONDecodeError as error:
            message = "stored properties are not valid JSON"
            raise ValidationError(message) from error
        if not isinstance(decoded, dict):
            message = "stored properties must be a JSON object"
            raise ValidationError(message)
        properties: dict[str, Value] = {}
        for key, value in decoded.items():
            property_key = self.validate_identifier(key, "property key")
            properties[property_key] = self.validate_value(value)
        return properties

    def json_path(self, key: str) -> str:
        """Build a quoted JSON path for a property key.

        Parameters
        ----------
        key : str
            Property key. Dots, spaces, and quotes are treated literally.

        Returns
        -------
        str
            A SQLite JSON path such as ``$."a.b"``.

        Raises
        ------
        ValidationError
            If the key is not a non-empty string.
        """
        property_key = self.validate_identifier(key, "property key")
        escaped = property_key.replace("\\", "\\\\").replace('"', '\\"')
        return f'$."{escaped}"'

    def json_type(self, value: Value) -> str:
        """Return the SQLite JSON type reported for a property value.

        Parameters
        ----------
        value : Value
            Stored value whose type is needed.

        Returns
        -------
        str
            One of ``true``, ``false``, ``integer``, ``real``, ``text``, or
            ``array``.

        Raises
        ------
        ValidationError
            If the value is not storable.
        """
        validated = self.validate_value(value)
        if isinstance(validated, bool):
            return "true" if validated else "false"
        if isinstance(validated, int):
            return "integer"
        if isinstance(validated, float):
            return "real"
        if isinstance(validated, str):
            return "text"
        return "array"

    def comparison_value(self, value: Value) -> int | float | str:
        """Return the value SQLite ``json_extract`` yields for a property value.

        Parameters
        ----------
        value : Value
            Value used in a property predicate.

        Returns
        -------
        int | float | str
            The scalar to bind. Booleans become ``0`` or ``1`` and lists
            become canonical JSON text.

        Raises
        ------
        ValidationError
            If the value is not storable.
        """
        validated = self.validate_value(value)
        if isinstance(validated, bool):
            return int(validated)
        if isinstance(validated, list):
            return self._dumps(validated)
        return validated

    def _scalar_kind(self, value: object) -> str:
        """Classify and validate one scalar value.

        Parameters
        ----------
        value : object
            Candidate scalar.

        Returns
        -------
        str
            A stable kind name used to check list homogeneity.

        Raises
        ------
        ValidationError
            If the value is not a supported scalar.
        """
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            if not self.INTEGER_MIN <= value <= self.INTEGER_MAX:
                message = "integers must fit in the signed 64-bit range"
                raise ValidationError(message)
            return "int"
        if isinstance(value, float):
            if not math.isfinite(value):
                message = "floats must be finite"
                raise ValidationError(message)
            return "float"
        if isinstance(value, str):
            return "str"
        if value is None:
            message = "null is not a storable property value; assign None to remove a property"
            raise ValidationError(message)
        if isinstance(value, list):
            message = "nested lists are not storable property values"
            raise ValidationError(message)
        if isinstance(value, dict):
            message = "mappings are not storable property values"
            raise ValidationError(message)
        message = f"unsupported property value type: {type(value).__name__}"
        raise ValidationError(message)

    @staticmethod
    def _dumps(value: object) -> str:
        """Serialize a validated value with canonical JSON settings.

        Parameters
        ----------
        value : object
            Value to serialize.

        Returns
        -------
        str
            Compact JSON text with sorted keys and unescaped Unicode.
        """
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
