# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for relationship persistence, properties, and lookups."""

import math
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
        start = node_repository.create(("Program",))
        end = node_repository.create(("Program",))
        created = relationship_repository.create(
            start.id,
            "ALLIES_WITH",
            end.id,
            {"since_cycle": 2020},
        )
        loaded = relationship_repository.get(created.id)
        assert loaded == created
        assert loaded.labels == ("ALLIES_WITH",)
        assert loaded.directed is True
        assert loaded.start_id == start.id
        assert loaded.end_id == end.id
        assert loaded["since_cycle"] == 2020

    def test_stored_direction_is_preserved(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "TRACKS", second.id)
        loaded = relationship_repository.get(relationship.id)
        assert loaded.start_id == first.id
        assert loaded.end_id == second.id

    def test_self_loop_is_stored(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        node = node_repository.create()
        relationship = relationship_repository.create(node.id, "ALLIES_WITH", node.id)
        loaded = relationship_repository.get(relationship.id)
        assert loaded.start_id == node.id
        assert loaded.end_id == node.id

    def test_missing_endpoint_creates_nothing(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        node = node_repository.create()
        with pytest.raises(NotFoundError):
            relationship_repository.create(node.id, "ALLIES_WITH", node.id + 1)
        with pytest.raises(NotFoundError):
            relationship_repository.create(node.id + 1, "ALLIES_WITH", node.id)
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
        relationship = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        assert relationship_repository.exists(relationship.id)
        assert not relationship_repository.exists(relationship.id + 1)

    def test_ids_are_distinct(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        first_relationship = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        second_relationship = relationship_repository.create(second.id, "ALLIES_WITH", first.id)
        assert first_relationship.id != second_relationship.id


class TestProperties(_RelationshipTestCase):
    """Verify relationship property updates."""

    def test_set_and_remove_properties(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        relationship = relationship_repository.set_properties(
            relationship.id,
            {"since_cycle": 2020, "weight": 2.5},
        )
        assert dict(relationship) == {"since_cycle": 2020, "weight": 2.5}
        relationship = relationship_repository.set_properties(
            relationship.id,
            {"weight": None},
        )
        assert dict(relationship) == {"since_cycle": 2020}
        relationship = relationship_repository.remove_properties(relationship.id, ("since_cycle",))
        assert dict(relationship) == {}

    def test_earlier_snapshot_is_unchanged(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(
            first.id,
            "ALLIES_WITH",
            second.id,
            {"since_cycle": 2020},
        )
        relationship_repository.set_properties(relationship.id, {"since_cycle": 2021})
        assert relationship["since_cycle"] == 2020

    def test_missing_relationship_raises(self, repositories: Repositories) -> None:
        _, relationship_repository = repositories
        with pytest.raises(NotFoundError):
            relationship_repository.set_properties(999, {"since_cycle": 2020})
        with pytest.raises(NotFoundError):
            relationship_repository.remove_properties(999, ("since_cycle",))

    def test_invalid_value_rejected(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        with pytest.raises(ValidationError):
            relationship_repository.set_properties(relationship.id, {"bad": [1, "a"]})


class TestFind(_RelationshipTestCase):
    """Verify relationship lookups."""

    def test_find_by_type(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        knows = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        relationship_repository.create(first.id, "TRUSTS", second.id)
        found = list(relationship_repository.find("ALLIES_WITH"))
        assert [item.id for item in found] == [knows.id]

    def test_find_by_type_and_property(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        matching = relationship_repository.create(
            first.id,
            "ALLIES_WITH",
            second.id,
            {"since_cycle": 2020},
        )
        relationship_repository.create(first.id, "ALLIES_WITH", second.id, {"since_cycle": 2019})
        found = list(relationship_repository.find("ALLIES_WITH", {"since_cycle": 2020}))
        assert [item.id for item in found] == [matching.id]

    @pytest.mark.parametrize("key", ['a"b', "a\nb"])
    def test_find_by_special_property_key(self, repositories: Repositories, key: str) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        matching = relationship_repository.create(
            first.id,
            "ALLIES_WITH",
            second.id,
            {key: "Tron"},
        )
        relationship_repository.create(first.id, "ALLIES_WITH", second.id, {key: "Clu"})
        found = list(relationship_repository.find("ALLIES_WITH", {key: "Tron"}))
        assert [item.id for item in found] == [matching.id]

    def test_all_relationships(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        first_relationship = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        second_relationship = relationship_repository.create(second.id, "TRUSTS", first.id)
        assert [item.id for item in relationship_repository.all()] == [
            first_relationship.id,
            second_relationship.id,
        ]

    def test_real_values_match_exactly(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        value = 1.6287812207021506e-109
        neighbor = math.nextafter(value, math.inf)
        matching = relationship_repository.create(
            first.id,
            "ALLIES_WITH",
            second.id,
            {"weight": value},
        )
        relationship_repository.create(
            first.id,
            "ALLIES_WITH",
            second.id,
            {"weight": neighbor},
        )
        found = list(relationship_repository.find("ALLIES_WITH", {"weight": value}))
        assert [item.id for item in found] == [matching.id]

    def test_real_value_matches_a_special_key(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        key = 'a"b'
        value = 2.7710821668887726e-173
        matching = relationship_repository.create(
            first.id,
            "ALLIES_WITH",
            second.id,
            {key: value},
        )
        relationship_repository.create(
            first.id,
            "ALLIES_WITH",
            second.id,
            {key: math.nextafter(value, math.inf)},
        )
        found = list(relationship_repository.find("ALLIES_WITH", {key: value}))
        assert [item.id for item in found] == [matching.id]

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
        relationship_repository.create(first.id, "ALLIES_WITH", second.id, {"value": stored})
        assert list(relationship_repository.find(properties={"value": queried})) == []

    def test_invalid_type_filter_rejected(self, repositories: Repositories) -> None:
        _, relationship_repository = repositories
        with pytest.raises(ValidationError):
            list(relationship_repository.find(""))


class TestLabelsAndDirection(_RelationshipTestCase):
    """Verify label sets, direction, and relationship label mutation."""

    def test_create_undirected_multi_label(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(
            first.id,
            ["TRUSTS", "ALLIES_WITH"],
            second.id,
            directed=False,
        )
        assert relationship.labels == ("ALLIES_WITH", "TRUSTS")
        assert relationship.directed is False
        assert relationship_repository.get(relationship.id) == relationship

    def test_add_and_remove_labels(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, (), second.id)
        added = relationship_repository.add_labels(relationship.id, ("TRUSTS", "ISO"))
        assert added.labels == ("ISO", "TRUSTS")
        removed = relationship_repository.remove_labels(added.id, ("TRUSTS",))
        assert removed.labels == ("ISO",)

    def test_find_by_labels_and_direction(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        both = relationship_repository.create(
            first.id,
            ["ALLIES_WITH", "TRUSTS"],
            second.id,
            directed=False,
        )
        relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        found = list(
            relationship_repository.find(
                ("ALLIES_WITH", "TRUSTS"),
                directed=False,
            )
        )
        assert [item.id for item in found] == [both.id]
        assert list(relationship_repository.find(directed=True))

    def test_ids_are_not_reused(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        relationship_repository.delete(relationship.id)
        replacement = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        assert replacement.id > relationship.id


class TestFindPredicateShape:
    """Verify relationship property predicates embed the JSON path as a literal."""

    def test_property_path_is_inlined(self) -> None:
        database = Database(":memory:")
        try:
            codec = PropertyCodec()
            node_repository = NodeRepository(database.connection, codec)
            relationship_repository = RelationshipRepository(database.connection, codec)
            first = node_repository.create()
            second = node_repository.create()
            relationship = relationship_repository.create(
                first.id,
                "ALLIES_WITH",
                second.id,
                {"since_cycle": 2020},
            )
            statements: list[str] = []
            database.connection.set_trace_callback(statements.append)
            try:
                found = list(relationship_repository.find("ALLIES_WITH", {"since_cycle": 2020}))
            finally:
                database.connection.set_trace_callback(None)
            assert [item.id for item in found] == [relationship.id]
            lookup = next(statement for statement in statements if "json_extract" in statement)
            assert "json_extract(relationships.props, '$.\"since_cycle\"') = 2020" in lookup
            assert "json_type(relationships.props, '$.\"since_cycle\"')" in lookup
            assert "?" not in lookup
        finally:
            database.close()


class TestDelete(_RelationshipTestCase):
    """Verify direct relationship deletion."""

    def test_delete(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "ALLIES_WITH", second.id)
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
        relationship_repository.create(node.id, "ALLIES_WITH", node.id)
        assert relationship_repository.delete_incident(node.id) == 1
        assert list(relationship_repository.all()) == []

    def test_connected_lookup(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        assert not relationship_repository.is_connected(first.id)
        relationship_repository.create(first.id, "ALLIES_WITH", second.id)
        assert relationship_repository.is_connected(first.id)
        assert relationship_repository.is_connected(second.id)
