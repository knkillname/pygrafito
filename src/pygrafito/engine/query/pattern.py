# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Bounded in-memory matching for patterns that contain quantified relationships."""

import dataclasses
import heapq
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence

from pygrafito.engine.query.ast import (
    EdgeDirection,
    Expression,
    GroupedPathTerm,
    MatchMode,
    NodePattern,
    PathMode,
    PathPattern,
    PathSearch,
    PathSearchKind,
    PropertyEntry,
    RelationshipPattern,
    SimplePathTerm,
)
from pygrafito.engine.query.budget import BudgetTracker
from pygrafito.engine.query.labels import LabelExpressions
from pygrafito.engine.query.values import (
    ExpressionEvaluator,
    PatternValueResolver,
    QueryValue,
    Values,
)
from pygrafito.engine.traversal import (
    AdjacencySnapshot,
    DatabaseNeighborhood,
    TraversalCapture,
    TraversalSource,
)
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
    match_mode : MatchMode, optional
        Relationship-sharing rule of the clause, by default
        ``MatchMode.REPEATABLE_ELEMENTS``.
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
        match_mode: MatchMode = MatchMode.REPEATABLE_ELEMENTS,
    ) -> None:
        self._nodes = nodes
        self._relationships = relationships
        self._select_nodes = select_nodes
        self._parameters = parameters
        self._evaluator = evaluator
        self._budget = budget
        self._match_mode = match_mode
        self._values = PatternValueResolver(evaluator, parameters)
        self._grouped = GroupedMatcher(self)
        self._search = PathSearchEvaluator(self)
        self._grouped_search = GroupedSearchEvaluator(self)

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
        return list(self.iter_match(patterns, where, bound))

    def iter_match(
        self,
        patterns: Sequence[PathPattern],
        where: Expression | None,
        bound: Mapping[str, QueryValue],
    ) -> Iterator[dict[str, QueryValue]]:
        """Yield every match of a stage against one input row.

        Closing the iterator stops the walk, so a caller that satisfies its
        demand early does not expand the remaining relationships.

        Parameters
        ----------
        patterns : Sequence[PathPattern]
            Patterns evaluated together as one stage.
        where : Expression | None
            Stage filter, or ``None``.
        bound : Mapping[str, QueryValue]
            Variables produced by earlier stages.

        Yields
        ------
        dict[str, QueryValue]
            One complete binding per match.
        """
        rows: Iterator[tuple[dict[str, QueryValue], frozenset[int]]] = iter(
            ((dict(bound), frozenset()),)
        )
        for pattern in patterns:
            rows = self._match_stage(pattern, rows)
        for row, _used in rows:
            if (
                where is not None
                and self._evaluator.evaluate(where, row, self._parameters) is not True
            ):
                continue
            yield row

    def _match_stage(
        self,
        pattern: PathPattern,
        rows: Iterator[tuple[dict[str, QueryValue], frozenset[int]]],
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Match one pattern for every row produced by the previous one.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to match.
        rows : Iterator[tuple[dict[str, QueryValue], frozenset[int]]]
            Input bindings and their clause-wide used edge sets.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            One binding per match and the edges it used.
        """
        for row, used in rows:
            if pattern.search is not None and not pattern.is_simple:
                matches = self._grouped_search.iter_pattern(pattern, row, used)
            elif pattern.search is not None:
                matches = self._search.iter_pattern(pattern, row, used)
            else:
                matches = self._match_pattern_with_usage(pattern, row, used)
            for match, used_after in matches:
                self._consume_row()
                yield match, used_after

    def _match_pattern_with_usage(
        self,
        pattern: PathPattern,
        base: Mapping[str, QueryValue],
        used: frozenset[int],
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Yield every match of one pattern and its clause-wide used edges.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to match.
        base : Mapping[str, QueryValue]
            Variables bound before the pattern starts.
        used : frozenset[int]
            Relationship identifiers already bound by the clause.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Complete binding for one match and the relationships it used.
        """
        if not pattern.is_simple:
            for walk in self._grouped.iter_matches(pattern, base, used):
                yield dict(walk.binding), walk.used
            return
        first = pattern.nodes[0]
        initial = used if self._match_mode is MatchMode.DIFFERENT_EDGES else frozenset()
        for start in self._start_nodes(first, base):
            binding = self._bind_node(first, start, base)
            if binding is None:
                continue
            snapshot = self._capture(start, pattern)
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
                used=initial,
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

    def _capture(self, start: Node, pattern: PathPattern) -> TraversalSource:
        """Select the adjacency source a walk reads.

        A bounded pattern captures one fixed region. A pattern with an
        open-ended position reads adjacency level by level from the live
        neighborhood instead, so it never materializes the reachable region.

        Parameters
        ----------
        start : Node
            Node to expand from.
        pattern : PathPattern
            Pattern being matched.

        Returns
        -------
        TraversalSource
            Materialized region or live neighborhood.
        """
        if self._has_open_position(pattern):
            return DatabaseNeighborhood(self._nodes, self._relationships)
        depth = self._depth(pattern)
        if depth <= 0:
            return AdjacencySnapshot((start,), ())
        return TraversalCapture(self._nodes, self._relationships).region(
            start,
            depth,
            Direction.BOTH,
        )

    @staticmethod
    def _has_open_position(pattern: PathPattern) -> bool:
        """Report whether any relationship position is open-ended.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to inspect.

        Returns
        -------
        bool
            ``True`` when a quantified position has no upper bound.
        """
        return pattern.has_open_position()

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
        maximum = pattern.maximum_relationships()
        return 0 if maximum is None else maximum

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

    def _extend_memory(
        self,
        pattern: PathPattern,
        state: WalkState,
        edge: Relationship,
        target: Node,
    ) -> tuple[frozenset[int], frozenset[int], bool] | None:
        """Apply the path mode and match mode to one candidate extension.

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
            state, or ``None`` when a mode rejects the extension.
        """
        mode = self._mode(pattern)
        used = state.used
        visited = state.visited
        closed = False
        if self._match_mode is MatchMode.DIFFERENT_EDGES and edge.id in used:
            return None
        if mode is PathMode.TRAIL:
            if edge.id in used:
                return None
            used = used | {edge.id}
        elif mode in {PathMode.SIMPLE, PathMode.ACYCLIC}:
            if state.closed:
                return None
            if target.id in visited:
                start = state.path_nodes[0].id
                if mode is PathMode.SIMPLE and target.id == start:
                    closed = True
                else:
                    return None
            else:
                visited = visited | {target.id}
        if self._match_mode is MatchMode.DIFFERENT_EDGES:
            used = used | {edge.id}
        return used, visited, closed

    def _walk(
        self,
        pattern: PathPattern,
        state: WalkState,
        snapshot: TraversalSource,
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Walk one relationship position of a pattern.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Partial match to extend.
        snapshot : TraversalSource
            Captured region.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Complete binding for one match and the relationships it used.
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
        snapshot: TraversalSource,
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Yield a binding when every path position has been consumed.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Complete walk.
        snapshot : TraversalSource
            Captured region.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Final binding and the relationships the path used.
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
        yield dict(binding), state.used

    def _walk_fixed(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        snapshot: TraversalSource,
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Follow one ordinary relationship position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Partial match to extend.
        relationship : RelationshipPattern
            Relationship position to follow.
        snapshot : TraversalSource
            Captured region.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Complete binding for one match and the relationships it used.
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
            next_state = self._advance_fixed_state(
                pattern,
                state,
                relationship,
                edge,
                target_id,
                snapshot,
            )
            if next_state is not None:
                yield from self._walk(pattern, next_state, snapshot)

    def _walk_quantified(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        snapshot: TraversalSource,
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Follow a quantified relationship position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            Partial match to extend.
        relationship : RelationshipPattern
            Quantified relationship position.
        snapshot : TraversalSource
            Captured region.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Complete binding for one match and the relationships it used.
        """
        minimum = 1 if relationship.min_hops is None else relationship.min_hops
        maximum = relationship.max_hops
        types = frozenset(relationship.types) if relationship.types else None
        stack: list[tuple[WalkState, Iterator[tuple[Relationship, int]] | None]] = [(state, None)]
        while stack:
            current, candidates = stack[-1]
            if candidates is None:
                if current.hops >= minimum:
                    yield from self._finish_segment(pattern, current, relationship, snapshot)
                if current.closed or (maximum is not None and current.hops >= maximum):
                    stack.pop()
                    continue
                stack[-1] = (
                    current,
                    self._arrow_edges(
                        snapshot,
                        current.current,
                        relationship.direction,
                        types,
                    ),
                )
                continue
            try:
                edge, target_id = next(candidates)
            except StopIteration:
                stack.pop()
                continue
            self._consume_expansion()
            if not self._relationship_matches(
                relationship,
                edge,
                current.binding,
            ):
                continue
            next_state = self._advance_quantified_state(
                pattern,
                current,
                edge,
                target_id,
                snapshot,
            )
            if next_state is not None:
                stack.append((next_state, None))

    def _finish_segment(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        snapshot: TraversalSource,
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Close one quantified segment and continue with the next position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            State at the end of the segment.
        relationship : RelationshipPattern
            Quantified position being closed.
        snapshot : TraversalSource
            Captured region.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Complete binding for one match and the relationships it used.
        """
        next_state = self._close_segment_state(
            pattern,
            state,
            relationship,
            snapshot,
        )
        if next_state is not None:
            yield from self._walk(pattern, next_state, snapshot)

    def _advance_fixed_state(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        edge: Relationship,
        target_id: int,
        snapshot: TraversalSource,
    ) -> WalkState | None:
        """Build the state after following one ordinary relationship.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            State before the relationship.
        relationship : RelationshipPattern
            Relationship position being followed.
        edge : Relationship
            Traversed relationship.
        target_id : int
            Node reached through the relationship.
        snapshot : TraversalSource
            Captured region.

        Returns
        -------
        WalkState | None
            Advanced state, or ``None`` when a mode or binding rejects it.
        """
        target = snapshot.node(target_id)
        memory = self._extend_memory(pattern, state, edge, target)
        if memory is None:
            return None
        used, visited, closed = memory
        binding = self._bind_node(pattern.nodes[state.position + 1], target, state.binding)
        if binding is None:
            return None
        binding = self._bind_relationships(binding, relationship, (edge,))
        if binding is None:
            return None
        return WalkState(
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

    def _advance_quantified_state(
        self,
        pattern: PathPattern,
        state: WalkState,
        edge: Relationship,
        target_id: int,
        snapshot: TraversalSource,
    ) -> WalkState | None:
        """Build the state after one hop inside a quantified position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            State before the hop.
        edge : Relationship
            Traversed relationship.
        target_id : int
            Node reached through the relationship.
        snapshot : TraversalSource
            Captured region.

        Returns
        -------
        WalkState | None
            Advanced state, or ``None`` when a mode rejects it.
        """
        target = snapshot.node(target_id)
        memory = self._extend_memory(pattern, state, edge, target)
        if memory is None:
            return None
        used, visited, closed = memory
        return WalkState(
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

    def _close_segment_state(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        snapshot: TraversalSource,
    ) -> WalkState | None:
        """Build the state that closes one quantified position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            State at the end of the segment.
        relationship : RelationshipPattern
            Quantified position being closed.
        snapshot : TraversalSource
            Captured region.

        Returns
        -------
        WalkState | None
            State advanced past the segment, or ``None`` when a binding
            rejects it.
        """
        node = snapshot.node(state.current)
        binding = self._bind_node(pattern.nodes[state.position + 1], node, state.binding)
        if binding is None:
            return None
        binding = self._bind_relationships(binding, relationship, state.segment_rels)
        if binding is None:
            return None
        return WalkState(
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
        snapshot: TraversalSource,
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
        snapshot : TraversalSource
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


@dataclasses.dataclass(frozen=True, slots=True)
class ModeMemory:
    """Repetition memory for one path mode.

    Parameters
    ----------
    mode : PathMode
        Mode whose constraints are tracked.
    start_id : int
        Node where the path or group started.
    used : frozenset[int], optional
        Relationships already used by a ``TRAIL`` memory, by default none.
    visited : frozenset[int], optional
        Nodes already visited by a ``SIMPLE`` or ``ACYCLIC`` memory, by
        default none.
    closed : bool, optional
        Whether a ``SIMPLE`` path has returned to its start, by default
        ``False``.
    """

    mode: PathMode
    start_id: int
    used: frozenset[int] = frozenset()
    visited: frozenset[int] = frozenset()
    closed: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class TermWalk:
    """Partial match over a sequence of path terms.

    Parameters
    ----------
    current : Node
        Node at the end of the matched prefix.
    binding : Mapping[str, QueryValue]
        Variables bound so far.
    path_nodes : tuple[Node, ...]
        Nodes in traversal order.
    path_rels : tuple[Relationship, ...]
        Relationships in traversal order.
    used : frozenset[int]
        Relationship identifiers already used by the clause match mode.
    memory : ModeMemory
        Outer path mode memory.
    inner : tuple[ModeMemory, ...]
        Active group mode memories, from outermost to innermost.
    """

    current: Node
    binding: Mapping[str, QueryValue]
    path_nodes: tuple[Node, ...]
    path_rels: tuple[Relationship, ...]
    used: frozenset[int]
    memory: ModeMemory
    inner: tuple[ModeMemory, ...] = ()


class GroupedMatcher:
    """Match path patterns that contain grouped terms.

    Parameters
    ----------
    engine : PatternEngine
        Engine whose predicate, binding, edge, and budget helpers are reused.
    """

    def __init__(self, engine: PatternEngine) -> None:
        self._engine = engine

    def iter_matches(
        self,
        pattern: PathPattern,
        base: Mapping[str, QueryValue],
        used: frozenset[int],
        *,
        start: Node | None = None,
        max_length: int | None = None,
    ) -> Iterator[TermWalk]:
        """Yield every complete match of one grouped or juxtaposed pattern.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to match.
        base : Mapping[str, QueryValue]
            Variables bound before the pattern.
        used : frozenset[int]
            Relationships already bound by the clause.
        start : Node | None, optional
            Restrict matching to one start node, by default every matching
            start.
        max_length : int | None, optional
            Maximum relationship count, by default unlimited.

        Yields
        ------
        TermWalk
            Complete match with its path and used relationships.
        """
        initial = used if self._engine._match_mode is MatchMode.DIFFERENT_EDGES else frozenset()
        if start is None:
            starts = sorted(
                self._engine._start_nodes(pattern.first_node, base),
                key=lambda node: node.id,
            )
        else:
            starts = [start]
        for candidate in starts:
            first_term = pattern.terms[0]
            binding = (
                dict(base)
                if isinstance(first_term, GroupedPathTerm)
                else self._engine._bind_node(pattern.first_node, candidate, base)
            )
            if binding is None:
                continue
            snapshot = self._engine._capture(candidate, pattern)
            mode = self._engine._mode(pattern)
            memory = ModeMemory(
                mode=mode,
                start_id=candidate.id,
                visited=(
                    frozenset({candidate.id})
                    if mode in {PathMode.SIMPLE, PathMode.ACYCLIC}
                    else frozenset()
                ),
            )
            walk = TermWalk(
                current=candidate,
                binding=binding,
                path_nodes=(candidate,),
                path_rels=(),
                used=initial,
                memory=memory,
            )
            for result in self._walk_terms(pattern.terms, 0, walk, snapshot, max_length):
                binding = self._bind_path_variable(pattern, result)
                if binding is None:
                    continue
                yield dataclasses.replace(result, binding=binding)

    def _bind_path_variable(
        self,
        pattern: PathPattern,
        walk: TermWalk,
    ) -> dict[str, QueryValue] | None:
        """Bind or check the whole-path variable.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being completed.
        walk : TermWalk
            Complete walk.

        Returns
        -------
        dict[str, QueryValue] | None
            Binding extended with the path, or ``None`` on a conflict.
        """
        if pattern.variable is None:
            return dict(walk.binding)
        path = Path(nodes=walk.path_nodes, relationships=walk.path_rels)
        existing = walk.binding.get(pattern.variable, self._engine._MISSING)
        if existing is self._engine._MISSING:
            return {**walk.binding, pattern.variable: path}
        if isinstance(existing, Path) and existing == path:
            return dict(walk.binding)
        return None

    def _walk_terms(
        self,
        terms: Sequence[SimplePathTerm | GroupedPathTerm],
        index: int,
        walk: TermWalk,
        snapshot: TraversalSource,
        max_length: int | None,
    ) -> Iterator[TermWalk]:
        """Walk the terms of one pattern from one index.

        Parameters
        ----------
        terms : Sequence[SimplePathTerm | GroupedPathTerm]
            Terms to walk.
        index : int
            Current term index.
        walk : TermWalk
            Partial match.
        snapshot : TraversalSource
            Captured adjacency source.
        max_length : int | None
            Maximum relationship count, or ``None``.

        Yields
        ------
        TermWalk
            Complete match.
        """
        if index == len(terms):
            yield walk
            return
        term = terms[index]
        if isinstance(term, SimplePathTerm):
            entered = self._enter_simple_term(term, walk)
            if entered is None:
                return
            for result in self._walk_relationships(term, 0, entered, snapshot, max_length):
                yield from self._walk_terms(terms, index + 1, result, snapshot, max_length)
            return
        for result in self._walk_group(term, walk, snapshot, max_length):
            yield from self._walk_terms(terms, index + 1, result, snapshot, max_length)

    def _enter_simple_term(
        self,
        term: SimplePathTerm,
        walk: TermWalk,
    ) -> TermWalk | None:
        """Bind the boundary node of a simple term.

        Parameters
        ----------
        term : SimplePathTerm
            Term being entered.
        walk : TermWalk
            Partial match.

        Returns
        -------
        TermWalk | None
            Walk with the boundary bound, or ``None`` when it does not match.
        """
        binding = self._engine._bind_node(term.nodes[0], walk.current, walk.binding)
        if binding is None:
            return None
        return dataclasses.replace(walk, binding=binding)

    def _walk_relationships(
        self,
        term: SimplePathTerm,
        index: int,
        walk: TermWalk,
        snapshot: TraversalSource,
        max_length: int | None,
    ) -> Iterator[TermWalk]:
        """Walk one relationship position of a simple term.

        Parameters
        ----------
        term : SimplePathTerm
            Term being walked.
        index : int
            Relationship index inside the term.
        walk : TermWalk
            Partial match.
        snapshot : TraversalSource
            Captured adjacency source.
        max_length : int | None
            Maximum relationship count, or ``None``.

        Yields
        ------
        TermWalk
            Walk after the term completes.
        """
        if index == len(term.relationships):
            yield walk
            return
        relationship = term.relationships[index]
        if relationship.min_hops is not None or relationship.max_hops is not None:
            yield from self._walk_quantified_term(
                term,
                index,
                walk,
                snapshot,
                max_length,
                hops=0,
                segment_rels=(),
                segment_nodes=(),
            )
            return
        types = frozenset(relationship.types) if relationship.types else None
        for edge, target_id in self._engine._arrow_edges(
            snapshot,
            walk.current.id,
            relationship.direction,
            types,
        ):
            self._engine._consume_expansion()
            if not self._engine._relationship_matches(relationship, edge, walk.binding):
                continue
            if max_length is not None and len(walk.path_rels) >= max_length:
                continue
            advanced = self._advance_edge(walk, edge, snapshot.node(target_id))
            if advanced is None:
                continue
            target = snapshot.node(target_id)
            binding = self._engine._bind_node(
                term.nodes[index + 1],
                target,
                advanced.binding,
            )
            if binding is None:
                continue
            binding = self._engine._bind_relationships(binding, relationship, (edge,))
            if binding is None:
                continue
            next_walk = dataclasses.replace(
                advanced,
                binding=binding,
                path_nodes=(*advanced.path_nodes, target),
                path_rels=(*advanced.path_rels, edge),
            )
            yield from self._walk_relationships(
                term,
                index + 1,
                next_walk,
                snapshot,
                max_length,
            )

    def _walk_quantified_term(
        self,
        term: SimplePathTerm,
        index: int,
        walk: TermWalk,
        snapshot: TraversalSource,
        max_length: int | None,
        *,
        hops: int,
        segment_rels: tuple[Relationship, ...],
        segment_nodes: tuple[Node, ...],
    ) -> Iterator[TermWalk]:
        """Walk one quantified relationship position of a simple term.

        Parameters
        ----------
        term : SimplePathTerm
            Term being walked.
        index : int
            Relationship index inside the term.
        walk : TermWalk
            Partial match before the quantified position.
        snapshot : TraversalSource
            Captured adjacency source.
        max_length : int | None
            Maximum relationship count, or ``None``.
        hops : int
            Hops taken inside the current segment.
        segment_rels : tuple[Relationship, ...]
            Relationships in the current segment.
        segment_nodes : tuple[Node, ...]
            Nodes reached in the current segment.

        Yields
        ------
        TermWalk
            Walk after the term completes.
        """
        relationship = term.relationships[index]
        minimum = 1 if relationship.min_hops is None else relationship.min_hops
        maximum = relationship.max_hops
        if hops >= minimum:
            target = snapshot.node(walk.current.id)
            binding = self._engine._bind_node(
                term.nodes[index + 1],
                target,
                walk.binding,
            )
            if binding is not None:
                binding = self._engine._bind_relationships(binding, relationship, segment_rels)
            if binding is not None:
                closed = dataclasses.replace(
                    walk,
                    binding=binding,
                    path_nodes=(*walk.path_nodes, *segment_nodes),
                    path_rels=(*walk.path_rels, *segment_rels),
                )
                yield from self._walk_relationships(
                    term,
                    index + 1,
                    closed,
                    snapshot,
                    max_length,
                )
        if maximum is not None and hops >= maximum:
            return
        if walk.memory.closed or any(memory.closed for memory in walk.inner):
            return
        if max_length is not None and len(walk.path_rels) + len(segment_rels) >= max_length:
            return
        types = frozenset(relationship.types) if relationship.types else None
        for edge, target_id in self._engine._arrow_edges(
            snapshot,
            walk.current.id,
            relationship.direction,
            types,
        ):
            self._engine._consume_expansion()
            if not self._engine._relationship_matches(relationship, edge, walk.binding):
                continue
            target = snapshot.node(target_id)
            advanced = self._advance_edge(walk, edge, target)
            if advanced is None:
                continue
            yield from self._walk_quantified_term(
                term,
                index,
                advanced,
                snapshot,
                max_length,
                hops=hops + 1,
                segment_rels=(*segment_rels, edge),
                segment_nodes=(*segment_nodes, target),
            )

    def _advance_edge(
        self,
        walk: TermWalk,
        edge: Relationship,
        target: Node,
    ) -> TermWalk | None:
        """Apply path and match modes to one candidate edge.

        Parameters
        ----------
        walk : TermWalk
            Walk before the edge.
        edge : Relationship
            Candidate relationship.
        target : Node
            Node reached through the relationship.

        Returns
        -------
        TermWalk | None
            Walk with updated memory and current node, or ``None`` when a
            mode rejects the edge.
        """
        used = walk.used
        if self._engine._match_mode is MatchMode.DIFFERENT_EDGES and edge.id in used:
            return None
        memory = self._apply_memory(walk.memory, edge, target)
        if memory is None:
            return None
        inner: list[ModeMemory] = []
        for item in walk.inner:
            advanced = self._apply_memory(item, edge, target)
            if advanced is None:
                return None
            inner.append(advanced)
        if self._engine._match_mode is MatchMode.DIFFERENT_EDGES:
            used = used | {edge.id}
        return dataclasses.replace(
            walk,
            current=target,
            used=used,
            memory=memory,
            inner=tuple(inner),
        )

    @staticmethod
    def _apply_memory(
        memory: ModeMemory,
        edge: Relationship,
        target: Node,
    ) -> ModeMemory | None:
        """Apply one path-mode memory to a candidate edge.

        Parameters
        ----------
        memory : ModeMemory
            Memory to update.
        edge : Relationship
            Candidate relationship.
        target : Node
            Node reached through the relationship.

        Returns
        -------
        ModeMemory | None
            Updated memory, or ``None`` when the mode rejects the edge.
        """
        used = memory.used
        visited = memory.visited
        closed = memory.closed
        if memory.mode is PathMode.TRAIL:
            if edge.id in used:
                return None
            used = used | {edge.id}
        elif memory.mode in {PathMode.SIMPLE, PathMode.ACYCLIC}:
            if closed:
                return None
            if target.id in visited:
                if memory.mode is PathMode.SIMPLE and target.id == memory.start_id:
                    closed = True
                else:
                    return None
            else:
                visited = visited | {target.id}
        return dataclasses.replace(
            memory,
            used=used,
            visited=visited,
            closed=closed,
        )

    def _walk_group(
        self,
        term: GroupedPathTerm,
        walk: TermWalk,
        snapshot: TraversalSource,
        max_length: int | None,
    ) -> Iterator[TermWalk]:
        """Walk one grouped term.

        Parameters
        ----------
        term : GroupedPathTerm
            Grouped term to walk.
        walk : TermWalk
            Walk at the group boundary.
        snapshot : TraversalSource
            Captured adjacency source.
        max_length : int | None
            Maximum relationship count, or ``None``.

        Yields
        ------
        TermWalk
            Walk after a permitted number of iterations.
        """
        if term.quantifier.min_hops == 0:
            yield dataclasses.replace(walk, binding=self._empty_group_binding(term, walk))
        if term.quantifier.max_hops == 0:
            return
        mode = term.mode if term.mode is not None else PathMode.WALK
        memory = ModeMemory(
            mode=mode,
            start_id=walk.current.id,
            visited=(
                frozenset({walk.current.id})
                if mode in {PathMode.SIMPLE, PathMode.ACYCLIC}
                else frozenset()
            ),
        )
        entered = dataclasses.replace(walk, inner=(*walk.inner, memory))
        yield from self._walk_group_iterations(
            term,
            entered,
            snapshot,
            max_length,
            start_path_len=len(walk.path_nodes),
            start_rel_len=len(walk.path_rels),
        )

    def _walk_group_iterations(
        self,
        term: GroupedPathTerm,
        walk: TermWalk,
        snapshot: TraversalSource,
        max_length: int | None,
        *,
        start_path_len: int,
        start_rel_len: int,
    ) -> Iterator[TermWalk]:
        """Walk repeated iterations of one group without call recursion.

        Parameters
        ----------
        term : GroupedPathTerm
            Grouped term being repeated.
        walk : TermWalk
            Walk at the group boundary with the inner mode memory pushed.
        snapshot : TraversalSource
            Captured adjacency source.
        max_length : int | None
            Maximum relationship count, or ``None``.
        start_path_len : int
            Path node count at the group boundary.
        start_rel_len : int
            Path relationship count at the group boundary.

        Yields
        ------
        TermWalk
            Walk after closing the group.
        """
        outer_binding = dict(walk.binding)
        stack: list[
            tuple[
                TermWalk,
                int,
                Mapping[str, list[QueryValue]],
                Iterator[TermWalk] | None,
            ]
        ] = [(walk, 0, {}, None)]
        while stack:
            current, iteration, accumulated, iterator = stack[-1]
            if iterator is None:
                iterator = self._walk_terms(
                    term.pattern.terms,
                    0,
                    current,
                    snapshot,
                    max_length,
                )
                stack[-1] = (current, iteration, accumulated, iterator)
            try:
                inner = next(iterator)
            except StopIteration:
                stack.pop()
                continue
            if len(inner.path_rels) <= len(current.path_rels):
                continue
            base_binding, collected = self._accumulate(
                term,
                inner.binding,
                accumulated,
                outer_binding,
            )
            count = iteration + 1
            if count >= term.quantifier.min_hops:
                binding = self._close_group_binding(
                    term,
                    base_binding,
                    collected,
                    inner.path_nodes,
                    inner.path_rels,
                    start_path_len,
                    start_rel_len,
                )
                if binding is not None:
                    yield dataclasses.replace(
                        inner,
                        binding=binding,
                        inner=inner.inner[:-1],
                    )
            if term.quantifier.max_hops is not None and count >= term.quantifier.max_hops:
                continue
            next_walk = dataclasses.replace(
                inner,
                binding=self._strip_group_binding(term, inner.binding, outer_binding),
            )
            stack.append((next_walk, count, collected, None))

    def _empty_group_binding(
        self,
        term: GroupedPathTerm,
        walk: TermWalk,
    ) -> dict[str, QueryValue]:
        """Bind every group variable to an empty list for zero iterations.

        Parameters
        ----------
        term : GroupedPathTerm
            Group taking no iteration.
        walk : TermWalk
            Walk at the group boundary.

        Returns
        -------
        dict[str, QueryValue]
            Binding extended with empty lists.
        """
        binding = dict(walk.binding)
        for name in self._group_variables(term):
            if name not in binding:
                binding[name] = []
        return binding

    def _accumulate(
        self,
        term: GroupedPathTerm,
        binding: Mapping[str, QueryValue],
        accumulated: Mapping[str, list[QueryValue]],
        outer_binding: Mapping[str, QueryValue],
    ) -> tuple[dict[str, QueryValue], dict[str, list[QueryValue]]]:
        """Collect group variables from one completed iteration.

        Parameters
        ----------
        term : GroupedPathTerm
            Group being repeated.
        binding : Mapping[str, QueryValue]
            Binding produced by the iteration.
        accumulated : Mapping[str, list[QueryValue]]
            Values collected from earlier iterations.
        outer_binding : Mapping[str, QueryValue]
            Binding at the group boundary.

        Returns
        -------
        tuple[dict[str, QueryValue], dict[str, list[QueryValue]]]
            Binding without the current iteration's group variables, and the
            updated accumulators.
        """
        base = dict(binding)
        values = {name: list(items) for name, items in accumulated.items()}
        for name in self._group_variables(term):
            if name in outer_binding:
                continue
            value = base.pop(name, self._engine._MISSING)
            if value is self._engine._MISSING:
                continue
            target = values.setdefault(name, [])
            if isinstance(value, list):
                target.extend(value)
            elif value is not None:
                target.append(typing.cast(QueryValue, value))
        return base, values

    def _strip_group_binding(
        self,
        term: GroupedPathTerm,
        binding: Mapping[str, QueryValue],
        outer_binding: Mapping[str, QueryValue],
    ) -> dict[str, QueryValue]:
        """Remove group variables before the next iteration.

        Parameters
        ----------
        term : GroupedPathTerm
            Group being repeated.
        binding : Mapping[str, QueryValue]
            Binding after one iteration.
        outer_binding : Mapping[str, QueryValue]
            Binding at the group boundary.

        Returns
        -------
        dict[str, QueryValue]
            Binding without group-local values.
        """
        stripped = dict(binding)
        for name in self._group_variables(term):
            if name not in outer_binding:
                stripped.pop(name, None)
        return stripped

    def _close_group_binding(
        self,
        term: GroupedPathTerm,
        binding: Mapping[str, QueryValue],
        accumulated: Mapping[str, list[QueryValue]],
        path_nodes: Sequence[Node],
        path_rels: Sequence[Relationship],
        start_path_len: int,
        start_rel_len: int,
    ) -> dict[str, QueryValue] | None:
        """Bind the flattened lists and group path variable.

        Parameters
        ----------
        term : GroupedPathTerm
            Group being closed.
        binding : Mapping[str, QueryValue]
            Binding without the current iteration's group variables.
        accumulated : Mapping[str, list[QueryValue]]
            Flattened group variable values.
        path_nodes : Sequence[Node]
            Nodes of the complete walk.
        path_rels : Sequence[Relationship]
            Relationships of the complete walk.
        start_path_len : int
            Path node count at the group boundary.
        start_rel_len : int
            Path relationship count at the group boundary.

        Returns
        -------
        dict[str, QueryValue] | None
            Closed binding, or ``None`` on a path-variable conflict.
        """
        closed = dict(binding)
        for name, values in accumulated.items():
            closed[name] = values
        if term.variable is None:
            return closed
        path = Path(
            nodes=tuple(path_nodes[start_path_len - 1 :]),
            relationships=tuple(path_rels[start_rel_len:]),
        )
        existing = closed.get(term.variable, self._engine._MISSING)
        if existing is self._engine._MISSING:
            closed[term.variable] = path
            return closed
        if isinstance(existing, Path) and existing == path:
            return closed
        return None

    def _group_variables(self, term: GroupedPathTerm) -> tuple[str, ...]:
        """Return node and relationship variables introduced by a group.

        Parameters
        ----------
        term : GroupedPathTerm
            Group to inspect.

        Returns
        -------
        tuple[str, ...]
            Variable names in traversal order, without duplicates.
        """
        names: list[str] = []
        for inner in term.pattern.terms:
            if isinstance(inner, SimplePathTerm):
                for node in inner.nodes:
                    if node.variable is not None:
                        names.append(node.variable)
                for relationship in inner.relationships:
                    if relationship.variable is not None:
                        names.append(relationship.variable)
            else:
                names.extend(self._group_variables(inner))
        return tuple(dict.fromkeys(names))


class PathSearchEvaluator:
    """Select paths in nondecreasing length order for one search prefix.

    Parameters
    ----------
    engine : PatternEngine
        Matcher whose node selection, predicates, bindings, and mode helpers
        are reused.
    """

    def __init__(self, engine: PatternEngine) -> None:
        self._engine = engine

    def iter_pattern(
        self,
        pattern: PathPattern,
        base: Mapping[str, QueryValue],
        used: frozenset[int],
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Yield the paths selected for one pattern and input row.

        Parameters
        ----------
        pattern : PathPattern
            Pattern carrying a path-search prefix.
        base : Mapping[str, QueryValue]
            Variables bound before the pattern starts.
        used : frozenset[int]
            Relationship identifiers already bound by the clause.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Selected binding and the relationships it used.
        """
        search = pattern.search
        if search is None:
            return
        if search.kind is PathSearchKind.SHORTEST and search.k == 0:
            return
        first = pattern.nodes[0]
        initial = used if self._engine._match_mode is MatchMode.DIFFERENT_EDGES else frozenset()
        starts = sorted(self._engine._start_nodes(first, base), key=lambda node: node.id)
        for start in starts:
            binding = self._engine._bind_node(first, start, base)
            if binding is None:
                continue
            snapshot = self._engine._capture(start, pattern)
            mode = self._engine._mode(pattern)
            visited = (
                frozenset({start.id})
                if mode in {PathMode.SIMPLE, PathMode.ACYCLIC}
                else frozenset()
            )
            root = WalkState(
                position=0,
                current=start.id,
                hops=0,
                segment_rels=(),
                segment_nodes=(),
                path_nodes=(start,),
                path_rels=(),
                used=initial,
                visited=visited,
                closed=False,
                binding=binding,
            )
            for end in self._end_candidates(pattern, base, first, start):
                yield from self._search_partition(
                    pattern,
                    root,
                    snapshot,
                    end.id,
                    search,
                )

    def _end_candidates(
        self,
        pattern: PathPattern,
        base: Mapping[str, QueryValue],
        first: NodePattern,
        start: Node,
    ) -> tuple[Node, ...]:
        """Return candidate end nodes for one start node.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        base : Mapping[str, QueryValue]
            Variables bound before the pattern starts.
        first : NodePattern
            First node pattern.
        start : Node
            Candidate start node.

        Returns
        -------
        tuple[Node, ...]
            Nodes matching the final node pattern, in ascending id order.
        """
        if not pattern.all_relationships():
            return (start,)
        last = pattern.last_node
        if last.variable is not None:
            if last.variable == first.variable:
                return (start,)
            if last.variable in base:
                value = base[last.variable]
                return (value,) if isinstance(value, Node) else ()
        candidates = self._engine._select_nodes(
            last,
            self._engine._parameters,
            self._engine._evaluator,
            base,
        )
        seen: set[int] = set()
        unique: list[Node] = []
        for node in sorted(candidates, key=lambda candidate: candidate.id):
            if node.id in seen:
                continue
            seen.add(node.id)
            unique.append(node)
        return tuple(unique)

    def _search_partition(
        self,
        pattern: PathPattern,
        root: WalkState,
        snapshot: TraversalSource,
        end_id: int,
        search: PathSearch,
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Select paths for one start and end pair.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        root : WalkState
            Walk state at the start node.
        snapshot : TraversalSource
            Captured region.
        end_id : int
            Required end node identifier.
        search : PathSearch
            Selection rule.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Selected binding and its used relationships, in selection order.
        """
        if search.kind is PathSearchKind.SHORTEST and search.k == 0:
            return
        start_id = root.path_nodes[0].id
        heap: list[tuple[int, tuple[tuple[int, int], ...], tuple[int, ...], int, WalkState]] = []
        best: dict[tuple[object, ...], list[int]] = {}
        counter = 0
        seen_paths: set[tuple[tuple[int, ...], tuple[tuple[int, int], ...]]] = set()
        selected: list[tuple[dict[str, QueryValue], frozenset[int]]] = []
        min_length: int | None = None

        def push(state: WalkState) -> None:
            nonlocal counter
            length = self._length(state)
            if not self._admit(best, self._state_key(pattern, state, start_id), length, search):
                return
            _, relationships, nodes = self._sequences(state)
            counter += 1
            heapq.heappush(heap, (length, relationships, nodes, counter, state))

        push(root)
        while heap:
            length, relationships, nodes, _, state = heapq.heappop(heap)
            if min_length is not None and length > min_length:
                break
            if state.position == len(pattern.relationships):
                if state.current != end_id:
                    continue
                for binding, used_after in self._engine._finish(pattern, state, snapshot):
                    identity = (nodes, relationships)
                    if identity in seen_paths:
                        continue
                    seen_paths.add(identity)
                    selected.append((binding, used_after))
                    if search.kind in {PathSearchKind.ANY, PathSearchKind.ANY_SHORTEST}:
                        yield selected[-1]
                        return
                    if search.kind is PathSearchKind.SHORTEST:
                        if len(selected) >= typing.cast(int, search.k):
                            yield from selected
                            return
                    elif min_length is None:
                        min_length = length
                continue
            relationship = pattern.relationships[state.position]
            for child in self._children(pattern, state, relationship, snapshot):
                child_length = self._length(child)
                if (
                    min_length is not None
                    and search.kind is PathSearchKind.ALL_SHORTEST
                    and child_length > min_length
                ):
                    continue
                push(child)
        yield from selected

    def _children(
        self,
        pattern: PathPattern,
        state: WalkState,
        relationship: RelationshipPattern,
        snapshot: TraversalSource,
    ) -> Iterator[WalkState]:
        """Yield the states reachable from one search state.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            State to expand.
        relationship : RelationshipPattern
            Relationship position at the state.
        snapshot : TraversalSource
            Captured region.

        Yields
        ------
        WalkState
            A closure or one-hop child state.
        """
        quantified = relationship.min_hops is not None or relationship.max_hops is not None
        minimum = 1 if relationship.min_hops is None else relationship.min_hops
        maximum = relationship.max_hops
        if quantified and state.hops >= minimum:
            closed = self._engine._close_segment_state(
                pattern,
                state,
                relationship,
                snapshot,
            )
            if closed is not None:
                yield closed
        if state.closed:
            return
        if quantified and maximum is not None and state.hops >= maximum:
            return
        types = frozenset(relationship.types) if relationship.types else None
        for edge, target_id in self._engine._arrow_edges(
            snapshot,
            state.current,
            relationship.direction,
            types,
        ):
            self._engine._consume_expansion()
            if not self._engine._relationship_matches(relationship, edge, state.binding):
                continue
            if quantified:
                child = self._engine._advance_quantified_state(
                    pattern,
                    state,
                    edge,
                    target_id,
                    snapshot,
                )
            else:
                child = self._engine._advance_fixed_state(
                    pattern,
                    state,
                    relationship,
                    edge,
                    target_id,
                    snapshot,
                )
            if child is not None:
                yield child

    def _admit(
        self,
        best: dict[tuple[object, ...], list[int]],
        key: tuple[object, ...],
        length: int,
        search: PathSearch,
    ) -> bool:
        """Report whether an arrival can still contribute a selected path.

        Parameters
        ----------
        best : dict[tuple[object, ...], list[int]]
            Arrival lengths already kept for each state key.
        key : tuple[object, ...]
            State key of the arrival.
        length : int
            Path length of the arrival.
        search : PathSearch
            Selection rule.

        Returns
        -------
        bool
            ``True`` when the arrival is retained.
        """
        lengths = best.setdefault(key, [])
        if search.kind is PathSearchKind.ALL_SHORTEST:
            if not lengths or length < lengths[0]:
                lengths[:] = [length]
                return True
            if length == lengths[0]:
                lengths.append(length)
                return True
            return False
        if search.kind is PathSearchKind.SHORTEST:
            cap = typing.cast(int, search.k)
            if len(lengths) < cap:
                lengths.append(length)
                lengths.sort()
                return True
            if length < lengths[-1]:
                lengths[-1] = length
                lengths.sort()
                return True
            return False
        if not lengths or length < lengths[0]:
            lengths[:] = [length]
            return True
        return False

    def _state_key(
        self,
        pattern: PathPattern,
        state: WalkState,
        start_id: int,
    ) -> tuple[object, ...]:
        """Build the pruning key of one search state.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        state : WalkState
            State to key.
        start_id : int
            Start node identifier.

        Returns
        -------
        tuple[object, ...]
            Hashable state key.
        """
        hops = 0
        if state.position < len(pattern.relationships):
            relationship = pattern.relationships[state.position]
            if relationship.min_hops is not None or relationship.max_hops is not None:
                minimum = 1 if relationship.min_hops is None else relationship.min_hops
                hops = min(state.hops, minimum)
        return (
            start_id,
            state.current,
            state.position,
            hops,
            state.used,
            state.visited,
            state.closed,
            self._binding_key(state.binding),
        )

    @staticmethod
    def _length(state: WalkState) -> int:
        """Return the traversed relationship count of one state.

        Parameters
        ----------
        state : WalkState
            State to measure.

        Returns
        -------
        int
            Number of relationships in the path so far.
        """
        return len(state.path_rels) + len(state.segment_rels)

    @staticmethod
    def _sequences(
        state: WalkState,
    ) -> tuple[int, tuple[tuple[int, int], ...], tuple[int, ...]]:
        """Return the length and tie-break sequences of one state.

        Parameters
        ----------
        state : WalkState
            State to inspect.

        Returns
        -------
        tuple[int, tuple[tuple[int, int], ...], tuple[int, ...]]
            Path length, orientation-aware relationship sequence, and node
            identifier sequence.
        """
        relationships = (*state.path_rels, *state.segment_rels)
        nodes = (*state.path_nodes, *state.segment_nodes)
        sequence = tuple(
            (relationship.id, 0 if nodes[index + 1].id == relationship.end_id else 1)
            for index, relationship in enumerate(relationships)
        )
        return len(relationships), sequence, tuple(node.id for node in nodes)

    @staticmethod
    def _binding_key(binding: Mapping[str, QueryValue]) -> tuple[object, ...]:
        """Build the element-binding part of a search state key.

        Parameters
        ----------
        binding : Mapping[str, QueryValue]
            Variables bound in the state.

        Returns
        -------
        tuple[object, ...]
            Sorted element and element-list identities.
        """
        items: list[tuple[str, int, object]] = []
        for name, value in sorted(binding.items()):
            if isinstance(value, Node):
                items.append((name, 0, value.id))
            elif isinstance(value, Relationship):
                items.append((name, 1, value.id))
            elif isinstance(value, list):
                items.append(
                    (
                        name,
                        2,
                        tuple(
                            element.id
                            for element in value
                            if isinstance(element, Node | Relationship)
                        ),
                    )
                )
        return tuple(items)


class GroupedSearchEvaluator:
    """Select grouped paths in nondecreasing length order.

    Parameters
    ----------
    engine : PatternEngine
        Engine whose node selection, bindings, and grouped matcher are reused.
    """

    def __init__(self, engine: PatternEngine) -> None:
        self._engine = engine
        self._matcher = GroupedMatcher(engine)

    def iter_pattern(
        self,
        pattern: PathPattern,
        base: Mapping[str, QueryValue],
        used: frozenset[int],
    ) -> Iterator[tuple[dict[str, QueryValue], frozenset[int]]]:
        """Yield selected paths for one grouped pattern and input row.

        Parameters
        ----------
        pattern : PathPattern
            Grouped pattern carrying a search prefix.
        base : Mapping[str, QueryValue]
            Variables bound before the pattern.
        used : frozenset[int]
            Relationships already bound by the clause.

        Yields
        ------
        tuple[dict[str, QueryValue], frozenset[int]]
            Selected binding and its used relationships.
        """
        search = pattern.search
        if search is None:
            return
        if search.kind is PathSearchKind.SHORTEST and search.k == 0:
            return
        starts = sorted(
            self._engine._start_nodes(pattern.first_node, base),
            key=lambda node: node.id,
        )
        node_count = sum(1 for _ in self._engine._nodes.all())
        if search.kind is PathSearchKind.SHORTEST:
            k = typing.cast(int, search.k)
            max_length = max(1, node_count * max(1, k + 1))
        else:
            max_length = max(1, node_count)
        for start in starts:
            for end in self._end_candidates(pattern, base, start):
                selected = 0
                for length in range(max_length + 1):
                    walks = [
                        walk
                        for walk in self._matcher.iter_matches(
                            pattern,
                            base,
                            used,
                            start=start,
                            max_length=length,
                        )
                        if len(walk.path_rels) == length and walk.path_nodes[-1].id == end.id
                    ]
                    if not walks:
                        continue
                    unique = self._select(walks)
                    if search.kind in {PathSearchKind.ANY, PathSearchKind.ANY_SHORTEST}:
                        yield dict(unique[0].binding), unique[0].used
                        break
                    if search.kind is PathSearchKind.ALL_SHORTEST:
                        for walk in unique:
                            yield dict(walk.binding), walk.used
                        break
                    remaining = typing.cast(int, search.k) - selected
                    for walk in unique[:remaining]:
                        selected += 1
                        yield dict(walk.binding), walk.used
                    if selected >= typing.cast(int, search.k):
                        break

    def _end_candidates(
        self,
        pattern: PathPattern,
        base: Mapping[str, QueryValue],
        start: Node,
    ) -> tuple[Node, ...]:
        """Return candidate end nodes for one grouped start node.

        Parameters
        ----------
        pattern : PathPattern
            Pattern being matched.
        base : Mapping[str, QueryValue]
            Variables bound before the pattern.
        start : Node
            Candidate start node.

        Returns
        -------
        tuple[Node, ...]
            Nodes matching the final node pattern, in ascending id order.
        """
        if not pattern.all_relationships():
            return (start,)
        last = pattern.last_node
        first = pattern.first_node
        if last.variable is not None:
            if last.variable == first.variable:
                return (start,)
            if last.variable in base:
                value = base[last.variable]
                return (value,) if isinstance(value, Node) else ()
        candidates = self._engine._select_nodes(
            last,
            self._engine._parameters,
            self._engine._evaluator,
            base,
        )
        seen: set[int] = set()
        unique: list[Node] = []
        for node in sorted(candidates, key=lambda candidate: candidate.id):
            if node.id in seen:
                continue
            seen.add(node.id)
            unique.append(node)
        return tuple(unique)

    @classmethod
    def _select(cls, walks: Sequence[TermWalk]) -> list[TermWalk]:
        """Sort and deduplicate completed paths for one partition.

        Parameters
        ----------
        walks : Sequence[TermWalk]
            Completed paths at one length.

        Returns
        -------
        list[TermWalk]
            Distinct paths in deterministic tie-break order.
        """
        ordered = sorted(walks, key=cls._tie_break)
        selected: list[TermWalk] = []
        seen: set[tuple[tuple[tuple[int, int], ...], tuple[int, ...]]] = set()
        for walk in ordered:
            identity = cls._identity(walk)
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(walk)
        return selected

    @classmethod
    def _tie_break(
        cls,
        walk: TermWalk,
    ) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...]]:
        """Return the relationship and node tie-break sequences.

        Parameters
        ----------
        walk : TermWalk
            Completed path.

        Returns
        -------
        tuple[tuple[tuple[int, int], ...], tuple[int, ...]]
            Orientation-aware relationship sequence and node sequence.
        """
        return cls._identity(walk)

    @staticmethod
    def _identity(
        walk: TermWalk,
    ) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...]]:
        """Return the path identity used for ordering and deduplication.

        Parameters
        ----------
        walk : TermWalk
            Completed path.

        Returns
        -------
        tuple[tuple[tuple[int, int], ...], tuple[int, ...]]
            Orientation-aware relationship sequence and node sequence.
        """
        sequence = tuple(
            (
                relationship.id,
                0 if walk.path_nodes[index + 1].id == relationship.end_id else 1,
            )
            for index, relationship in enumerate(walk.path_rels)
        )
        return sequence, tuple(node.id for node in walk.path_nodes)


__all__ = [
    "GroupedMatcher",
    "GroupedSearchEvaluator",
    "ModeMemory",
    "NodeSelector",
    "PathSearchEvaluator",
    "PatternEngine",
    "TermWalk",
    "WalkState",
]
