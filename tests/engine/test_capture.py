# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for bounded traversal region capture."""

from collections.abc import Iterable, Iterator

import pytest

from pygrafito.engine.traversal import AdjacencySnapshot, TraversalCapture
from pygrafito.model import Direction, NotFoundError, ValidationError
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository

type Repositories = tuple[NodeRepository, RelationshipRepository]


class _CaptureTestCase:
    """Provide a themed graph and a capture over it."""

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

    @staticmethod
    def relationships_in(snapshot: AdjacencySnapshot, node_ids: Iterable[int]) -> set[int]:
        """Return every captured relationship incident to the given nodes.

        Parameters
        ----------
        snapshot : AdjacencySnapshot
            Captured region.
        node_ids : Iterable[int]
            Nodes known to be inside the region.

        Returns
        -------
        set[int]
            Identifiers of the captured relationships.
        """
        found: set[int] = set()
        for node_id in node_ids:
            for relationship, _ in snapshot.edges(node_id, Direction.OUTGOING, None):
                found.add(relationship.id)
            for relationship, _ in snapshot.edges(node_id, Direction.INCOMING, None):
                found.add(relationship.id)
        return found

    @staticmethod
    def present(snapshot: AdjacencySnapshot, node_ids: Iterable[int]) -> set[int]:
        """Return the given node ids that the snapshot contains.

        Parameters
        ----------
        snapshot : AdjacencySnapshot
            Captured region.
        node_ids : Iterable[int]
            Candidate identifiers.

        Returns
        -------
        set[int]
            Identifiers present in the snapshot.
        """
        return {node_id for node_id in node_ids if snapshot.contains(node_id)}


class TestBoundedRegion(_CaptureTestCase):
    """Verify the captured region stops exactly at the depth bound."""

    def test_diamond(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        start = nodes.create(("Grid",))
        left = nodes.create(("Safehouse",))
        right = nodes.create(("Outlands",))
        end = nodes.create(("Portal",))
        first = relationships.create(start.id, "GRID_LINK", left.id)
        second = relationships.create(start.id, "GRID_LINK", right.id)
        third = relationships.create(left.id, "GRID_LINK", end.id)
        fourth = relationships.create(right.id, "GRID_LINK", end.id)
        capture = TraversalCapture(nodes, relationships)

        shallow = capture.region(start, max_depth=1)
        assert self.present(shallow, (start.id, left.id, right.id, end.id)) == {
            start.id,
            left.id,
            right.id,
        }
        assert self.relationships_in(shallow, (start.id,)) == {first.id, second.id}

        deep = capture.region(start, max_depth=2)
        assert self.present(deep, (start.id, left.id, right.id, end.id)) == {
            start.id,
            left.id,
            right.id,
            end.id,
        }
        assert self.relationships_in(
            deep,
            (start.id, left.id, right.id, end.id),
        ) == {first.id, second.id, third.id, fourth.id}

    def test_directed_cycle(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        first = nodes.create(("Program",))
        second = nodes.create(("Program",))
        third = nodes.create(("Program",))
        first_link = relationships.create(first.id, "LOOP", second.id)
        second_link = relationships.create(second.id, "LOOP", third.id)
        third_link = relationships.create(third.id, "LOOP", first.id)
        capture = TraversalCapture(nodes, relationships)

        bounded = capture.region(first, max_depth=2)
        assert self.present(bounded, (first.id, second.id, third.id)) == {
            first.id,
            second.id,
            third.id,
        }
        assert self.relationships_in(bounded, (first.id, second.id, third.id)) == {
            first_link.id,
            second_link.id,
        }

        complete = capture.region(first, max_depth=3)
        assert self.relationships_in(complete, (first.id, second.id, third.id)) == {
            first_link.id,
            second_link.id,
            third_link.id,
        }

    def test_parallel_relationships(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        start = nodes.create(("Grid",))
        end = nodes.create(("Portal",))
        first = relationships.create(start.id, "GRID_LINK", end.id)
        second = relationships.create(start.id, "GRID_LINK", end.id)
        capture = TraversalCapture(nodes, relationships)
        region = capture.region(start, max_depth=1)
        assert self.relationships_in(region, (start.id, end.id)) == {first.id, second.id}

    def test_self_loop(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        tron = nodes.create(("Program",))
        quorra = nodes.create(("Program",))
        loop = relationships.create(tron.id, "CYCLE", tron.id)
        link = relationships.create(tron.id, "ALLIES_WITH", quorra.id)
        capture = TraversalCapture(nodes, relationships)
        region = capture.region(tron, max_depth=1, direction=Direction.BOTH)
        assert self.relationships_in(region, (tron.id, quorra.id)) == {loop.id, link.id}

    def test_unreachable_region_is_absent(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        start = nodes.create(("Grid",))
        island = nodes.create(("Outlands",))
        relationships.create(island.id, "GRID_LINK", island.id)
        capture = TraversalCapture(nodes, relationships)
        region = capture.region(start, max_depth=3)
        assert self.present(region, (start.id, island.id)) == {start.id}

    def test_included_node_is_present(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        start = nodes.create(("Grid",))
        island = nodes.create(("Outlands",))
        capture = TraversalCapture(nodes, relationships)
        region = capture.region(start, max_depth=1, include=(island.id,))
        assert self.present(region, (start.id, island.id)) == {start.id, island.id}
        assert self.relationships_in(region, (start.id, island.id)) == set()

    def test_missing_start_raises(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        capture = TraversalCapture(nodes, relationships)
        with pytest.raises(NotFoundError):
            capture.region(999, max_depth=1)

    def test_missing_included_node_raises(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        start = nodes.create(("Grid",))
        capture = TraversalCapture(nodes, relationships)
        with pytest.raises(NotFoundError):
            capture.region(start, max_depth=1, include=(999,))

    def test_invalid_depth_raises(self, repositories: Repositories) -> None:
        nodes, relationships = repositories
        start = nodes.create(("Grid",))
        capture = TraversalCapture(nodes, relationships)
        with pytest.raises(ValidationError, match="max_depth"):
            capture.region(start, max_depth=-1)
