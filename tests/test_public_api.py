# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Freeze the exported public API surface against a checked-in snapshot."""

import dataclasses
import enum
import inspect
import json
import pathlib
import typing

import pygrafito


class TestPublicApi:
    """Compare the exported surface with the checked-in contract."""

    ROOT: typing.ClassVar[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
    SNAPSHOT: typing.ClassVar[pathlib.Path] = ROOT / "tests" / "fixtures" / "public_api.json"
    CORE_CLASSES: typing.ClassVar[tuple[str, ...]] = ("Graph", "Transaction", "PreparedQuery")

    @classmethod
    def normalize(cls, text: str) -> str:
        """Normalize interpreter-specific spellings in a signature.

        Parameters
        ----------
        text : str
            Rendered signature.

        Returns
        -------
        str
            Signature with a stable path type spelling.
        """
        return text.replace("pathlib._local.", "pathlib.")

    @classmethod
    def render_signature(cls, value: object) -> str:
        """Render the signature of one method, class method, or property.

        Parameters
        ----------
        value : object
            Attribute read from a class dictionary.

        Returns
        -------
        str
            Normalized signature text.

        Raises
        ------
        TypeError
            If the attribute is not callable and not a property.
        """
        if isinstance(value, property):
            if value.fget is None:
                raise TypeError("property has no getter")
            target = value.fget
        elif isinstance(value, (classmethod, staticmethod)):
            target = value.__func__
        elif callable(value):
            target = value
        else:
            raise TypeError(f"unsupported public attribute: {value!r}")
        return cls.normalize(str(inspect.signature(target)))

    @classmethod
    def describe_core_class(cls, name: str) -> dict[str, dict[str, str]]:
        """Describe the public methods and properties of one core class.

        Parameters
        ----------
        name : str
            Exported class name.

        Returns
        -------
        dict[str, dict[str, str]]
            Method and property signatures keyed by attribute name.
        """
        target = getattr(pygrafito, name)
        methods: dict[str, str] = {}
        properties: dict[str, str] = {}
        for attribute, value in target.__dict__.items():
            if attribute.startswith("_"):
                continue
            if isinstance(value, property):
                properties[attribute] = cls.render_signature(value)
            elif isinstance(value, (classmethod, staticmethod)) or inspect.isfunction(value):
                methods[attribute] = cls.render_signature(value)
        return {"methods": methods, "properties": properties}

    @classmethod
    def describe_dataclass(cls, target: object) -> list[dict[str, str]]:
        """Describe the fields of one exported dataclass.

        Parameters
        ----------
        target : object
            Dataclass type.

        Returns
        -------
        list[dict[str, str]]
            Field name, annotation, and default for each field.
        """
        hints = typing.get_type_hints(target)
        description: list[dict[str, str]] = []
        for field in dataclasses.fields(typing.cast(typing.Any, target)):
            if field.default is not dataclasses.MISSING:
                default = repr(field.default)
            elif field.default_factory is not dataclasses.MISSING:
                default = "<factory>"
            else:
                default = "<required>"
            description.append(
                {
                    "name": field.name,
                    "type": str(hints.get(field.name, field.type)),
                    "default": default,
                }
            )
        return description

    @classmethod
    def surface(cls) -> dict[str, object]:
        """Build the complete public surface description.

        Returns
        -------
        dict[str, object]
            Exports, core class signatures, dataclass fields, exceptions, and enums.
        """
        exports = sorted(pygrafito.__all__)
        core = {name: cls.describe_core_class(name) for name in cls.CORE_CLASSES}
        dataclass_surface: dict[str, list[dict[str, str]]] = {}
        exceptions: dict[str, list[str]] = {}
        enums: dict[str, list[list[str]]] = {}
        for name in exports:
            target = getattr(pygrafito, name)
            if not inspect.isclass(target):
                continue
            if dataclasses.is_dataclass(target):
                dataclass_surface[name] = cls.describe_dataclass(target)
            if issubclass(target, BaseException):
                exceptions[name] = [base.__name__ for base in target.__mro__]
            if issubclass(target, enum.Enum):
                enums[name] = [[member.name, member.value] for member in target]
        return {
            "exports": exports,
            "core": core,
            "dataclasses": dataclass_surface,
            "exceptions": exceptions,
            "enums": enums,
        }

    def test_snapshot_matches(self) -> None:
        """Fail when the public surface differs from the checked-in snapshot."""
        snapshot = json.loads(self.SNAPSHOT.read_text(encoding="utf-8"))
        assert self.surface() == snapshot

    def test_exception_hierarchy(self) -> None:
        """Require every exported exception to inherit ``PygrafitoError``."""
        exceptions = [
            getattr(pygrafito, name)
            for name in pygrafito.__all__
            if inspect.isclass(getattr(pygrafito, name))
            and issubclass(getattr(pygrafito, name), BaseException)
        ]
        assert exceptions
        for target in exceptions:
            assert issubclass(target, pygrafito.PygrafitoError)
