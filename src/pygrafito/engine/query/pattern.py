# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Bounded in-memory matching for patterns that contain quantified relationships."""

import dataclasses
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence

from pygrafito.engine.query.ast import (
    EdgeDirection,
    Expression,
    NodePattern,
    PathMode,
    PathPattern,
    PropertyEntry,
    RelationshipPattern,
)
from pygrafito.engine.query.budget import BudgetTracker
from pygrafito.engine.query.labels import LabelExpressions
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
        Relationship identifiers already used by the path, for ``TRAIL``.
    visited : frozenset[int]
        Node identifiers reached by the path, for ``SIMPLE`` and ``ACYCLIC``.
    closed : bool
        Whether a ``SIMPLE`` path has returned to its start and cannot extend.
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
    visited: frozenset[int]
    closed: bool
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
    budget : BudgetTracker | None, optional
        Budget counters of this execution, by default none.
    """

    _MISSING: object = object()

    def __init__(
        self,
        nodes: NodeRepository,
        relationships: RelationshipRepository,
        select_nodes: NodeSelector,
        parameters: Mapping[str, QueryValue],
        evaluator: ExpressionEvaluator,
        budget: BudgetTracker | None = None,
    ) -> None:
        self._nodes = nodes
        self._relationships = relationships
        self._select_nodes = select_nodes
        self._parameters = parameters
        self._evaluator = evaluator
        self._budget = budget
        self._values = PatternValueResolver(evaluator, parameters)

    def _consume_expansion(self) -> None:
        """Count one relationship expansion against the execution budget."""
        if self._budget is not None:
            self._budget.consume_expansions()

    def _consume_row(self) -> None:
        """Count one intermediate binding against the execution budget."""
        if self._budget is not None:
            self._budget.consume_rows()

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
                for match in self._match_pattern(pattern, row):
                    self._consume_row()
                    next_rows.append(match)
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
            mode = self._mode(pattern)
            visited = (
                frozenset({start.id})
                if mode in {PathMode.SIMPLE, PathMode.ACYCLIC}
                else frozenset()
            )
            state = WalkState(
                position=0,
                current=start.id,
                hops=0,
                segment_rels=(),
                segment_nodes=(),
                path_nodes=(start,),
                path_rels=(),
                used=frozenset(),
                visited=visited,
                closed=False,
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
            if not self._labels_match(pattern, value.labels):
                return ()
            if not self._properties_match(pattern.properties, value.properties, base):
                return ()
            if not self._where_matches(pattern.where, pattern.variable, value, base):
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

    @staticmethod
    def _mode(pattern: PathPattern) -> PathMode:
        """Return the effective mode of one pattern.

        Parameters
        ----------
        pattern : PathPattern
            Pattern whose mode is read.

        Returns
        -------
        PathMode
            Resolved mode, or ``WALK`` when analysis assigned none.
        """
        return PathMode.WALK if pattern.mode is None else pattern.mode

    @classmethod
    def _extend_memory(
        cls,
        pattern: PathPattern,
        state: WalkState,
        edge: Relationship,
        target: Node,
    ) -> tuple[frozenset[int], frozenset[int], bool] | None:
        """Apply the path mode to one candidate extension.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Current partial match.
        edge : Relationship
            Candidate relationship.
        target : Node
            Node reached through the candidate relationship.

        Returns
        -------
        tuple[frozenset[int], frozenset[int], bool] | None
            Relationship set, node set, and closed flag for the extended
            state, or ``None`` when the mode rejects the extension.
        """
        mode = cls._mode(pattern)
        if mode is PathMode.WALK:
            return state.used, state.visited, False
        if mode is PathMode.TRAIL:
            if edge.id in state.used:
                return None
            return state.used | {edge.id}, state.visited, False
        if state.closed:
            return None
        if target.id in state.visited:
            start = state.path_nodes[0].id
            if mode is PathMode.SIMPLE and target.id == start:
                return state.used, state.visited, True
            return None
        return state.used, state.visited | {target.id}, False

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
        if state.closed:
            return
        types = frozenset(relationship.types) if relationship.types else None
        for edge, target_id in self._arrow_edges(
            snapshot,
            state.current,
            relationship.direction,
            types,
        ):
            self._consume_expansion()
            if not self._relationship_matches(
                relationship,
                edge,
                state.binding,
            ):
                continue
            target = snapshot.node(target_id)
            memory = self._extend_memory(pattern, state, edge, target)
            if memory is None:
                continue
            used, visited, closed = memory
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
                used=used,
                visited=visited,
                closed=closed,
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
        if state.closed or state.hops >= maximum:
            return
        types = frozenset(relationship.types) if relationship.types else None
        for edge, target_id in self._arrow_edges(
            snapshot,
            state.current,
            relationship.direction,
            types,
        ):
            self._consume_expansion()
            if not self._relationship_matches(
                relationship,
                edge,
                state.binding,
            ):
                continue
            target = snapshot.node(target_id)
            memory = self._extend_memory(pattern, state, edge, target)
            if memory is None:
                continue
            used, visited, closed = memory
            next_state = WalkState(
                position=state.position,
                current=target_id,
                hops=state.hops + 1,
                segment_rels=(*state.segment_rels, edge),
                segment_nodes=(*state.segment_nodes, target),
                path_nodes=state.path_nodes,
                path_rels=state.path_rels,
                used=used,
                visited=visited,
                closed=closed,
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
            visited=state.visited,
            closed=state.closed,
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
        if not self._labels_match(pattern, node.labels):
            return None
        if not self._properties_match(pattern.properties, node.properties, binding):
            return None
        if not self._where_matches(pattern.where, pattern.variable, node, binding):
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
        if pattern.label_expression is not None:
            if not LabelExpressions.matches(pattern.label_expression, relationship.labels):
                return False
        elif pattern.types and not set(pattern.types) & set(relationship.labels):
            return False
        if not self._where_matches(pattern.where, pattern.variable, relationship, binding):
            return False
        return self._properties_match(pattern.properties, relationship.properties, binding)

    @staticmethod
    def _arrow_edges(
        snapshot: AdjacencySnapshot,
        node_id: int,
        direction: EdgeDirection,
        labels: frozenset[str] | None,
    ) -> Iterator[tuple[Relationship, int]]:
        """Yield edges allowed by one query relationship direction.

        The storage traversal follows undirected edges from either endpoint in
        both outgoing and incoming walks. The query direction then admits or
        excludes those undirected candidates according to its directedness.

        Parameters
        ----------
        snapshot : AdjacencySnapshot
            Captured region.
        node_id : int
            Current node.
        direction : EdgeDirection
            Direction form of the relationship pattern.
        labels : frozenset[str] | None
            Allowed labels, or ``None`` for all labels.

        Yields
        ------
        tuple[Relationship, int]
            Followable edge and the node reached through it.
        """
        directedness = direction.directedness
        for relationship, target in snapshot.edges(node_id, direction.traversal, labels):
            if directedness is True and not relationship.directed:
                continue
            if directedness is False and relationship.directed:
                continue
            yield relationship, target

    @staticmethod
    def _labels_match(
        pattern: NodePattern | RelationshipPattern,
        labels: frozenset[str],
    ) -> bool:
        """Check one pattern's label expression against element labels.

        Parameters
        ----------
        pattern : NodePattern | RelationshipPattern
            Pattern carrying the label constraint.
        labels : frozenset[str]
            Labels carried by the candidate element.

        Returns
        -------
        bool
            ``True`` when the pattern matches.
        """
        if pattern.label_expression is not None:
            return LabelExpressions.matches(pattern.label_expression, labels)
        if isinstance(pattern, NodePattern):
            return all(label in labels for label in pattern.labels)
        return not pattern.types or any(label in labels for label in pattern.types)

    def _where_matches(
        self,
        where: Expression | None,
        variable: str | None,
        value: QueryValue,
        binding: Mapping[str, QueryValue],
    ) -> bool:
        """Evaluate an inline element predicate.

        Parameters
        ----------
        where : Expression | None
            Predicate to evaluate, or ``None``.
        variable : str | None
            Element variable, or ``None`` when anonymous.
        value : QueryValue
            Element snapshot the predicate is scoped to.
        binding : Mapping[str, QueryValue]
            Variables bound so far.

        Returns
        -------
        bool
            ``True`` when the predicate is absent or evaluates to ``True``.
        """
        if where is None:
            return True
        scope = binding if variable is None else {**binding, variable: value}
        return self._values.resolve(where, scope) is True

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
