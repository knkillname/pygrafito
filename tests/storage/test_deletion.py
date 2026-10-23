# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Tests for direct, refused, and detaching deletion."""

from collections.abc import Iterator

import pytest

from pygrafito.model import (
    ConnectedNodeError,
    NotFoundError,
)
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository

type Repositories = tuple[NodeRepository, RelationshipRepository]


class _DeletionTestCase:
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


class TestRelationshipDeletion(_DeletionTestCase):
    """Verify direct relationship deletion."""

    def test_relationship_deleted_without_touching_nodes(
        self,
        repositories: Repositories,
    ) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create(("Person",))
        second = node_repository.create(("Person",))
        relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        relationship_repository.delete(relationship.id)
        assert not relationship_repository.exists(relationship.id)
        assert node_repository.get(first.id) == first
        assert node_repository.get(second.id) == second

    def test_parallel_relationships_delete_individually(
        self,
        repositories: Repositories,
    ) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        first_relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        second_relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        relationship_repository.delete(first_relationship.id)
        remaining = list(relationship_repository.all())
        assert [item.id for item in remaining] == [second_relationship.id]


class TestNodeRefusal(_DeletionTestCase):
    """Verify that connected nodes cannot be deleted without detaching."""

    def test_outgoing_connection_refused(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        with pytest.raises(ConnectedNodeError):
            node_repository.delete(first.id)
        assert node_repository.exists(first.id)
        assert relationship_repository.exists(relationship.id)

    def test_incoming_connection_refused(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        first = node_repository.create()
        second = node_repository.create()
        relationship = relationship_repository.create(first.id, "KNOWS", second.id)
        with pytest.raises(ConnectedNodeError):
            node_repository.delete(second.id)
        assert node_repository.exists(second.id)
        assert relationship_repository.exists(relationship.id)

    def test_self_loop_refused(self, repositories: Repositories) -> None:
        node_repository, relationship_repository = repositories
        node = node_repository.create()
        relationship = relationship_repository.create(node.id, "KNOWS", node.id)
        with pytest.raises(ConnectedNodeError):
            node_repository.delete(node.id)
        assert node_repository.exists(node.id)
        assert relationship_repository.exists(relationship.id)

    def test_missing_node_raises(self, repositories: Repositories) -> None:
        node_repository, _ = repositories
        with pytest.raises(NotFoundError):
            node_repository.delete(999)


class TestDetachDeletion(_DeletionTestCase):
    """Verify deletion that removes incident relationships first."""

    def test_isolated_node_deleted(self, repositories: Repositories) -> None:
        node_repository, _ = repositories
        node = node_repository.create(("Person",), {"name": "Ada"})
        node_repository.delete(node.id)
        assert not node_repository.exists(node.id)

    def test_detach_removes_incident_relationships(
        self,
        repositories: Repositories,
    ) -> None:
        node_repository, relationship_repository = repositories
        center = node_repository.create()
        outgoing = node_repository.create()
        incoming = node_repository.create()
        survivor = node_repository.create()
        outgoing_relationship = relationship_repository.create(
            center.id,
            "KNOWS",
            outgoing.id,
        )
        incoming_relationship = relationship_repository.create(
            incoming.id,
            "KNOWS",
            center.id,
        )
        self_loop = relationship_repository.create(center.id, "KNOWS", center.id)
        unrelated = relationship_repository.create(outgoing.id, "KNOWS", survivor.id)
        node_repository.delete(center.id, detach=True)
        assert not node_repository.exists(center.id)
        assert not relationship_repository.exists(outgoing_relationship.id)
        assert not relationship_repository.exists(incoming_relationship.id)
        assert not relationship_repository.exists(self_loop.id)
        assert relationship_repository.exists(unrelated.id)
        assert node_repository.exists(outgoing.id)
        assert node_repository.exists(incoming.id)
        assert node_repository.exists(survivor.id)

    def test_detach_on_isolated_node(self, repositories: Repositories) -> None:
        node_repository, _ = repositories
        node = node_repository.create()
        node_repository.delete(node.id, detach=True)
        assert not node_repository.exists(node.id)

    def test_labels_removed_with_node(self, repositories: Repositories) -> None:
        node_repository, _ = repositories
        node = node_repository.create(("Person", "Employee"))
        node_repository.delete(node.id)
        assert list(node_repository.find(("Person",))) == []
