# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Bounded in-memory matching for patterns that contain quantified relationships."""

import dataclasses
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence

from pygrafito.engine.query.ast import (
    Expression,
    NodePattern,
    PathPattern,
    PropertyEntry,
    RelationshipPattern,
)
from pygrafito.engine.query.values import (
    ExpressionEvaluator,
    PatternValueResolver,
    QueryValue,
    Values,
)
from pygrafito.engine.traversal import AdjacencySnapshot, TraversalCapture
from pygrafito.model import (
    Direction,
    Node,
    Path,
    Relationship,
)
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository

type NodeSelector = Callable[
    [NodePattern, Mapping[str, QueryValue], ExpressionEvaluator, Mapping[str, QueryValue]],
    Sequence[Node],
]


@dataclasses.dataclass(frozen=True, slots=True)
class WalkState:
    """One partial match while walking a quantified path.

    Parameters
    ----------
    position : int
        Index of the next relationship position.
    current : int
        Identifier of the node reached so far.
    hops : int
        Hops taken inside the current quantified segment.
    segment_rels : tuple[Relationship, ...]
        Relationships of the current quantified segment.
    segment_nodes : tuple[Node, ...]
        Nodes reached by the current quantified segment.
    path_nodes : tuple[Node, ...]
        Nodes accumulated for the whole path.
    path_rels : tuple[Relationship, ...]
        Relationships accumulated for the whole path.
    used : frozenset[int]
        Relationship identifiers already used by the path.
    binding : Mapping[str, QueryValue]
        Variables bound so far.
    """

    position: int
    current: int
    hops: int
    segment_rels: tuple[Relationship, ...]
    segment_nodes: tuple[Node, ...]
    path_nodes: tuple[Node, ...]
    path_rels: tuple[Relationship, ...]
    used: frozenset[int]
    binding: Mapping[str, QueryValue]


class PatternEngine:
    """Match a pattern set over depth-bounded adjacency snapshots.

    Parameters
    ----------
    nodes : NodeRepository
        Node source used to capture regions.
    relationships : RelationshipRepository
        Relationship source used to capture regions.
    select_nodes : NodeSelector
        Callback that returns candidate start nodes for a node pattern.
    parameters : Mapping[str, QueryValue]
        Query parameter values.
    evaluator : ExpressionEvaluator
        Evaluator used for the stage filter.
    """

    _MISSING: object = object()

    def __init__(
        self,
        nodes: NodeRepository,
        relationships: RelationshipRepository,
        select_nodes: NodeSelector,
        parameters: Mapping[str, QueryValue],
        evaluator: ExpressionEvaluator,
    ) -> None:
        self._nodes = nodes
        self._relationships = relationships
        self._select_nodes = select_nodes
        self._parameters = parameters
        self._evaluator = evaluator
        self._values = PatternValueResolver(evaluator, parameters)

    def match(
        self,
        patterns: Sequence[PathPattern],
        where: Expression | None,
        bound: Mapping[str, QueryValue],
    ) -> list[dict[str, QueryValue]]:
        """Match every pattern of a stage against one input row.

        Parameters
        ----------
        patterns : Sequence[PathPattern]
            Patterns evaluated together as one stage.
        where : Expression | None
            Stage filter, or ``None``.
        bound : Mapping[str, QueryValue]
            Variables produced by earlier stages.

        Returns
        -------
        list[dict[str, QueryValue]]
            One complete binding per match.
        """
        rows = [dict(bound)]
        for pattern in patterns:
            next_rows: list[dict[str, QueryValue]] = []
            for row in rows:
                next_rows.extend(self._match_pattern(pattern, row))
            rows = next_rows
        if where is None:
            return rows
        return [
            row for row in rows if self._evaluator.evaluate(where, row, self._parameters) is True
        ]

    def _match_pattern(
        self,
        pattern: PathPattern,
        base: Mapping[str, QueryValue],
    ) -> Iterator[dict[str, QueryValue]]:
        """Yield every match of one pattern.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to match.
        base : Mapping[str, QueryValue]
            Variables bound before the pattern starts.

        Yields
        ------
        dict[str, QueryValue]
            Complete binding for one match.
        """
        first = pattern.nodes[0]
        for start in self._start_nodes(first, base):
            binding = self._bind_node(first, start, base)
            if binding is None:
                continue
            snapshot = self._capture(start, self._depth(pattern))
            state = WalkState(
                position=0,
                current=start.id,
                hops=0,
                segment_rels=(),
                segment_nodes=(),
                path_nodes=(start,),
                path_rels=(),
                used=frozenset(),
                binding=binding,
            )
            yield from self._walk(pattern, state, snapshot)

    def _start_nodes(
        self,
        pattern: NodePattern,
        base: Mapping[str, QueryValue],
    ) -> Sequence[Node]:
        """Return candidate start nodes for the first node pattern.

        Parameters
        ----------
        pattern : NodePattern
            First node pattern of the path.
        base : Mapping[str, QueryValue]
            Variables bound before the pattern starts.

        Returns
        -------
        Sequence[Node]
            Bound start node, or every node matching the pattern.
        """
        name = pattern.variable
        if name is not None and name in base:
            value = base[name]
            if not isinstance(value, Node):
                return ()
            if not all(label in value.labels for label in pattern.labels):
                return ()
            if not self._properties_match(pattern.properties, value.properties, base):
                return ()
            return (value,)
        return self._select_nodes(pattern, self._parameters, self._evaluator, base)

    def _capture(self, start: Node, depth: int) -> AdjacencySnapshot:
        """Capture the region a bounded walk can reach from a start node.

        Parameters
        ----------
        start : Node
            Node to expand from.
        depth : int
            Maximum number of relationships the path can follow.

        Returns
        -------
        AdjacencySnapshot
            Materialized region fixed at capture time.
        """
        if depth <= 0:
            return AdjacencySnapshot((start,), ())
        return TraversalCapture(self._nodes, self._relationships).region(
            start,
            depth,
            Direction.BOTH,
        )

    @staticmethod
    def _depth(pattern: PathPattern) -> int:
        """Return the maximum number of hops a pattern can follow.

        Parameters
        ----------
        pattern : PathPattern
            Pattern whose bound is computed.

        Returns
        -------
        int
            Sum of each relationship position's maximum.
        """
        return sum(
            1 if relationship.max_hops is None else relationship.max_hops
            for relationship in pattern.relationships
        )

    def _walk(
        self,
        pattern: PathPattern,
        state: WalkState,
        snapshot: AdjacencySnapshot,
    ) -> Iterator[dict[str, QueryValue]]:
        """Walk one relationship position of a pattern.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Partial match to extend.
        snapshot : AdjacencySnapshot
            Captured region.

        Yields
        ------
        dict[str, QueryValue]
            Complete binding for one match.
        """
        if state.position == len(pattern.relationships):
            yield from self._finish(pattern, state, snapshot)
            return
        relationship = pattern.relationships[state.position]
        if relationship.min_hops is not None or relationship.max_hops is not None:
            yield from self._walk_quantified(pattern, state, relationship, snapshot)
            return
        yield from self._walk_fixed(pattern, state, relationship, snapshot)

    def _finish(
        self,
        pattern: PathPattern,
        state: WalkState,
        snapshot: AdjacencySnapshot,
    ) -> Iterator[dict[str, QueryValue]]:
        """Yield a binding when every path position has been consumed.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Complete walk.
        snapshot : AdjacencySnapshot
            Captured region.

        Yields
        ------
        dict[str, QueryValue]
            Final binding.
        """
        node = snapshot.node(state.current)
        binding = self._bind_node(pattern.nodes[-1], node, state.binding)
        if binding is None:
            return
        if pattern.variable is not None:
            path = Path(nodes=state.path_nodes, relationships=state.path_rels)
            existing = binding.get(pattern.variable, self._MISSING)
            if existing is self._MISSING:
                binding = {**binding, pattern.variable: path}
            elif not isinstance(existing, Path) or existing != path:
                return
        yield dict(binding)

    def _walk_fixed(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        snapshot: AdjacencySnapshot,
    ) -> Iterator[dict[str, QueryValue]]:
        """Follow one ordinary relationship position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Partial match to extend.
        relationship : RelationshipPattern
            Relationship position to follow.
        snapshot : AdjacencySnapshot
            Captured region.

        Yields
        ------
        dict[str, QueryValue]
            Complete binding for one match.
        """
        types = frozenset(relationship.types) if relationship.types else None
        for edge, target_id in self._arrow_edges(
            snapshot,
            state.current,
            relationship.direction,
            types,
        ):
            if edge.id in state.used or not self._relationship_matches(
                relationship,
                edge,
                state.binding,
            ):
                continue
            target = snapshot.node(target_id)
            binding = self._bind_node(pattern.nodes[state.position + 1], target, state.binding)
            if binding is None:
                continue
            binding = self._bind_relationships(binding, relationship, (edge,))
            if binding is None:
                continue
            next_state = WalkState(
                position=state.position + 1,
                current=target_id,
                hops=0,
                segment_rels=(),
                segment_nodes=(),
                path_nodes=(*state.path_nodes, target),
                path_rels=(*state.path_rels, edge),
                used=state.used | {edge.id},
                binding=binding,
            )
            yield from self._walk(pattern, next_state, snapshot)

    def _walk_quantified(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        snapshot: AdjacencySnapshot,
    ) -> Iterator[dict[str, QueryValue]]:
        """Follow a quantified relationship position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Partial match to extend.
        relationship : RelationshipPattern
            Quantified relationship position.
        snapshot : AdjacencySnapshot
            Captured region.

        Yields
        ------
        dict[str, QueryValue]
            Complete binding for one match.
        """
        minimum = 1 if relationship.min_hops is None else relationship.min_hops
        maximum = 0 if relationship.max_hops is None else relationship.max_hops
        if state.hops >= minimum:
            yield from self._finish_segment(pattern, state, relationship, snapshot)
        if state.hops >= maximum:
            return
        types = frozenset(relationship.types) if relationship.types else None
        for edge, target_id in self._arrow_edges(
            snapshot,
            state.current,
            relationship.direction,
            types,
        ):
            if edge.id in state.used or not self._relationship_matches(
                relationship,
                edge,
                state.binding,
            ):
                continue
            target = snapshot.node(target_id)
            next_state = WalkState(
                position=state.position,
                current=target_id,
                hops=state.hops + 1,
                segment_rels=(*state.segment_rels, edge),
                segment_nodes=(*state.segment_nodes, target),
                path_nodes=state.path_nodes,
                path_rels=state.path_rels,
                used=state.used | {edge.id},
                binding=state.binding,
            )
            yield from self._walk(pattern, next_state, snapshot)

    def _finish_segment(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        snapshot: AdjacencySnapshot,
    ) -> Iterator[dict[str, QueryValue]]:
        """Close one quantified segment and continue with the next position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            State at the end of the segment.
        relationship : RelationshipPattern
            Quantified position being closed.
        snapshot : AdjacencySnapshot
            Captured region.

        Yields
        ------
        dict[str, QueryValue]
            Complete binding for one match.
        """
        node = snapshot.node(state.current)
        binding = self._bind_node(pattern.nodes[state.position + 1], node, state.binding)
        if binding is None:
            return
        binding = self._bind_relationships(binding, relationship, state.segment_rels)
        if binding is None:
            return
        next_state = WalkState(
            position=state.position + 1,
            current=state.current,
            hops=0,
            segment_rels=(),
            segment_nodes=(),
            path_nodes=(*state.path_nodes, *state.segment_nodes),
            path_rels=(*state.path_rels, *state.segment_rels),
            used=state.used,
            binding=binding,
        )
        yield from self._walk(pattern, next_state, snapshot)

    def _bind_node(
        self,
        pattern: NodePattern,
        node: Node,
        binding: Mapping[str, QueryValue],
    ) -> dict[str, QueryValue] | None:
        """Check one node pattern and bind its variable.

        Parameters
        ----------
        pattern : NodePattern
            Node pattern to satisfy.
        node : Node
            Candidate node.
        binding : Mapping[str, QueryValue]
            Variables bound so far.

        Returns
        -------
        dict[str, QueryValue] | None
            Extended binding, or ``None`` when the pattern does not match.
        """
        if not all(label in node.labels for label in pattern.labels):
            return None
        if not self._properties_match(pattern.properties, node.properties, binding):
            return None
        name = pattern.variable
        if name is None:
            return dict(binding)
        existing = binding.get(name, self._MISSING)
        if existing is self._MISSING:
            return {**binding, name: node}
        if isinstance(existing, Node) and existing.id == node.id:
            return dict(binding)
        return None

    def _bind_relationships(
        self,
        binding: Mapping[str, QueryValue],
        pattern: RelationshipPattern,
        relationships: Sequence[Relationship],
    ) -> dict[str, QueryValue] | None:
        """Bind a relationship variable to one edge or a list of edges.

        Parameters
        ----------
        binding : Mapping[str, QueryValue]
            Variables bound so far.
        pattern : RelationshipPattern
            Relationship position whose variable is bound.
        relationships : Sequence[Relationship]
            Traversed relationships.

        Returns
        -------
        dict[str, QueryValue] | None
            Extended binding, or ``None`` when a bound variable conflicts.
        """
        name = pattern.variable
        if name is None:
            return dict(binding)
        value: QueryValue
        if pattern.min_hops is not None or pattern.max_hops is not None:
            value = list(relationships)
        elif relationships:
            value = relationships[0]
        else:
            value = None
        existing = binding.get(name, self._MISSING)
        if existing is self._MISSING:
            return {**binding, name: value}
        if Values.equals(typing.cast(QueryValue, existing), value) is True:
            return dict(binding)
        return None

    def _relationship_matches(
        self,
        pattern: RelationshipPattern,
        relationship: Relationship,
        binding: Mapping[str, QueryValue],
    ) -> bool:
        """Check the labels and property map of one traversed relationship.

        Parameters
        ----------
        pattern : RelationshipPattern
            Relationship position to satisfy.
        relationship : Relationship
            Candidate relationship.
        binding : Mapping[str, QueryValue]
            Variables bound so far.

        Returns
        -------
        bool
            ``True`` when the relationship satisfies the pattern.
        """
        if pattern.types and not set(pattern.types) & set(relationship.labels):
            return False
        return self._properties_match(pattern.properties, relationship.properties, binding)

    @staticmethod
    def _arrow_edges(
        snapshot: AdjacencySnapshot,
        node_id: int,
        direction: Direction,
        labels: frozenset[str] | None,
    ) -> Iterator[tuple[Relationship, int]]:
        """Yield edges allowed by one query relationship direction.

        The traversal API follows undirected edges from either endpoint in
        both outgoing and incoming walks. The query dialect's arrows are
        storage-direction constraints, so an undirected edge is reachable only
        through the undirected ``--`` pattern.

        Parameters
        ----------
        snapshot : AdjacencySnapshot
            Captured region.
        node_id : int
            Current node.
        direction : Direction
            Pattern direction.
        labels : frozenset[str] | None
            Allowed labels, or ``None`` for all labels.

        Yields
        ------
        tuple[Relationship, int]
            Followable edge and the node reached through it.
        """
        for relationship, target in snapshot.edges(node_id, direction, labels):
            if not relationship.directed and direction is not Direction.BOTH:
                continue
            yield relationship, target

    def _properties_match(
        self,
        entries: Sequence[PropertyEntry],
        properties: Mapping[str, QueryValue],
        binding: Mapping[str, QueryValue],
    ) -> bool:
        """Compare a pattern property map with stored properties.

        Parameters
        ----------
        entries : Sequence[PropertyEntry]
            Property-map entries.
        properties : Mapping[str, QueryValue]
            Stored properties.
        binding : Mapping[str, QueryValue]
            Variables bound so far.

        Returns
        -------
        bool
            ``True`` when every entry matches.
        """
        for entry in entries:
            expected = self._values.resolve(entry.value, binding)
            if expected is None:
                return False
            if Values.equals(properties.get(entry.key), expected) is not True:
                return False
        return True


__all__ = [
    "NodeSelector",
    "PatternEngine",
    "WalkState",
]
