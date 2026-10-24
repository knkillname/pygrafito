# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the domain model snapshots and error hierarchy."""

import typing
from dataclasses import FrozenInstanceError

import pytest

from pygrafito.model import (
    ConnectedNodeError,
    Constraint,
    ConstraintViolationError,
    Direction,
    ElementKind,
    GraphClosedError,
    HandleAffinityError,
    Index,
    IndexKind,
    LockTimeoutError,
    Node,
    NotFoundError,
    Path,
    PygrafitoError,
    Relationship,
    TransactionError,
    TraversalStep,
    UnsupportedSqliteError,
    ValidationError,
    Value,
)


class TestDirection:
    """Verify direction members."""

    def test_members(self) -> None:
        assert Direction.OUTGOING.value == "outgoing"
        assert Direction.INCOMING.value == "incoming"
        assert Direction.BOTH.value == "both"


class TestElementKind:
    """Verify the shared element-kind enum and its index alias."""

    def test_members(self) -> None:
        assert ElementKind.NODE.value == "node"
        assert ElementKind.RELATIONSHIP.value == "relationship"

    def test_index_kind_is_an_alias(self) -> None:
        assert IndexKind is ElementKind


class TestConstraint:
    """Verify the uniqueness constraint value type."""

    def test_fields_and_immutability(self) -> None:
        constraint = Constraint(ElementKind.NODE, "Program", "designation")
        assert constraint == Constraint(ElementKind.NODE, "Program", "designation")
        assert constraint != Constraint(ElementKind.RELATIONSHIP, "Program", "designation")
        with pytest.raises(FrozenInstanceError):
            constraint.key = "cycles"  # type: ignore[misc]

    def test_ordering_key(self) -> None:
        constraints = [
            Constraint(ElementKind.RELATIONSHIP, "ALLIES_WITH", "since"),
            Constraint(ElementKind.NODE, "Program", "designation"),
            Constraint(ElementKind.NODE, "ISO", "designation"),
        ]
        ordered = sorted(constraints, key=lambda item: item.ordering_key)
        assert ordered == [
            Constraint(ElementKind.NODE, "ISO", "designation"),
            Constraint(ElementKind.NODE, "Program", "designation"),
            Constraint(ElementKind.RELATIONSHIP, "ALLIES_WITH", "since"),
        ]

    @pytest.mark.parametrize(
        ("kind", "scope", "key"),
        [
            ("node", "Program", "designation"),
            (ElementKind.NODE, "", "designation"),
            (ElementKind.NODE, "Program", ""),
            (ElementKind.NODE, None, "designation"),
            (ElementKind.RELATIONSHIP, "ALLIES_WITH", 1),
        ],
    )
    def test_invalid_fields_rejected(self, kind: object, scope: object, key: object) -> None:
        with pytest.raises(ValidationError):
            Constraint(
                typing.cast(ElementKind, kind),
                typing.cast(str, scope),
                typing.cast(str, key),
            )

    def test_violation_payload(self) -> None:
        error = ConstraintViolationError(
            ElementKind.NODE,
            "Program",
            "designation",
            "Tron",
            7,
        )
        assert error.kind is ElementKind.NODE
        assert error.scope == "Program"
        assert error.key == "designation"
        assert error.value == "Tron"
        assert error.existing == 7
        assert "Tron" in str(error)
        assert "7" in str(error)


class TestIndex:
    """Verify the declared index value type."""

    def test_members(self) -> None:
        assert IndexKind.NODE.value == "node"
        assert IndexKind.RELATIONSHIP.value == "relationship"

    def test_value_equality_and_immutability(self) -> None:
        index = Index(IndexKind.NODE, "cycles")
        assert index == Index(IndexKind.NODE, "cycles")
        assert index != Index(IndexKind.RELATIONSHIP, "cycles")
        with pytest.raises(FrozenInstanceError):
            index.key = "designation"  # type: ignore[misc]

    @pytest.mark.parametrize("key", ["", None, 1])
    def test_invalid_key_rejected(self, key: object) -> None:
        with pytest.raises(ValidationError):
            Index(IndexKind.NODE, key)  # type: ignore[arg-type]

    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Index(typing.cast(IndexKind, "node"), "cycles")


class TestNode:
    """Verify node snapshot behavior."""

    def test_mapping_access(self) -> None:
        node = Node(id=1, labels=frozenset({"Person"}), properties={"name": "Ada", "age": 36})
        assert node["name"] == "Ada"
        assert node.get("age") == 36
        assert node.get("missing") is None
        assert set(node) == {"name", "age"}
        assert len(node) == 2

    def test_labels_are_frozen(self) -> None:
        labels = {"Person"}
        node = Node(id=1, labels=frozenset(labels))
        labels.add("Employee")
        assert node.labels == frozenset({"Person"})

    def test_snapshot_is_frozen(self) -> None:
        node = Node(id=1, properties={"name": "Ada"})
        mutable = typing.cast(typing.Any, node)
        with pytest.raises(FrozenInstanceError):
            mutable.id = 2
        with pytest.raises(TypeError):
            mutable.properties["name"] = "Grace"

    def test_defaults_are_empty(self) -> None:
        node = Node(id=1)
        assert node.labels == frozenset()
        assert dict(node) == {}

    def test_property_input_is_copied(self) -> None:
        properties: dict[str, Value] = {"name": "Ada"}
        node = Node(id=1, properties=properties)
        properties["name"] = "Grace"
        assert node["name"] == "Ada"


class TestRelationship:
    """Verify relationship snapshot behavior."""

    def test_fields_and_mapping(self) -> None:
        relationship = Relationship(
            id=3,
            rel_type="KNOWS",
            start_id=1,
            end_id=2,
            properties={"since": 2020},
        )
        assert relationship.rel_type == "KNOWS"
        assert relationship.start_id == 1
        assert relationship.end_id == 2
        assert relationship["since"] == 2020

    def test_defaults_are_empty(self) -> None:
        relationship = Relationship(id=1, rel_type="KNOWS", start_id=1, end_id=2)
        assert dict(relationship) == {}


class TestPath:
    """Verify path shape and endpoints."""

    def test_length_and_endpoints(self) -> None:
        first = Node(id=1)
        second = Node(id=2)
        relationship = Relationship(id=1, rel_type="KNOWS", start_id=1, end_id=2)
        path = Path(nodes=(first, second), relationships=(relationship,))
        assert path.length == 1
        assert path.start is first
        assert path.end is second

    def test_zero_length_path(self) -> None:
        node = Node(id=1)
        path = Path(nodes=(node,), relationships=())
        assert path.length == 0
        assert path.start is node
        assert path.end is node

    def test_empty_nodes_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Path(nodes=(), relationships=())

    def test_mismatched_counts_rejected(self) -> None:
        node = Node(id=1)
        relationship = Relationship(id=1, rel_type="KNOWS", start_id=1, end_id=1)
        with pytest.raises(ValidationError):
            Path(nodes=(node,), relationships=(relationship,))

    def test_sequences_are_materialized(self) -> None:
        node = Node(id=1)
        nodes: list[Node] = [node]
        path = Path(nodes=typing.cast(typing.Any, nodes), relationships=())
        nodes.clear()
        assert path.nodes == (node,)

    def test_snapshot_is_frozen(self) -> None:
        path = Path(nodes=(Node(id=1),), relationships=())
        mutable = typing.cast(typing.Any, path)
        with pytest.raises(FrozenInstanceError):
            mutable.nodes = ()


class TestTraversalStep:
    """Verify traversal steps."""

    def test_fields(self) -> None:
        node = Node(id=4)
        step = TraversalStep(node=node, depth=2)
        assert step.node is node
        assert step.depth == 2


class TestErrorHierarchy:
    """Verify that every domain error derives from the base error."""

    @pytest.mark.parametrize(
        "error_type",
        [
            ValidationError,
            NotFoundError,
            ConnectedNodeError,
            GraphClosedError,
            TransactionError,
            UnsupportedSqliteError,
            HandleAffinityError,
            LockTimeoutError,
            ConstraintViolationError,
        ],
    )
    def test_inheritance(self, error_type: type[PygrafitoError]) -> None:
        assert issubclass(error_type, PygrafitoError)
        assert issubclass(PygrafitoError, Exception)
