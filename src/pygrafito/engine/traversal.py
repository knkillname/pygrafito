# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Traversal snapshots and evaluators."""

import collections
import typing
from collections.abc import Iterable, Iterator, Sequence

from pygrafito.model import (
    Direction,
    Node,
    NotFoundError,
    Path,
    Relationship,
    TraversalStep,
    ValidationError,
)
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository


class TraversalSupport:
    """Shared validation and conversion helpers for traversal requests."""

    @staticmethod
    def node_id(element: Node | int) -> int:
        """Extract a node id from a snapshot or integer.

        Parameters
        ----------
        element : Node | int
            Node snapshot or id.

        Returns
        -------
        int
            Identifier of the node.

        Raises
        ------
        ValidationError
            If the argument is not a node snapshot or integer id.
        """
        if isinstance(element, Node):
            return element.id
        if isinstance(element, int) and not isinstance(element, bool):
            return element
        message = "node must be a Node snapshot or integer id"
        raise ValidationError(message)

    @staticmethod
    def validate_direction(direction: Direction) -> None:
        """Validate a traversal direction.

        Parameters
        ----------
        direction : Direction
            Direction to validate.

        Raises
        ------
        ValidationError
            If the direction is not a Direction member.
        """
        if not isinstance(direction, Direction):
            message = "direction must be a Direction member"
            raise ValidationError(message)

    @staticmethod
    def reverse_direction(
        direction: Direction,
    ) -> Direction:
        """Return the direction that follows edges backwards.

        Parameters
        ----------
        direction : Direction
            Original traversal direction.

        Returns
        -------
        Direction
            The opposite direction, or ``BOTH`` for both directions.
        """
        if direction is Direction.OUTGOING:
            return Direction.INCOMING
        if direction is Direction.INCOMING:
            return Direction.OUTGOING
        return Direction.BOTH

    @staticmethod
    def normalize_types(
        rel_types: Iterable[str] | None,
    ) -> frozenset[str] | None:
        """Normalize a relationship type filter.

        Parameters
        ----------
        rel_types : Iterable[str] | None
            Relationship types to allow.

        Returns
        -------
        frozenset[str] | None
            The allowed types, or ``None`` when every type is allowed.

        Raises
        ------
        ValidationError
            If a type is not a non-empty string.
        """
        if rel_types is None:
            return None
        normalized: set[str] = set()
        for rel_type in rel_types:
            if not isinstance(rel_type, str) or not rel_type:
                message = "relationship types must be non-empty strings"
                raise ValidationError(message)
            normalized.add(rel_type)
        return frozenset(normalized) or None

    @staticmethod
    def validate_depth(depth: int, field: str) -> None:
        """Validate a non-negative integer traversal depth.

        Parameters
        ----------
        depth : int
            Depth to validate.
        field : str
            Field name used in error messages.

        Raises
        ------
        ValidationError
            If the depth is not an integer or is negative.
        """
        if not isinstance(depth, int) or isinstance(depth, bool):
            message = f"{field} must be an integer"
            raise ValidationError(message)
        if depth < 0:
            message = f"{field} must be non-negative"
            raise ValidationError(message)


class TraversalSource:
    """Read-only adjacency that breadth-first traversal can consume.

    A source answers node lookups and expands an ordered frontier. It either
    holds materialized adjacency or reads it on demand, so evaluators do not
    depend on how much of the graph was loaded.
    """

    def contains(self, node_id: int) -> bool:
        """Report whether the source can serve a node.

        Parameters
        ----------
        node_id : int
            Identifier to check.

        Returns
        -------
        bool
            ``True`` when the node is available.
        """
        raise NotImplementedError

    def node(self, node_id: int) -> Node:
        """Return one node snapshot.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        Node
            Node snapshot.
        """
        raise NotImplementedError

    def nodes(self, node_ids: Iterable[int]) -> dict[int, Node]:
        """Return several node snapshots at once.

        Parameters
        ----------
        node_ids : Iterable[int]
            Identifiers to read.

        Returns
        -------
        dict[int, Node]
            Snapshots keyed by id, omitting ids that are not available.
        """
        raise NotImplementedError

    def frontier_edges(
        self,
        frontier: Sequence[int],
        direction: Direction,
        rel_types: frozenset[str] | None,
    ) -> Iterator[tuple[int, Relationship, int]]:
        """Yield the edges leaving one ordered frontier.

        Parameters
        ----------
        frontier : Sequence[int]
            Ordered node identifiers to expand.
        direction : Direction
            Direction to follow.
        rel_types : frozenset[str] | None
            Allowed relationship types, or ``None`` for all types.

        Yields
        ------
        tuple[int, Relationship, int]
            The frontier node, the edge, and the node reached through it.
        """
        raise NotImplementedError


class AdjacencySnapshot(TraversalSource):
    """A materialized, read-only view of nodes and relationships.

    Parameters
    ----------
    nodes : Iterable[Node]
        Nodes that may appear in traversal results.
    relationships : Iterable[Relationship]
        Relationships that may be followed.
    """

    def __init__(
        self,
        nodes: Iterable[Node],
        relationships: Iterable[Relationship],
    ) -> None:
        self._nodes = {node.id: node for node in nodes}
        edges = tuple(relationships)
        outgoing: dict[int, list[Relationship]] = {}
        incoming: dict[int, list[Relationship]] = {}
        for relationship in edges:
            outgoing.setdefault(relationship.start_id, []).append(relationship)
            incoming.setdefault(relationship.end_id, []).append(relationship)
        self._outgoing = {node_id: tuple(values) for node_id, values in outgoing.items()}
        self._incoming = {node_id: tuple(values) for node_id, values in incoming.items()}

    @typing.override
    def contains(self, node_id: int) -> bool:
        """Report whether the snapshot contains a node.

        Parameters
        ----------
        node_id : int
            Identifier to check.

        Returns
        -------
        bool
            ``True`` when the node was captured.
        """
        return node_id in self._nodes

    @typing.override
    def node(self, node_id: int) -> Node:
        """Return a captured node.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        Node
            Snapshot of the node.

        Raises
        ------
        NotFoundError
            If the snapshot does not contain the node.
        """
        try:
            return self._nodes[node_id]
        except KeyError as error:
            message = f"node {node_id} does not exist"
            raise NotFoundError(message) from error

    @typing.override
    def nodes(self, node_ids: Iterable[int]) -> dict[int, Node]:
        """Return several captured nodes at once.

        Parameters
        ----------
        node_ids : Iterable[int]
            Identifiers to read.

        Returns
        -------
        dict[int, Node]
            Snapshots keyed by id, omitting ids outside the snapshot.
        """
        return {node_id: self._nodes[node_id] for node_id in node_ids if node_id in self._nodes}

    @typing.override
    def frontier_edges(
        self,
        frontier: Sequence[int],
        direction: Direction,
        rel_types: frozenset[str] | None,
    ) -> Iterator[tuple[int, Relationship, int]]:
        """Yield edges leaving one ordered frontier.

        Parameters
        ----------
        frontier : Sequence[int]
            Ordered node identifiers to expand.
        direction : Direction
            Direction to follow.
        rel_types : frozenset[str] | None
            Allowed relationship types, or ``None`` for all types.

        Yields
        ------
        tuple[int, Relationship, int]
            The frontier node, the edge, and the node reached through it.
        """
        for node_id in frontier:
            for relationship, target in self.edges(node_id, direction, rel_types):
                yield node_id, relationship, target

    def edges(
        self,
        node_id: int,
        direction: Direction,
        rel_types: frozenset[str] | None,
    ) -> Iterator[tuple[Relationship, int]]:
        """Iterate over relationships and the node they lead to.

        Parameters
        ----------
        node_id : int
            Current node.
        direction : Direction
            Direction to follow.
        rel_types : frozenset[str] | None
            Allowed relationship types, or ``None`` for all types.

        Yields
        ------
        tuple[Relationship, int]
            Each followable relationship and the node reached through it.
        """
        if direction in (
            Direction.OUTGOING,
            Direction.BOTH,
        ):
            for relationship in self._outgoing.get(node_id, ()):
                if rel_types is None or relationship.rel_type in rel_types:
                    yield relationship, relationship.end_id
        if direction in (
            Direction.INCOMING,
            Direction.BOTH,
        ):
            for relationship in self._incoming.get(node_id, ()):
                if direction is Direction.BOTH and relationship.start_id == node_id:
                    continue
                if rel_types is None or relationship.rel_type in rel_types:
                    yield relationship, relationship.start_id

    def distances_to(
        self,
        target_id: int,
        direction: Direction,
        rel_types: frozenset[str] | None,
    ) -> dict[int, int]:
        """Compute shortest hop distances from every node to a target.

        Parameters
        ----------
        target_id : int
            Node that paths should end at.
        direction : Direction
            Direction in which paths advance.
        rel_types : frozenset[str] | None
            Allowed relationship types, or ``None`` for all types.

        Returns
        -------
        dict[int, int]
            Distance keyed by node id. Nodes that cannot reach the target are
            absent.
        """
        distances: dict[int, int] = {target_id: 0}
        queue: collections.deque[int] = collections.deque([target_id])
        reverse = TraversalSupport.reverse_direction(direction)
        while queue:
            current = queue.popleft()
            next_distance = distances[current] + 1
            for _, neighbor in self.edges(current, reverse, rel_types):
                if neighbor not in distances:
                    distances[neighbor] = next_distance
                    queue.append(neighbor)
        return distances


class DatabaseNeighborhood(TraversalSource):
    """Read adjacency from the repositories on demand.

    Nothing is materialized, so a search reads only the levels it visits.

    Parameters
    ----------
    nodes : NodeRepository
        Source for node snapshots.
    relationships : RelationshipRepository
        Source for frontier reads.
    """

    def __init__(
        self,
        nodes: NodeRepository,
        relationships: RelationshipRepository,
    ) -> None:
        self._nodes = nodes
        self._relationships = relationships

    @typing.override
    def contains(self, node_id: int) -> bool:
        """Report whether the node exists in the database.

        Parameters
        ----------
        node_id : int
            Identifier to check.

        Returns
        -------
        bool
            ``True`` when the node exists.
        """
        return self._nodes.exists(node_id)

    @typing.override
    def node(self, node_id: int) -> Node:
        """Read one node snapshot.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        Node
            Node snapshot.
        """
        return self._nodes.get(node_id)

    @typing.override
    def nodes(self, node_ids: Iterable[int]) -> dict[int, Node]:
        """Read several node snapshots at once.

        Parameters
        ----------
        node_ids : Iterable[int]
            Identifiers to read.

        Returns
        -------
        dict[int, Node]
            Snapshots keyed by id, omitting missing ids.
        """
        return self._nodes.get_many(node_ids)

    @typing.override
    def frontier_edges(
        self,
        frontier: Sequence[int],
        direction: Direction,
        rel_types: frozenset[str] | None,
    ) -> Iterator[tuple[int, Relationship, int]]:
        """Read one ordered adjacency level from the database.

        Parameters
        ----------
        frontier : Sequence[int]
            Ordered node identifiers to expand.
        direction : Direction
            Direction to follow.
        rel_types : frozenset[str] | None
            Allowed relationship types, or ``None`` for all types.

        Yields
        ------
        tuple[int, Relationship, int]
            The frontier node, the edge, and the node reached through it.
        """
        yield from self._relationships.frontier(frontier, direction, rel_types)


class TraversalCapture:
    """Materialize the region a bounded search can reach.

    The region holds every node within the depth bound and every relationship
    whose tail is within the bound minus one, including edges that return to
    already visited nodes, because trail enumeration needs them.

    Parameters
    ----------
    nodes : NodeRepository
        Source for node snapshots.
    relationships : RelationshipRepository
        Source for level reads.
    """

    def __init__(
        self,
        nodes: NodeRepository,
        relationships: RelationshipRepository,
    ) -> None:
        self._nodes = nodes
        self._relationships = relationships

    def region(
        self,
        start: Node | int,
        max_depth: int,
        direction: Direction = Direction.OUTGOING,
        rel_types: Iterable[str] | None = None,
        include: Iterable[int] = (),
    ) -> AdjacencySnapshot:
        """Capture the bounded region around a start node.

        Parameters
        ----------
        start : Node | int
            Start node or its id.
        max_depth : int
            Maximum number of relationships to follow.
        direction : Direction, optional
            Direction to follow, by default outgoing.
        rel_types : Iterable[str] | None, optional
            Allowed relationship types, by default all types.
        include : Iterable[int], optional
            Extra node ids that must be present even when the region cannot
            reach them, by default none.

        Returns
        -------
        AdjacencySnapshot
            Materialized region fixed at capture time.

        Raises
        ------
        ValidationError
            If the depth or direction is invalid.
        NotFoundError
            If the start node or an included node does not exist.
        """
        start_id = TraversalSupport.node_id(start)
        TraversalSupport.validate_depth(max_depth, "max_depth")
        TraversalSupport.validate_direction(direction)
        types = TraversalSupport.normalize_types(rel_types)
        nodes_by_id: dict[int, Node] = {start_id: self._nodes.get(start_id)}
        relationships: dict[int, Relationship] = {}
        frontier: tuple[int, ...] = (start_id,)
        for level in range(1, max_depth + 1):
            seen = set(nodes_by_id)
            discovered: list[int] = []
            for _, relationship, target in self._relationships.frontier(
                frontier,
                direction,
                types,
            ):
                relationships.setdefault(relationship.id, relationship)
                if target not in seen:
                    seen.add(target)
                    discovered.append(target)
            if discovered:
                nodes_by_id.update(self._nodes.get_many(discovered))
            if level == max_depth or not discovered:
                break
            frontier = tuple(discovered)
        for node_id in include:
            if node_id not in nodes_by_id:
                nodes_by_id[node_id] = self._nodes.get(node_id)
        return AdjacencySnapshot(
            nodes_by_id.values(),
            sorted(relationships.values(), key=lambda relationship: relationship.id),
        )


class ReachabilityEvaluator:
    """Yield distinct reachable nodes at their shortest depth.

    Parameters
    ----------
    snapshot : AdjacencySnapshot
        Graph snapshot to traverse.
    start : Node | int
        Traversal start node or its id.
    max_depth : int
        Maximum number of relationships to follow.
    direction : Direction, optional
        Direction to follow, by default outgoing.
    rel_types : Iterable[str] | None, optional
        Allowed relationship types, by default all types.
    """

    def __init__(
        self,
        snapshot: AdjacencySnapshot,
        start: Node | int,
        max_depth: int,
        direction: Direction = Direction.OUTGOING,
        rel_types: Iterable[str] | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._start = TraversalSupport.node_id(start)
        self._max_depth = max_depth
        TraversalSupport.validate_depth(max_depth, "max_depth")
        TraversalSupport.validate_direction(direction)
        self._direction = direction
        self._types = TraversalSupport.normalize_types(rel_types)
        if not snapshot.contains(self._start):
            message = f"node {self._start} does not exist"
            raise NotFoundError(message)

    def __iter__(self) -> Iterator[TraversalStep]:
        """Yield reached nodes in breadth-first order.

        Yields
        ------
        TraversalStep
            Each non-start node once with its shortest depth.
        """
        visited = {self._start}
        queue: collections.deque[tuple[int, int]] = collections.deque([(self._start, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= self._max_depth:
                continue
            for _, target in self._snapshot.edges(
                current,
                self._direction,
                self._types,
            ):
                if target in visited:
                    continue
                visited.add(target)
                next_depth = depth + 1
                yield TraversalStep(
                    node=self._snapshot.node(target),
                    depth=next_depth,
                )
                queue.append((target, next_depth))


class ShortestPathEvaluator:
    """Find one shortest path with bidirectional breadth-first search.

    Parameters
    ----------
    source : TraversalSource
        Adjacency source read one frontier at a time.
    start : Node | int
        Start node or its id.
    end : Node | int
        End node or its id.
    direction : Direction, optional
        Direction in which paths advance, by default outgoing.
    rel_types : Iterable[str] | None, optional
        Allowed relationship types, by default all types.
    max_depth : int | None, optional
        Maximum path length, by default unbounded.
    """

    def __init__(
        self,
        source: TraversalSource,
        start: Node | int,
        end: Node | int,
        direction: Direction = Direction.OUTGOING,
        rel_types: Iterable[str] | None = None,
        max_depth: int | None = None,
    ) -> None:
        self._source = source
        self._start = TraversalSupport.node_id(start)
        self._end = TraversalSupport.node_id(end)
        TraversalSupport.validate_direction(direction)
        self._direction = direction
        self._types = TraversalSupport.normalize_types(rel_types)
        if max_depth is not None:
            TraversalSupport.validate_depth(max_depth, "max_depth")
        self._max_depth = max_depth
        if not source.contains(self._start):
            message = f"node {self._start} does not exist"
            raise NotFoundError(message)
        if not source.contains(self._end):
            message = f"node {self._end} does not exist"
            raise NotFoundError(message)

    def evaluate(self) -> Path | None:
        """Return one shortest path, or ``None`` when none exists.

        Returns
        -------
        Path | None
            A path with the fewest relationships, or ``None``.
        """
        if self._start == self._end:
            return Path(
                nodes=(self._source.node(self._start),),
                relationships=(),
            )
        if self._max_depth == 0:
            return None
        forward_parent: dict[int, tuple[int, Relationship] | None] = {self._start: None}
        backward_parent: dict[int, tuple[int, Relationship] | None] = {self._end: None}
        forward_depth = {self._start: 0}
        backward_depth = {self._end: 0}
        forward_frontier = [self._start]
        backward_frontier = [self._end]
        while forward_frontier and backward_frontier:
            if len(forward_frontier) <= len(backward_frontier):
                forward_frontier, meeting = self._expand(
                    forward_frontier,
                    forward_depth,
                    forward_parent,
                    backward_parent,
                    backward_depth,
                    self._direction,
                )
            else:
                backward_frontier, meeting = self._expand(
                    backward_frontier,
                    backward_depth,
                    backward_parent,
                    forward_parent,
                    forward_depth,
                    TraversalSupport.reverse_direction(self._direction),
                )
            if meeting is not None:
                length = forward_depth[meeting] + backward_depth[meeting]
                if self._max_depth is not None and length > self._max_depth:
                    return None
                return self._build_path(meeting, forward_parent, backward_parent)
        return None

    def _expand(
        self,
        frontier: list[int],
        own_depth: dict[int, int],
        own_parent: dict[int, tuple[int, Relationship] | None],
        other_parent: dict[int, tuple[int, Relationship] | None],
        other_depth: dict[int, int],
        direction: Direction,
    ) -> tuple[list[int], int | None]:
        """Expand one breadth-first layer and detect an intersection.

        Parameters
        ----------
        frontier : list[int]
            Nodes at the current depth of this side, in discovery order.
        own_depth : dict[int, int]
            Depth of each visited node on this side.
        own_parent : dict[int, tuple[int, Relationship] | None]
            Parent link for each visited node on this side.
        other_parent : dict[int, tuple[int, Relationship] | None]
            Visited nodes on the other side.
        other_depth : dict[int, int]
            Depth of each visited node on the other side.
        direction : Direction
            Direction followed by this side.

        Returns
        -------
        tuple[list[int], int | None]
            The next frontier and the best meeting node, if any.
        """
        next_frontier: list[int] = []
        meeting: int | None = None
        best_length: int | None = None
        edges = self._source.frontier_edges(frontier, direction, self._types)
        for current, relationship, target in edges:
            next_depth = own_depth[current] + 1
            if self._max_depth is not None and next_depth > self._max_depth:
                continue
            if target in own_parent:
                continue
            own_parent[target] = (current, relationship)
            own_depth[target] = next_depth
            next_frontier.append(target)
            if target in other_parent:
                total = next_depth + other_depth[target]
                if best_length is None or total < best_length:
                    best_length = total
                    meeting = target
        return next_frontier, meeting

    def _build_path(
        self,
        meeting: int,
        forward_parent: dict[int, tuple[int, Relationship] | None],
        backward_parent: dict[int, tuple[int, Relationship] | None],
    ) -> Path:
        """Reconstruct a path through the meeting node.

        Parameters
        ----------
        meeting : int
            Node visited from both search sides.
        forward_parent : dict[int, tuple[int, Relationship] | None]
            Parent links from the start side.
        backward_parent : dict[int, tuple[int, Relationship] | None]
            Parent links from the end side.

        Returns
        -------
        Path
            Path from start to end.
        """
        prefix_nodes = [meeting]
        prefix_relationships: list[Relationship] = []
        current = meeting
        while (link := forward_parent[current]) is not None:
            previous, relationship = link
            prefix_nodes.append(previous)
            prefix_relationships.append(relationship)
            current = previous
        prefix_nodes.reverse()
        prefix_relationships.reverse()
        suffix_nodes: list[int] = []
        suffix_relationships: list[Relationship] = []
        current = meeting
        while (link := backward_parent[current]) is not None:
            following, relationship = link
            suffix_nodes.append(following)
            suffix_relationships.append(relationship)
            current = following
        ordered = (*prefix_nodes, *suffix_nodes)
        nodes_by_id = self._source.nodes(ordered)
        return Path(
            nodes=tuple(nodes_by_id[node_id] for node_id in ordered),
            relationships=(*prefix_relationships, *suffix_relationships),
        )


class TrailEnumerator:
    """Enumerate relationship-unique trails between two nodes lazily.

    Parameters
    ----------
    snapshot : AdjacencySnapshot
        Graph snapshot to search.
    start : Node | int
        Start node or its id.
    end : Node | int
        End node or its id.
    min_depth : int
        Inclusive minimum number of relationships.
    max_depth : int
        Inclusive maximum number of relationships.
    direction : Direction, optional
        Direction in which paths advance, by default outgoing.
    rel_types : Iterable[str] | None, optional
        Allowed relationship types, by default all types.
    limit : int | None, optional
        Maximum number of paths to produce, by default unlimited.
    """

    def __init__(
        self,
        snapshot: AdjacencySnapshot,
        start: Node | int,
        end: Node | int,
        min_depth: int,
        max_depth: int,
        direction: Direction = Direction.OUTGOING,
        rel_types: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._start = TraversalSupport.node_id(start)
        self._end = TraversalSupport.node_id(end)
        self._min_depth = min_depth
        self._max_depth = max_depth
        TraversalSupport.validate_depth(min_depth, "min_depth")
        TraversalSupport.validate_depth(max_depth, "max_depth")
        if min_depth > max_depth:
            message = "min_depth must not exceed max_depth"
            raise ValidationError(message)
        TraversalSupport.validate_direction(direction)
        self._direction = direction
        self._types = TraversalSupport.normalize_types(rel_types)
        if limit is not None:
            TraversalSupport.validate_depth(limit, "limit")
        self._limit = limit
        if not snapshot.contains(self._start):
            message = f"node {self._start} does not exist"
            raise NotFoundError(message)
        if not snapshot.contains(self._end):
            message = f"node {self._end} does not exist"
            raise NotFoundError(message)
        self._distances = snapshot.distances_to(
            self._end,
            direction,
            self._types,
        )
        self._produced = 0
        self._used: set[int] = set()

    def __iter__(self) -> Iterator[Path]:
        """Yield trails lazily.

        Yields
        ------
        Path
            Each trail within the depth range.
        """
        self._produced = 0
        self._used = set()
        if self._limit == 0:
            return
        if self._min_depth == 0 and self._start == self._end:
            yield Path(
                nodes=(self._snapshot.node(self._start),),
                relationships=(),
            )
            self._produced += 1
        yield from self._search(
            self._start,
            [self._snapshot.node(self._start)],
            [],
        )

    def _search(
        self,
        current: int,
        path_nodes: list[Node],
        path_relationships: list[Relationship],
    ) -> Iterator[Path]:
        """Depth-first search over relationship-unique trails.

        Parameters
        ----------
        current : int
            Current node.
        path_nodes : list[Node]
            Nodes visited so far.
        path_relationships : list[Relationship]
            Relationships used so far.

        Yields
        ------
        Path
            Trails that reach the end within the depth range.
        """
        if self._limit is not None and self._produced >= self._limit:
            return
        length = len(path_relationships)
        if length >= self._max_depth:
            return
        distance = self._distances.get(current)
        if distance is None or distance > self._max_depth - length:
            return
        for relationship, target in self._snapshot.edges(
            current,
            self._direction,
            self._types,
        ):
            if relationship.id in self._used:
                continue
            path_nodes.append(self._snapshot.node(target))
            path_relationships.append(relationship)
            self._used.add(relationship.id)
            if target == self._end and len(path_relationships) >= self._min_depth:
                yield Path(
                    nodes=tuple(path_nodes),
                    relationships=tuple(path_relationships),
                )
                self._produced += 1
                if self._limit is not None and self._produced >= self._limit:
                    path_nodes.pop()
                    path_relationships.pop()
                    self._used.remove(relationship.id)
                    return
            yield from self._search(target, path_nodes, path_relationships)
            path_nodes.pop()
            path_relationships.pop()
            self._used.remove(relationship.id)
