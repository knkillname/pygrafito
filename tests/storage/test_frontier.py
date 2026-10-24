# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for ordered adjacency-frontier reads."""

from collections.abc import Iterator

import pytest

from pygrafito.model import Direction
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository

type Repositories = tuple[NodeRepository, RelationshipRepository]


class _FrontierTestCase:
    """Provide a themed graph with parallel edges and self-loops."""

    @pytest.fixture
    def repositories(self) -> Iterator[Repositories]:
        """Yield repositories sharing one in-memory database.

        Yields
        ------
        Repositories
            Node and relationship repositories.
        """
        database = Database(":memory:")
        try:
            codec = PropertyCodec()
            yield (
                NodeRepository(database.connection, codec),
                RelationshipRepository(database.connection, codec),
            )
        finally:
            database.close()


class TestDirections(_FrontierTestCase):
    """Verify adjacency is read in the requested direction."""

    def test_outgoing(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        kevin = nodes.create(("Program",))
        quorra = nodes.create(("Program",))
        tron = nodes.create(("Program",))
        first = relationships.create(kevin.id, "ALLIES_WITH", quorra.id)
        second = relationships.create(kevin.id, "TRANSMISSION", tron.id)
        third = relationships.create(quorra.id, "ALLIES_WITH", tron.id)
        edges = list(relationships.frontier((kevin.id, quorra.id), Direction.OUTGOING))
        assert [(node_id, item.id, target) for node_id, item, target in edges] == [
            (kevin.id, first.id, quorra.id),
            (kevin.id, second.id, tron.id),
            (quorra.id, third.id, tron.id),
        ]

    def test_incoming(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        kevin = nodes.create(("Program",))
        quorra = nodes.create(("Program",))
        tron = nodes.create(("Program",))
        first = relationships.create(kevin.id, "ALLIES_WITH", quorra.id)
        second = relationships.create(quorra.id, "ALLIES_WITH", tron.id)
        third = relationships.create(kevin.id, "TRANSMISSION", tron.id)
        edges = list(relationships.frontier((quorra.id, tron.id), Direction.INCOMING))
        assert [(node_id, item.id, target) for node_id, item, target in edges] == [
            (quorra.id, first.id, kevin.id),
            (tron.id, second.id, quorra.id),
            (tron.id, third.id, kevin.id),
        ]

    def test_both_emits_self_loop_once(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        quorra = nodes.create(("Program",))
        tron = nodes.create(("Program",))
        loop = relationships.create(tron.id, "TRANSMISSION", tron.id)
        incoming = relationships.create(quorra.id, "ALLIES_WITH", tron.id)
        outgoing = relationships.create(tron.id, "ALLIES_WITH", quorra.id)
        edges = list(relationships.frontier((tron.id,), Direction.BOTH))
        assert [(node_id, item.id, target) for node_id, item, target in edges] == [
            (tron.id, loop.id, tron.id),
            (tron.id, outgoing.id, quorra.id),
            (tron.id, incoming.id, quorra.id),
        ]

    def test_incoming_keeps_self_loop(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        tron = nodes.create(("Program",))
        loop = relationships.create(tron.id, "TRANSMISSION", tron.id)
        edges = list(relationships.frontier((tron.id,), Direction.INCOMING))
        assert [(node_id, item.id, target) for node_id, item, target in edges] == [
            (tron.id, loop.id, tron.id)
        ]


class TestFiltering(_FrontierTestCase):
    """Verify type filtering and frontier normalization."""

    def test_type_filter(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        quorra = nodes.create(("Program",))
        tron = nodes.create(("Program",))
        allies = relationships.create(quorra.id, "ALLIES_WITH", tron.id)
        relationships.create(quorra.id, "TRANSMISSION", tron.id)
        edges = list(
            relationships.frontier((quorra.id,), Direction.OUTGOING, frozenset({"ALLIES_WITH"}))
        )
        assert [(item.id, target) for _, item, target in edges] == [(allies.id, tron.id)]

    def test_empty_frontier(self, repositories: Repositories) -> None:
        _, relationships = repositories
        assert list(relationships.frontier((), Direction.BOTH)) == []

    def test_duplicate_frontier_is_collapsed(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        kevin = nodes.create(("Program",))
        quorra = nodes.create(("Program",))
        relationships.create(kevin.id, "ALLIES_WITH", quorra.id)
        edges = list(relationships.frontier((kevin.id, kevin.id), Direction.OUTGOING))
        assert len(edges) == 1


class TestChunking(_FrontierTestCase):
    """Verify wide frontiers are split without changing order."""

    def test_wide_frontier(
        self,
        repositories: Repositories,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(RelationshipRepository, "MAXIMUM_PARAMETERS", 3)
        nodes, relationships = repositories
        created = [nodes.create(("Program",)) for _ in range(8)]
        links = [
            relationships.create(created[index].id, "ALLIES_WITH", created[index + 1].id)
            for index in range(len(created) - 1)
        ]
        edges = list(relationships.frontier(tuple(node.id for node in created), Direction.OUTGOING))
        assert [(node_id, item.id, target) for node_id, item, target in edges] == [
            (created[index].id, links[index].id, created[index + 1].id)
            for index in range(len(links))
        ]
