# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the live traversal neighborhood source."""

from collections.abc import Iterator

import pytest

from pygrafito.engine.traversal import DatabaseNeighborhood
from pygrafito.model import Direction, NotFoundError
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository

type Repositories = tuple[NodeRepository, RelationshipRepository]


class _NeighborhoodTestCase:
    """Provide a themed graph and a live neighborhood over it."""

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


class TestLookups(_NeighborhoodTestCase):
    """Verify node lookups delegate to the repository."""

    def test_contains(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        assert neighborhood.contains(quorra.id)
        assert not neighborhood.contains(999)

    def test_node(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        assert neighborhood.node(quorra.id) == quorra
        with pytest.raises(NotFoundError):
            neighborhood.node(999)

    def test_nodes(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        tron = nodes.create(("Program",), {"designation": "Tron"})
        loaded = neighborhood.nodes([quorra.id, tron.id, 999])
        assert loaded == {quorra.id: quorra, tron.id: tron}


class TestEdges(_NeighborhoodTestCase):
    """Verify single-node adjacency reads for open walks."""

    def test_outgoing_edges(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        kevin = nodes.create(("Program",), {"designation": "Kevin Flynn"})
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        edge = relationships.create(kevin.id, "TRUSTS", quorra.id)
        edges = list(neighborhood.edges(kevin.id, Direction.OUTGOING, None))
        assert [(item.id, target) for item, target in edges] == [(edge.id, quorra.id)]

    def test_incoming_direction(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        kevin = nodes.create(("Program",), {"designation": "Kevin Flynn"})
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        edge = relationships.create(kevin.id, "TRUSTS", quorra.id)
        edges = list(neighborhood.edges(quorra.id, Direction.INCOMING, None))
        assert [(item.id, target) for item, target in edges] == [(edge.id, kevin.id)]

    def test_label_filter(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        tron = nodes.create(("Program",), {"designation": "Tron"})
        allies = relationships.create(quorra.id, "ALLIES_WITH", tron.id)
        relationships.create(quorra.id, "TRANSMISSION", tron.id)
        edges = list(neighborhood.edges(quorra.id, Direction.OUTGOING, frozenset({"ALLIES_WITH"})))
        assert [(item.id, target) for item, target in edges] == [(allies.id, tron.id)]

    def test_undirected_edge_is_followed_from_both_ends(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        kevin = nodes.create(("Program",), {"designation": "Kevin Flynn"})
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        edge = relationships.create(kevin.id, "ALLIES_WITH", quorra.id, directed=False)
        forward = list(neighborhood.edges(kevin.id, Direction.BOTH, None))
        backward = list(neighborhood.edges(quorra.id, Direction.BOTH, None))
        assert [(item.id, target) for item, target in forward] == [(edge.id, quorra.id)]
        assert [(item.id, target) for item, target in backward] == [(edge.id, kevin.id)]

    def test_self_loop_is_emitted_once(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        tron = nodes.create(("Program",), {"designation": "Tron"})
        loop = relationships.create(tron.id, "MONITORS", tron.id)
        edges = list(neighborhood.edges(tron.id, Direction.BOTH, None))
        assert [(item.id, target) for item, target in edges] == [(loop.id, tron.id)]

    def test_missing_node_has_no_edges(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        assert list(neighborhood.edges(999, Direction.BOTH, None)) == []


class TestFrontier(_NeighborhoodTestCase):
    """Verify frontier reads keep database ordering and self-loop rules."""

    def test_outgoing_order(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        kevin = nodes.create(("Program",), {"designation": "Kevin Flynn"})
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        tron = nodes.create(("Program",), {"designation": "Tron"})
        first = relationships.create(kevin.id, "ALLIES_WITH", quorra.id)
        second = relationships.create(kevin.id, "TRANSMISSION", tron.id)
        edges = list(neighborhood.frontier_edges((kevin.id,), Direction.OUTGOING, None))
        assert [(node_id, item.id, target) for node_id, item, target in edges] == [
            (kevin.id, first.id, quorra.id),
            (kevin.id, second.id, tron.id),
        ]

    def test_both_emits_self_loop_once(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        tron = nodes.create(("Program",), {"designation": "Tron"})
        loop = relationships.create(tron.id, "TRANSMISSION", tron.id)
        edges = list(neighborhood.frontier_edges((tron.id,), Direction.BOTH, None))
        assert [(node_id, item.id, target) for node_id, item, target in edges] == [
            (tron.id, loop.id, tron.id)
        ]

    def test_type_filter(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        neighborhood = DatabaseNeighborhood(nodes, relationships)
        quorra = nodes.create(("Program",), {"designation": "Quorra"})
        tron = nodes.create(("Program",), {"designation": "Tron"})
        allies = relationships.create(quorra.id, "ALLIES_WITH", tron.id)
        relationships.create(quorra.id, "TRANSMISSION", tron.id)
        edges = list(
            neighborhood.frontier_edges(
                (quorra.id,),
                Direction.OUTGOING,
                frozenset({"ALLIES_WITH"}),
            )
        )
        assert [(item.id, target) for _, item, target in edges] == [(allies.id, tron.id)]
