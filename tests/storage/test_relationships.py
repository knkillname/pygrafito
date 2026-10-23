# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Tests for relationship persistence, properties, and lookups."""

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
from pygrafito.storage.relationships import RelationshipRepository

type Repositories = tuple[NodeRepository, RelationshipRepository]


class _RelationshipTestCase:
    """Provide node and relationship repositories on an in-memory graph."""

    @pytest.fixture
    def repositories(self) -> Iterator[Repositories]:
        """Return repositories sharing one in-memory database.

        Yields
        ------
        Repositories
            Node and relationship repositories.
        """
        database = Database(":memory:")
        try:
            property_codec = PropertyCodec()
            yield (
                NodeRepository(database.connection, property_codec),
                RelationshipRepository(database.connection, property_codec),
            )
        finally:
            database.close()


class TestCreateAndGet(_RelationshipTestCase):
    """Verify relationship creation and reading."""

    def test_create_and_get(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        start = node_repository.create(("Person",))
        end = node_repository.create(("Person",))
        created = relationship_repository.create(start.id, "KNOWS", end.id, {"since": 2020})
        loaded = relationship_repository.get(created.id)
        assert loaded == created
        assert loaded.rel_type == "KNOWS"
        assert loaded.start_id == start.id
        assert loaded.end_id == end.id
        assert loaded["since"] == 2020

    def test_stored_direction_is_preserved(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "FOLLOWS", second.id)
        loaded = relationship_repository.get(relationship.id)
        assert loaded.start_id == first.id
        assert loaded.end_id == second.id

    def test_self_loop_is_stored(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        node = node_repository.create()
        relationship = relationship_repository.create(node.id, "KNOWS", node.id)
        loaded = relationship_repository.get(relationship.id)
        assert loaded.start_id == node.id
        assert loaded.end_id == node.id

    def test_missing_endpoint_creates_nothing(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        node = node_repository.create()
        with pytest.raises(NotFoundError):
            relationship_repository.create(node.id, "KNOWS", node.id + 1)
        with pytest.raises(NotFoundError):
            relationship_repository.create(node.id + 1, "KNOWS", node.id)
        assert list(relationship_repository.all()) == []

    def test_invalid_type_rejected(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        with pytest.raises(ValidationError):
            relationship_repository.create(first.id, "", second.id)

    def test_missing_relationship_raises(self, repositories: Repositories) -> None:
        _, relationship_repository = repositories
        with pytest.raises(NotFoundError):
            relationship_repository.get(999)

    def test_exists(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        assert relationship_repository.exists(relationship.id)
        assert not relationship_repository.exists(relationship.id + 1)

    def test_ids_are_distinct(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        first_relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        second_relationship = relationship_repository.create(second.id, "KNOWS", first.id)
        assert first_relationship.id != second_relationship.id


class TestProperties(_RelationshipTestCase):
    """Verify relationship property updates."""

    def test_set_and_remove_properties(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        relationship = relationship_repository.set_properties(
            relationship.id,
            {"since": 2020, "weight": 2.5},
        )
        assert dict(relationship) == {"since": 2020, "weight": 2.5}
        relationship = relationship_repository.set_properties(
            relationship.id,
            {"weight": None},
        )
        assert dict(relationship) == {"since": 2020}
        relationship = relationship_repository.remove_properties(relationship.id, ("since",))
        assert dict(relationship) == {}

    def test_earlier_snapshot_is_unchanged(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(
            first.id,
            "KNOWS",
            second.id,
            {"since": 2020},
        )
        relationship_repository.set_properties(relationship.id, {"since": 2021})
        assert relationship["since"] == 2020

    def test_missing_relationship_raises(self, repositories: Repositories) -> None:
        _, relationship_repository = repositories
        with pytest.raises(NotFoundError):
            relationship_repository.set_properties(999, {"since": 2020})
        with pytest.raises(NotFoundError):
            relationship_repository.remove_properties(999, ("since",))

    def test_invalid_value_rejected(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        with pytest.raises(ValidationError):
            relationship_repository.set_properties(relationship.id, {"bad": [1, "a"]})


class TestFind(_RelationshipTestCase):
    """Verify relationship lookups."""

    def test_find_by_type(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        knows = relationship_repository.create(first.id, "KNOWS", second.id)
        relationship_repository.create(first.id, "LIKES", second.id)
        found = list(relationship_repository.find("KNOWS"))
        assert [item.id for item in found] == [knows.id]

    def test_find_by_type_and_property(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        matching = relationship_repository.create(
            first.id,
            "KNOWS",
            second.id,
            {"since": 2020},
        )
        relationship_repository.create(first.id, "KNOWS", second.id, {"since": 2019})
        found = list(relationship_repository.find("KNOWS", {"since": 2020}))
        assert [item.id for item in found] == [matching.id]

    def test_all_relationships(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        first_relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        second_relationship = relationship_repository.create(second.id, "LIKES", first.id)
        assert [item.id for item in relationship_repository.all()] == [
            first_relationship.id,
            second_relationship.id,
        ]

    @pytest.mark.parametrize(
        ("stored", "queried"),
        [
            (True, 1),
            (1, 1.0),
            ("2020", 2020),
            ([1, 2], [2, 1]),
        ],
    )
    def test_type_sensitive_lookup(
        self,
        repositories: Repositories,
        stored: Value,
        queried: Value,
    ) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship_repository.create(first.id, "KNOWS", second.id, {"value": stored})
        assert list(relationship_repository.find(properties={"value": queried})) == []

    def test_invalid_type_filter_rejected(self, repositories: Repositories) -> None:
        _, relationship_repository = repositories
        with pytest.raises(ValidationError):
            list(relationship_repository.find(""))


class TestDelete(_RelationshipTestCase):
    """Verify direct relationship deletion."""

    def test_delete(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        relationship_repository.delete(relationship.id)
        assert not relationship_repository.exists(relationship.id)
        assert list(relationship_repository.all()) == []

    def test_missing_relationship_raises(self, repositories: Repositories) -> None:
        _, relationship_repository = repositories
        with pytest.raises(NotFoundError):
            relationship_repository.delete(999)

    def test_incident_deletion_counts_self_loop_once(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        node = node_repository.create()
        relationship_repository.create(node.id, "KNOWS", node.id)
        assert relationship_repository.delete_incident(node.id) == 1
        assert list(relationship_repository.all()) == []

    def test_connected_lookup(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        assert not relationship_repository.is_connected(first.id)
        relationship_repository.create(first.id, "KNOWS", second.id)
        assert relationship_repository.is_connected(first.id)
        assert relationship_repository.is_connected(second.id)
