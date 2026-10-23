# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Tests for node persistence, labels, properties, and lookups."""

import typing
from collections.abc import Iterator

import pytest

from pygrafito.model import (
    NotFoundError,
    ValidationError,
    Value,
)
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.nodes import NodeRepository


class _NodeTestCase:
    """Provide a repository backed by an in-memory database."""

    @pytest.fixture
    def repository(self) -> Iterator[NodeRepository]:
        """Return a node repository on a fresh in-memory graph.

        Yields
        ------
        NodeRepository
            Repository under test.
        """
        database = Database(":memory:")
        try:
            yield NodeRepository(database.connection, PropertyCodec())
        finally:
            database.close()


class TestCreateAndGet(_NodeTestCase):
    """Verify node creation and reading."""

    def test_multiple_labels(self, repository: NodeRepository) -> None:
        node = repository.create(("Person", "Employee"), {"name": "Ada"})
        assert node.id > 0
        assert node.labels == frozenset({"Person", "Employee"})
        assert node["name"] == "Ada"

    def test_defaults_are_empty(self, repository: NodeRepository) -> None:
        node = repository.create()
        assert node.labels == frozenset()
        assert dict(node) == {}
        assert repository.get(node.id) == node

    def test_duplicate_labels_are_collapsed(self, repository: NodeRepository) -> None:
        node = repository.create(("Person", "Person"))
        assert node.labels == frozenset({"Person"})

    def test_ids_are_distinct(self, repository: NodeRepository) -> None:
        first = repository.create()
        second = repository.create()
        assert first.id != second.id

    def test_missing_node_raises(self, repository: NodeRepository) -> None:
        with pytest.raises(NotFoundError):
            repository.get(999)

    def test_exists(self, repository: NodeRepository) -> None:
        node = repository.create()
        assert repository.exists(node.id)
        assert not repository.exists(node.id + 1)


class TestLabels(_NodeTestCase):
    """Verify label updates."""

    def test_add_and_remove_labels(self, repository: NodeRepository) -> None:
        node = repository.create(("Person", "Employee"))
        node = repository.add_labels(node.id, ("Manager",))
        assert node.labels == frozenset({"Person", "Employee", "Manager"})
        node = repository.remove_labels(node.id, ("Employee",))
        assert node.labels == frozenset({"Person", "Manager"})
        node = repository.remove_labels(node.id, ("Missing",))
        assert node.labels == frozenset({"Person", "Manager"})

    def test_add_labels_is_idempotent(self, repository: NodeRepository) -> None:
        node = repository.create(("Person",))
        node = repository.add_labels(node.id, ("Person",))
        assert node.labels == frozenset({"Person"})

    def test_missing_node_raises(self, repository: NodeRepository) -> None:
        with pytest.raises(NotFoundError):
            repository.add_labels(999, ("Person",))
        with pytest.raises(NotFoundError):
            repository.remove_labels(999, ("Person",))

    @pytest.mark.parametrize("label", ["", None, 3])
    def test_invalid_label_rejected(
        self,
        repository: NodeRepository,
        label: object,
    ) -> None:
        with pytest.raises(ValidationError):
            repository.create((label,))  # type: ignore[arg-type]


class TestProperties(_NodeTestCase):
    """Verify property updates and snapshots."""

    def test_set_and_remove_properties(self, repository: NodeRepository) -> None:
        node = repository.create(properties={"name": "Ada", "age": 36})
        node = repository.set_properties(node.id, {"age": 37, "active": True})
        assert dict(node) == {"name": "Ada", "age": 37, "active": True}
        node = repository.set_properties(node.id, {"active": None})
        assert dict(node) == {"name": "Ada", "age": 37}
        node = repository.remove_properties(node.id, ("age", "missing"))
        assert dict(node) == {"name": "Ada"}

    def test_arbitrary_property_keys(self, repository: NodeRepository) -> None:
        properties = {"a.b": 1, "a b": 2, "$.x": 3, 'a"b': 4}
        node = repository.create(properties=properties)
        assert dict(repository.get(node.id)) == properties

    def test_earlier_snapshot_is_unchanged(self, repository: NodeRepository) -> None:
        node = repository.create(properties={"name": "Ada"})
        repository.set_properties(node.id, {"name": "Grace"})
        assert node["name"] == "Ada"
        assert repository.get(node.id)["name"] == "Grace"

    def test_snapshot_labels_are_unchanged(self, repository: NodeRepository) -> None:
        node = repository.create(("Person",))
        repository.add_labels(node.id, ("Employee",))
        assert node.labels == frozenset({"Person"})

    def test_missing_node_raises(self, repository: NodeRepository) -> None:
        with pytest.raises(NotFoundError):
            repository.set_properties(999, {"name": "Ada"})
        with pytest.raises(NotFoundError):
            repository.remove_properties(999, ("name",))

    def test_null_removes_property(self, repository: NodeRepository) -> None:
        node = repository.create(properties={"name": "Ada"})
        node = repository.set_properties(node.id, {"name": None})
        assert "name" not in node
        assert dict(repository.get(node.id)) == {}

    def test_invalid_value_rejected(self, repository: NodeRepository) -> None:
        node = repository.create()
        with pytest.raises(ValidationError):
            repository.set_properties(node.id, {"bad": typing.cast(Value, {"nested": 1})})
        with pytest.raises(ValidationError):
            repository.create(properties={"bad": [1, "a"]})

    @pytest.mark.parametrize("key", ["", None, 3])
    def test_invalid_property_key_rejected(
        self,
        repository: NodeRepository,
        key: object,
    ) -> None:
        with pytest.raises(ValidationError):
            repository.create(properties={key: 1})  # type: ignore[dict-item]


class TestFind(_NodeTestCase):
    """Verify label and property lookups."""

    def test_find_by_label_and_property(self, repository: NodeRepository) -> None:
        ada = repository.create(("Person",), {"age": 36})
        repository.create(("Person",), {"age": 30})
        repository.create(("Robot",), {"age": 36})
        found = list(repository.find(("Person",), {"age": 36}))
        assert [node.id for node in found] == [ada.id]

    def test_multiple_labels_must_all_match(self, repository: NodeRepository) -> None:
        both = repository.create(("Person", "Employee"))
        repository.create(("Person",))
        found = list(repository.find(("Person", "Employee")))
        assert [node.id for node in found] == [both.id]

    def test_no_filters_return_all_nodes(self, repository: NodeRepository) -> None:
        first = repository.create()
        second = repository.create()
        assert [node.id for node in repository.find()] == [first.id, second.id]
        assert [node.id for node in repository.all()] == [first.id, second.id]

    @pytest.mark.parametrize(
        ("stored", "queried"),
        [
            (True, 1),
            (1, 1.0),
            ("36", 36),
            (36, "36"),
            ([1, 2], [2, 1]),
        ],
    )
    def test_type_sensitive_lookup(
        self,
        repository: NodeRepository,
        stored: Value,
        queried: Value,
    ) -> None:
        repository.create(properties={"value": stored})
        assert list(repository.find(properties={"value": queried})) == []

    @pytest.mark.parametrize(
        "value",
        [True, False, 1, -1, 2.5, "text", [1, 2], [], [True, False]],
    )
    def test_exact_values_match(
        self,
        repository: NodeRepository,
        value: Value,
    ) -> None:
        node = repository.create(properties={"value": value})
        found = list(repository.find(properties={"value": value}))
        assert [item.id for item in found] == [node.id]

    def test_dotted_property_key_lookup(self, repository: NodeRepository) -> None:
        node = repository.create(properties={"a.b": 1})
        repository.create(properties={"a.b": 2})
        found = list(repository.find(properties={"a.b": 1}))
        assert [item.id for item in found] == [node.id]

    def test_invalid_filter_rejected(self, repository: NodeRepository) -> None:
        mixed = typing.cast(Value, [1, 2.0])
        with pytest.raises(ValidationError):
            list(repository.find(properties={"value": mixed}))


class TestCountAndReuse(_NodeTestCase):
    """Verify derived information used by the facade."""

    def test_is_connected_false_without_relationships(
        self,
        repository: NodeRepository,
    ) -> None:
        node = repository.create()
        assert not repository.is_connected(node.id)
