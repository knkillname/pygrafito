# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
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
        node = repository.create(("Program", "ISO"), {"designation": "Kevin Flynn"})
        assert node.id > 0
        assert node.labels == frozenset({"Program", "ISO"})
        assert node["designation"] == "Kevin Flynn"

    def test_defaults_are_empty(self, repository: NodeRepository) -> None:
        node = repository.create()
        assert node.labels == frozenset()
        assert dict(node) == {}
        assert repository.get(node.id) == node

    def test_duplicate_labels_are_collapsed(self, repository: NodeRepository) -> None:
        node = repository.create(("Program", "Program"))
        assert node.labels == frozenset({"Program"})

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
        node = repository.create(("Program", "ISO"))
        node = repository.add_labels(node.id, ("SystemMonitor",))
        assert node.labels == frozenset({"Program", "ISO", "SystemMonitor"})
        node = repository.remove_labels(node.id, ("ISO",))
        assert node.labels == frozenset({"Program", "SystemMonitor"})
        node = repository.remove_labels(node.id, ("Missing",))
        assert node.labels == frozenset({"Program", "SystemMonitor"})

    def test_add_labels_is_idempotent(self, repository: NodeRepository) -> None:
        node = repository.create(("Program",))
        node = repository.add_labels(node.id, ("Program",))
        assert node.labels == frozenset({"Program"})

    def test_missing_node_raises(self, repository: NodeRepository) -> None:
        with pytest.raises(NotFoundError):
            repository.add_labels(999, ("Program",))
        with pytest.raises(NotFoundError):
            repository.remove_labels(999, ("Program",))

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
        node = repository.create(properties={"designation": "Kevin Flynn", "cycles": 36})
        node = repository.set_properties(node.id, {"cycles": 37, "active": True})
        assert dict(node) == {"designation": "Kevin Flynn", "cycles": 37, "active": True}
        node = repository.set_properties(node.id, {"active": None})
        assert dict(node) == {"designation": "Kevin Flynn", "cycles": 37}
        node = repository.remove_properties(node.id, ("cycles", "missing"))
        assert dict(node) == {"designation": "Kevin Flynn"}

    def test_arbitrary_property_keys(self, repository: NodeRepository) -> None:
        properties = {"a.b": 1, "a b": 2, "$.x": 3, 'a"b': 4}
        node = repository.create(properties=properties)
        assert dict(repository.get(node.id)) == properties

    def test_earlier_snapshot_is_unchanged(self, repository: NodeRepository) -> None:
        node = repository.create(properties={"designation": "Kevin Flynn"})
        repository.set_properties(node.id, {"designation": "Quorra"})
        assert node["designation"] == "Kevin Flynn"
        assert repository.get(node.id)["designation"] == "Quorra"

    def test_snapshot_labels_are_unchanged(self, repository: NodeRepository) -> None:
        node = repository.create(("Program",))
        repository.add_labels(node.id, ("ISO",))
        assert node.labels == frozenset({"Program"})

    def test_missing_node_raises(self, repository: NodeRepository) -> None:
        with pytest.raises(NotFoundError):
            repository.set_properties(999, {"designation": "Kevin Flynn"})
        with pytest.raises(NotFoundError):
            repository.remove_properties(999, ("designation",))

    def test_null_removes_property(self, repository: NodeRepository) -> None:
        node = repository.create(properties={"designation": "Kevin Flynn"})
        node = repository.set_properties(node.id, {"designation": None})
        assert "designation" not in node
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
        ada = repository.create(("Program",), {"cycles": 36})
        repository.create(("Program",), {"cycles": 30})
        repository.create(("SystemMonitor",), {"cycles": 36})
        found = list(repository.find(("Program",), {"cycles": 36}))
        assert [node.id for node in found] == [ada.id]

    def test_multiple_labels_must_all_match(self, repository: NodeRepository) -> None:
        both = repository.create(("Program", "ISO"))
        repository.create(("Program",))
        found = list(repository.find(("Program", "ISO")))
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


class TestFindPredicateShape:
    """Verify node property predicates embed the JSON path as a literal."""

    def test_property_path_is_inlined(self) -> None:
        database = Database(":memory:")
        try:
            repository = NodeRepository(database.connection, PropertyCodec())
            node = repository.create(("Program",), {"cycles": 36})
            statements: list[str] = []
            database.connection.set_trace_callback(statements.append)
            try:
                found = list(repository.find(("Program",), {"cycles": 36}))
            finally:
                database.connection.set_trace_callback(None)
            assert [item.id for item in found] == [node.id]
            lookup = next(statement for statement in statements if "json_extract" in statement)
            assert "json_extract(nodes.props, '$.\"cycles\"') = 36" in lookup
            assert "json_type(nodes.props, '$.\"cycles\"')" in lookup
            assert "?" not in lookup
        finally:
            database.close()


class TestCountAndReuse(_NodeTestCase):
    """Verify derived information used by the facade."""

    def test_is_connected_false_without_relationships(
        self,
        repository: NodeRepository,
    ) -> None:
        node = repository.create()
        assert not repository.is_connected(node.id)


class TestBatchChunking:
    """Verify wide batches are split without losing nodes."""

    def test_wide_batch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(NodeRepository, "MAXIMUM_PARAMETERS", 3)
        database = Database(":memory:")
        try:
            repository = NodeRepository(database.connection, PropertyCodec())
            created = [repository.create(("Program",), {"cycles": index}) for index in range(8)]
            loaded = repository.get_many(node.id for node in created)
            assert set(loaded) == {node.id for node in created}
            assert [loaded[node.id]["cycles"] for node in created] == list(range(8))
        finally:
            database.close()
