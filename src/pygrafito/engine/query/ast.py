# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Frozen abstract syntax tree nodes for the query language."""

import dataclasses
from enum import Enum

from pygrafito.engine.query.tokens import Span
from pygrafito.model import Direction


class Operators:
    """Operator spellings shared by the parser, analyser, and evaluator."""

    EQUAL: str = "="
    NOT_EQUAL: str = "<>"
    LESS: str = "<"
    LESS_EQUAL: str = "<="
    GREATER: str = ">"
    GREATER_EQUAL: str = ">="
    AND: str = "AND"
    OR: str = "OR"
    NOT: str = "NOT"
    IN: str = "IN"
    STARTS_WITH: str = "STARTS WITH"
    ENDS_WITH: str = "ENDS WITH"
    CONTAINS: str = "CONTAINS"
    ADD: str = "+"
    CONCAT: str = "||"
    SUBTRACT: str = "-"
    MULTIPLY: str = "*"
    DIVIDE: str = "/"
    MODULO: str = "%"
    NEGATE: str = "-"
    POSITIVE: str = "+"


@dataclasses.dataclass(frozen=True, slots=True)
class Literal:
    """A literal scalar or null value.

    Parameters
    ----------
    value : bool | int | float | str | None
        Decoded literal value.
    """

    value: bool | int | float | str | None


@dataclasses.dataclass(frozen=True, slots=True)
class ListLiteral:
    """A list literal.

    Parameters
    ----------
    items : tuple[Expression, ...]
        Element expressions.
    """

    items: tuple[Expression, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class CaseBranch:
    """One ``WHEN ... THEN ...`` branch of a ``CASE`` expression.

    Parameters
    ----------
    match : Expression
        Value or predicate compared or tested by the branch.
    result : Expression
        Result produced when the branch matches.
    """

    match: Expression
    result: Expression


@dataclasses.dataclass(frozen=True, slots=True)
class Case:
    """A simple or searched ``CASE`` expression.

    Parameters
    ----------
    operand : Expression | None
        Simple-case operand, or ``None`` for a searched case.
    branches : tuple[CaseBranch, ...]
        Branches in evaluation order.
    default : Expression | None
        Optional ``ELSE`` result.
    """

    operand: Expression | None
    branches: tuple[CaseBranch, ...]
    default: Expression | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class MapEntry:
    """One key-value entry in an expression map literal.

    Parameters
    ----------
    key : str
        Static key name.
    value : Expression
        Value expression.
    """

    key: str
    value: Expression


@dataclasses.dataclass(frozen=True, slots=True)
class MapLiteral:
    """A map literal such as ``{designation: 'Tron'}``.

    Parameters
    ----------
    entries : tuple[MapEntry, ...]
        Entries in source order.
    """

    entries: tuple[MapEntry, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class ListAccess:
    """A list index access.

    Parameters
    ----------
    target : Expression
        List-producing expression.
    index : Expression
        Zero-based index expression.
    """

    target: Expression
    index: Expression


@dataclasses.dataclass(frozen=True, slots=True)
class ListSlice:
    """A list slice such as ``values[start:end]``.

    Parameters
    ----------
    target : Expression
        List-producing expression.
    start : Expression | None
        Inclusive start bound, or ``None`` for the beginning.
    end : Expression | None
        Exclusive end bound, or ``None`` for the end.
    """

    target: Expression
    start: Expression | None
    end: Expression | None


@dataclasses.dataclass(frozen=True, slots=True)
class ListComprehension:
    """A list comprehension.

    Parameters
    ----------
    variable : str
        Local loop variable.
    source : Expression
        Source list expression.
    where : Expression | None
        Optional filter predicate.
    projection : Expression | None
        Optional projection expression; the element is emitted when absent.
    """

    variable: str
    source: Expression
    where: Expression | None = None
    projection: Expression | None = None


class SubqueryKind(Enum):
    """Kind of query expression used inside a scalar expression."""

    EXISTS = "EXISTS"
    COUNT = "COUNT"


@dataclasses.dataclass(frozen=True, slots=True)
class Subquery:
    """A read-only ``EXISTS { ... }`` or ``COUNT { ... }`` expression.

    Parameters
    ----------
    kind : SubqueryKind
        Whether the expression tests existence or counts inner rows.
    clauses : tuple[Clause, ...]
        Read-stage clauses of the inner query.
    """

    kind: SubqueryKind
    clauses: tuple[Clause, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Variable:
    """A reference to a pattern variable.

    Parameters
    ----------
    name : str
        Case-sensitive variable name.
    span : Span | None, optional
        Source position of the reference, by default ``None``.
    """

    name: str
    span: Span | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Parameter:
    """A ``$name`` query parameter.

    Parameters
    ----------
    name : str
        Parameter name without the leading dollar sign.
    span : Span | None, optional
        Source position of the reference, by default ``None``.
    """

    name: str
    span: Span | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Property:
    """A property or mapping access such as ``n.designation``.

    Parameters
    ----------
    target : Expression
        Expression producing a node, relationship, or mapping.
    key : str
        Exact property key.
    span : Span | None, optional
        Source position of the access, by default ``None``.
    """

    target: Expression
    key: str
    span: Span | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class FunctionCall:
    """A scalar or aggregate function call.

    Parameters
    ----------
    name : str
        Function name as written; matching is case-insensitive.
    arguments : tuple[Expression, ...]
        Evaluated argument expressions.
    distinct : bool, optional
        Whether the call carries ``DISTINCT``, by default ``False``.
    span : Span | None, optional
        Source position of the call, by default ``None``.
    """

    name: str
    arguments: tuple[Expression, ...]
    distinct: bool = False
    span: Span | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Unary:
    """A prefix unary operation.

    Parameters
    ----------
    operator : str
        Operator spelling.
    operand : Expression
        Operand expression.
    """

    operator: str
    operand: Expression


@dataclasses.dataclass(frozen=True, slots=True)
class Binary:
    """An infix operation such as arithmetic, comparison, or boolean logic.

    Parameters
    ----------
    left : Expression
        Left operand.
    operator : str
        Operator spelling.
    right : Expression
        Right operand.
    """

    left: Expression
    operator: str
    right: Expression


@dataclasses.dataclass(frozen=True, slots=True)
class IsNull:
    """An ``IS NULL`` or ``IS NOT NULL`` test.

    Parameters
    ----------
    operand : Expression
        Expression whose nullness is tested.
    negated : bool, optional
        Whether the test is ``IS NOT NULL``, by default ``False``.
    """

    operand: Expression
    negated: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class Star:
    """The ``*`` argument of ``count(*)``."""


type Expression = (
    Literal
    | ListLiteral
    | Variable
    | Parameter
    | Property
    | FunctionCall
    | Unary
    | Binary
    | IsNull
    | Star
    | Case
    | MapLiteral
    | ListAccess
    | ListSlice
    | ListComprehension
    | Subquery
)


@dataclasses.dataclass(frozen=True, slots=True)
class PropertyEntry:
    """One key-value entry in a pattern property map.

    Parameters
    ----------
    key : str
        Exact property key.
    value : Expression
        Constant or parameter expression supplying the expected value.
    """

    key: str
    value: Expression


@dataclasses.dataclass(frozen=True, slots=True)
class LabelName:
    """A single required label.

    Parameters
    ----------
    name : str
        Exact label name.
    """

    name: str


@dataclasses.dataclass(frozen=True, slots=True)
class LabelAnd:
    """A conjunction of two label expressions."""

    left: LabelExpression
    right: LabelExpression


@dataclasses.dataclass(frozen=True, slots=True)
class LabelOr:
    """A disjunction of two label expressions."""

    left: LabelExpression
    right: LabelExpression


@dataclasses.dataclass(frozen=True, slots=True)
class LabelNot:
    """A negated label expression.

    Parameters
    ----------
    operand : LabelExpression
        Expression to negate.
    """

    operand: LabelExpression


@dataclasses.dataclass(frozen=True, slots=True)
class LabelWildcard:
    """The wildcard label expression, matching any element."""


type LabelExpression = LabelName | LabelAnd | LabelOr | LabelNot | LabelWildcard


class PathMode(Enum):
    """Path repetition rule resolved for one path pattern."""

    WALK = "walk"
    TRAIL = "trail"
    SIMPLE = "simple"
    ACYCLIC = "acyclic"


class MatchMode(Enum):
    """Relationship-sharing rule resolved for one ``MATCH`` clause."""

    REPEATABLE_ELEMENTS = "repeatable elements"
    DIFFERENT_EDGES = "different edges"


class PathSearchKind(Enum):
    """Selection rule applied to the paths of one pattern."""

    ANY = "ANY"
    ANY_SHORTEST = "ANY SHORTEST"
    ALL_SHORTEST = "ALL SHORTEST"
    SHORTEST = "SHORTEST"


@dataclasses.dataclass(frozen=True, slots=True)
class PathSearch:
    """A path-search prefix attached to one path pattern.

    Parameters
    ----------
    kind : PathSearchKind
        Selection rule to apply.
    k : int | None, optional
        Number of paths selected by ``SHORTEST k``, by default ``None`` for
        the other prefixes.
    span : Span | None, optional
        Source position of the prefix, by default ``None``.
    """

    kind: PathSearchKind
    k: int | None = None
    span: Span | None = None


class OrdinalityKind(Enum):
    """Base used by an iteration position variable."""

    ORDINALITY = "ordinality"
    OFFSET = "offset"


class EdgeDirection(Enum):
    """Storage directions one relationship position admits."""

    OUTGOING = "outgoing"
    INCOMING = "incoming"
    ANY = "any"
    UNDIRECTED = "undirected"
    DIRECTED_EITHER = "directed-either"
    INCOMING_OR_UNDIRECTED = "incoming-or-undirected"
    OUTGOING_OR_UNDIRECTED = "outgoing-or-undirected"

    @property
    def traversal(self) -> Direction:
        """Return the traversal direction used to enumerate candidates.

        Returns
        -------
        Direction
            Outgoing, incoming, or both incident relationships.
        """
        if self is EdgeDirection.OUTGOING:
            return Direction.OUTGOING
        if self is EdgeDirection.INCOMING:
            return Direction.INCOMING
        if self is EdgeDirection.INCOMING_OR_UNDIRECTED:
            return Direction.INCOMING
        if self is EdgeDirection.OUTGOING_OR_UNDIRECTED:
            return Direction.OUTGOING
        return Direction.BOTH

    @property
    def directedness(self) -> bool | None:
        """Return the admission rule for directed relationships.

        Returns
        -------
        bool | None
            ``True`` for directed relationships only, ``False`` for undirected
            relationships only, and ``None`` when both kinds are admitted.
        """
        if self in {EdgeDirection.OUTGOING, EdgeDirection.INCOMING, EdgeDirection.DIRECTED_EITHER}:
            return True
        if self is EdgeDirection.UNDIRECTED:
            return False
        return None


@dataclasses.dataclass(frozen=True, slots=True)
class NodePattern:
    """One node position inside a path pattern.

    Parameters
    ----------
    variable : str | None, optional
        Bound variable, or ``None`` for an anonymous node.
    labels : tuple[str, ...], optional
        Labels every match must carry, by default none.
    properties : tuple[PropertyEntry, ...], optional
        Property map every match must satisfy, by default none.
    label_expression : LabelExpression | None, optional
        Parsed label expression, or ``None`` when the pattern names no labels.
    where : Expression | None, optional
        Inline predicate scoped to the node, by default ``None``.
    """

    variable: str | None = None
    labels: tuple[str, ...] = ()
    properties: tuple[PropertyEntry, ...] = ()
    label_expression: LabelExpression | None = None
    where: Expression | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipPattern:
    """One relationship position inside a path pattern.

    Parameters
    ----------
    variable : str | None, optional
        Bound variable, or ``None`` for an anonymous relationship.
    types : tuple[str, ...], optional
        Accepted relationship types, by default any type.
    direction : EdgeDirection, optional
        Storage direction this position admits, by default outgoing.
    properties : tuple[PropertyEntry, ...], optional
        Property map every match must satisfy, by default none.
    min_hops : int | None, optional
        Minimum relationship count for a quantified pattern, by default
        ``None`` for an ordinary one-hop relationship.
    max_hops : int | None, optional
        Maximum relationship count for a quantified pattern, by default
        ``None``. A quantified position with ``min_hops`` set and
        ``max_hops`` absent is open-ended; both bounds are absent for an
        ordinary one-hop relationship.
    canonical_quantifier : bool, optional
        Whether the quantifier uses the canonical ``{n,m}`` spelling, by
        default ``False`` for the legacy ``*n..m`` spelling and ordinary
        relationships.
    label_expression : LabelExpression | None, optional
        Parsed relationship label expression, or ``None`` when it names none.
    where : Expression | None, optional
        Inline predicate scoped to the relationship, by default ``None``.
    """

    variable: str | None = None
    types: tuple[str, ...] = ()
    direction: EdgeDirection = EdgeDirection.OUTGOING
    properties: tuple[PropertyEntry, ...] = ()
    min_hops: int | None = None
    max_hops: int | None = None
    canonical_quantifier: bool = False
    label_expression: LabelExpression | None = None
    where: Expression | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class SimplePathTerm:
    """A node pattern followed by relationship-node pairs.

    Parameters
    ----------
    nodes : tuple[NodePattern, ...]
        Nodes from the start of the term to its end.
    relationships : tuple[RelationshipPattern, ...], optional
        Relationships in traversal order, by default none.
    """

    nodes: tuple[NodePattern, ...]
    relationships: tuple[RelationshipPattern, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class HopRange:
    """Repetition bounds of a grouped path term.

    Parameters
    ----------
    min_hops : int
        Minimum number of iterations.
    max_hops : int | None
        Maximum number of iterations, or ``None`` when open-ended.
    """

    min_hops: int
    max_hops: int | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class GroupedPathTerm:
    """A parenthesized path pattern followed by a repetition quantifier.

    Parameters
    ----------
    pattern : PathPattern
        Inner path pattern repeated by the term.
    quantifier : HopRange
        Repetition bounds.
    variable : str | None, optional
        Group path variable, by default ``None``.
    mode : PathMode | None, optional
        Inner path mode, by default ``None``.
    """

    pattern: PathPattern
    quantifier: HopRange
    variable: str | None = None
    mode: PathMode | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class PathPattern:
    """One path pattern made of juxtaposed terms.

    Parameters
    ----------
    terms : tuple[SimplePathTerm | GroupedPathTerm, ...], optional
        Path terms in traversal order, by default empty.
    variable : str | None, optional
        Path variable, or ``None`` when the path is not bound.
    mode : PathMode | None, optional
        Explicit per-path mode from the source, or the mode resolved by static
        analysis, by default ``None``.
    search : PathSearch | None, optional
        Path-search selection attached to the pattern, by default ``None``.
    """

    terms: tuple[SimplePathTerm | GroupedPathTerm, ...] = ()
    variable: str | None = None
    mode: PathMode | None = None
    search: PathSearch | None = None

    @classmethod
    def simple(
        cls,
        *,
        nodes: tuple[NodePattern, ...],
        relationships: tuple[RelationshipPattern, ...] = (),
        variable: str | None = None,
        mode: PathMode | None = None,
        search: PathSearch | None = None,
    ) -> PathPattern:
        """Build a pattern containing one simple term.

        Parameters
        ----------
        nodes : tuple[NodePattern, ...]
            Nodes from the start of the path to its end.
        relationships : tuple[RelationshipPattern, ...], optional
            Relationships in traversal order, by default none.
        variable : str | None, optional
            Path variable, by default ``None``.
        mode : PathMode | None, optional
            Per-path mode, by default ``None``.
        search : PathSearch | None, optional
            Path-search selection, by default ``None``.

        Returns
        -------
        PathPattern
            One-term pattern.
        """
        return cls(
            terms=(SimplePathTerm(nodes=nodes, relationships=relationships),),
            variable=variable,
            mode=mode,
            search=search,
        )

    @property
    def is_simple(self) -> bool:
        """Report whether the pattern has one simple term.

        Returns
        -------
        bool
            ``True`` when the flat node and relationship accessors are valid.
        """
        return len(self.terms) == 1 and isinstance(self.terms[0], SimplePathTerm)

    def flatten(
        self,
    ) -> tuple[tuple[NodePattern, ...], tuple[RelationshipPattern, ...]]:
        """Return the flat nodes and relationships of a simple pattern.

        Returns
        -------
        tuple[tuple[NodePattern, ...], tuple[RelationshipPattern, ...]]
            Nodes and relationships in traversal order.

        Raises
        ------
        ValueError
            If the pattern contains a grouped term or several terms.
        """
        if not self.is_simple:
            message = "the pattern has no flat node and relationship form"
            raise ValueError(message)
        term = self.terms[0]
        if not isinstance(term, SimplePathTerm):
            raise ValueError("the pattern has no flat node and relationship form")
        return term.nodes, term.relationships

    @property
    def nodes(self) -> tuple[NodePattern, ...]:
        """Return the flat nodes of a simple pattern.

        Returns
        -------
        tuple[NodePattern, ...]
            Nodes in traversal order.
        """
        return self.flatten()[0]

    @property
    def relationships(self) -> tuple[RelationshipPattern, ...]:
        """Return the flat relationships of a simple pattern.

        Returns
        -------
        tuple[RelationshipPattern, ...]
            Relationships in traversal order.
        """
        return self.flatten()[1]

    @property
    def first_node(self) -> NodePattern:
        """Return the first node pattern of the path.

        Returns
        -------
        NodePattern
            First node pattern of the first term.
        """
        term = self.terms[0]
        if isinstance(term, SimplePathTerm):
            return term.nodes[0]
        return term.pattern.first_node

    @property
    def last_node(self) -> NodePattern:
        """Return the last node pattern of the path.

        Returns
        -------
        NodePattern
            Last node pattern of the last term.
        """
        term = self.terms[-1]
        if isinstance(term, SimplePathTerm):
            return term.nodes[-1]
        return term.pattern.last_node

    def has_open_position(self) -> bool:
        """Report whether the pattern contains an open repetition.

        Returns
        -------
        bool
            ``True`` when a relationship or grouped term has no upper bound.
        """
        for term in self.terms:
            if isinstance(term, SimplePathTerm):
                if any(
                    relationship.min_hops is not None and relationship.max_hops is None
                    for relationship in term.relationships
                ):
                    return True
            elif term.quantifier.max_hops is None or term.pattern.has_open_position():
                return True
        return False

    def all_relationships(self) -> tuple[RelationshipPattern, ...]:
        """Return every relationship position, including nested groups.

        Returns
        -------
        tuple[RelationshipPattern, ...]
            Relationships in traversal order.
        """
        relationships: list[RelationshipPattern] = []
        for term in self.terms:
            if isinstance(term, SimplePathTerm):
                relationships.extend(term.relationships)
            else:
                relationships.extend(term.pattern.all_relationships())
        return tuple(relationships)

    def has_quantified_relationship(self) -> bool:
        """Report whether any relationship position carries a quantifier.

        Returns
        -------
        bool
            ``True`` when a relationship is quantified, including nested
            groups.
        """
        return any(
            relationship.min_hops is not None or relationship.max_hops is not None
            for relationship in self.all_relationships()
        )

    def minimum_relationships(self) -> int:
        """Return the minimum number of relationships the pattern traverses.

        Returns
        -------
        int
            Lower bound over every term.
        """
        total = 0
        for term in self.terms:
            if isinstance(term, SimplePathTerm):
                total += sum(
                    0 if relationship.min_hops == 0 else 1 for relationship in term.relationships
                )
            else:
                total += term.quantifier.min_hops * term.pattern.minimum_relationships()
        return total

    def maximum_relationships(self) -> int | None:
        """Return the maximum number of relationships the pattern traverses.

        Returns
        -------
        int | None
            Upper bound, or ``None`` when any repetition is open-ended.
        """
        total = 0
        for term in self.terms:
            if isinstance(term, SimplePathTerm):
                for relationship in term.relationships:
                    if relationship.min_hops is None and relationship.max_hops is None:
                        total += 1
                    elif relationship.max_hops is None:
                        return None
                    else:
                        total += relationship.max_hops
            else:
                if term.quantifier.max_hops is None:
                    return None
                inner = term.pattern.maximum_relationships()
                if inner is None:
                    return None
                total += term.quantifier.max_hops * inner
        return total


type PathTerm = SimplePathTerm | GroupedPathTerm


@dataclasses.dataclass(frozen=True, slots=True)
class ReturnItem:
    """One projected expression.

    Parameters
    ----------
    expression : Expression
        Expression to project.
    alias : str | None, optional
        Explicit alias, by default ``None``.
    text : str, optional
        Source text of the expression, used as the fallback column name.
    """

    expression: Expression
    alias: str | None = None
    text: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class SortItem:
    """One ``ORDER BY`` key.

    Parameters
    ----------
    expression : Expression
        Sort expression or projected alias.
    descending : bool, optional
        Whether the key sorts descending, by default ``False``.
    """

    expression: Expression
    descending: bool = False
    nulls_first: bool | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Match:
    """A ``MATCH`` clause.

    Parameters
    ----------
    patterns : tuple[PathPattern, ...]
        Path patterns evaluated together as one stage.
    where : Expression | None, optional
        Filter predicate, by default ``None``.
    optional : bool, optional
        Whether the clause is ``OPTIONAL MATCH``, by default ``False``.
    mode : PathMode | None, optional
        Explicit clause-wide path mode, by default ``None``.
    match_mode : MatchMode, optional
        Relationship-sharing rule of the clause, by default
        ``MatchMode.REPEATABLE_ELEMENTS``.
    """

    patterns: tuple[PathPattern, ...]
    where: Expression | None = None
    optional: bool = False
    mode: PathMode | None = None
    match_mode: MatchMode = MatchMode.REPEATABLE_ELEMENTS


@dataclasses.dataclass(frozen=True, slots=True)
class Create:
    """A ``CREATE`` clause.

    Parameters
    ----------
    pattern : PathPattern
        Pattern whose new elements are created.
    """

    pattern: PathPattern


@dataclasses.dataclass(frozen=True, slots=True)
class PropertyAssignment:
    """One ``SET variable.key = value`` assignment.

    Parameters
    ----------
    variable : str
        Bound node or relationship variable.
    key : str
        Property key to assign.
    value : Expression
        Expression supplying the new value.
    span : Span | None, optional
        Source position of the assignment, by default ``None``.
    """

    variable: str
    key: str
    value: Expression
    span: Span | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class LabelAssignment:
    """One ``SET variable:Label`` label addition.

    Parameters
    ----------
    variable : str
        Bound node variable.
    labels : tuple[str, ...]
        Labels to add.
    span : Span | None, optional
        Source position of the assignment, by default ``None``.
    """

    variable: str
    labels: tuple[str, ...]
    span: Span | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Set:
    """A ``SET`` clause.

    Parameters
    ----------
    assignments : tuple[PropertyAssignment, ...], optional
        Property assignments, by default none.
    labels : tuple[LabelAssignment, ...], optional
        Label additions, by default none.
    """

    assignments: tuple[PropertyAssignment, ...] = ()
    labels: tuple[LabelAssignment, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class PropertyRemoval:
    """One ``REMOVE variable.key`` removal.

    Parameters
    ----------
    variable : str
        Bound node or relationship variable.
    key : str
        Property key to remove.
    span : Span | None, optional
        Source position of the removal, by default ``None``.
    """

    variable: str
    key: str
    span: Span | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class LabelRemoval:
    """One ``REMOVE variable:Label`` removal.

    Parameters
    ----------
    variable : str
        Bound node variable.
    labels : tuple[str, ...]
        Labels to remove.
    span : Span | None, optional
        Source position of the removal, by default ``None``.
    """

    variable: str
    labels: tuple[str, ...]
    span: Span | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Remove:
    """A ``REMOVE`` clause.

    Parameters
    ----------
    properties : tuple[PropertyRemoval, ...], optional
        Property removals, by default none.
    labels : tuple[LabelRemoval, ...], optional
        Label removals, by default none.
    """

    properties: tuple[PropertyRemoval, ...] = ()
    labels: tuple[LabelRemoval, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class Delete:
    """A ``DELETE`` or ``DETACH DELETE`` clause.

    Parameters
    ----------
    variables : tuple[str, ...]
        Bound node or relationship variables to delete.
    detach : bool, optional
        Whether incident relationships are removed first, by default ``False``.
    """

    variables: tuple[str, ...]
    detach: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class Return:
    """A ``RETURN`` clause.

    Parameters
    ----------
    items : tuple[ReturnItem, ...]
        Projected expressions in output order.
    distinct : bool, optional
        Whether ``RETURN DISTINCT`` was requested, by default ``False``.
    order_by : tuple[SortItem, ...], optional
        Sort keys in significant order, by default none.
    skip : Expression | None, optional
        Skip expression, by default ``None``.
    limit : Expression | None, optional
        Limit expression, by default ``None``.
    star : bool, optional
        Whether the clause projects every variable in scope, by default
        ``False``.
    group_by : tuple[Expression, ...] | None, optional
        Explicit grouping keys, an empty tuple for ``GROUP BY ()``, or ``None``
        when the clause has no explicit grouping, by default ``None``.
    no_bindings : bool, optional
        Whether the pygrafito ``RETURN NO BINDINGS`` extension was requested,
        by default ``False``.
    """

    items: tuple[ReturnItem, ...]
    distinct: bool = False
    order_by: tuple[SortItem, ...] = ()
    skip: Expression | None = None
    limit: Expression | None = None
    star: bool = False
    group_by: tuple[Expression, ...] | None = None
    no_bindings: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class With:
    """A ``WITH`` clause that projects rows into a new scope.

    Parameters
    ----------
    items : tuple[ReturnItem, ...]
        Projected expressions in output order.
    distinct : bool, optional
        Whether duplicate rows are removed, by default ``False``.
    where : Expression | None, optional
        Filter evaluated against the projected scope, by default ``None``.
    order_by : tuple[SortItem, ...], optional
        Sort keys in significant order, by default none.
    skip : Expression | None, optional
        Skip expression, by default ``None``.
    limit : Expression | None, optional
        Limit expression, by default ``None``.
    star : bool, optional
        Whether the clause projects every variable in scope, by default
        ``False``.
    """

    items: tuple[ReturnItem, ...]
    distinct: bool = False
    where: Expression | None = None
    order_by: tuple[SortItem, ...] = ()
    skip: Expression | None = None
    limit: Expression | None = None
    star: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class Filter:
    """A ``FILTER`` stage that keeps rows whose predicate is true.

    Parameters
    ----------
    where : Expression
        Boolean expression evaluated against the current row.
    """

    where: Expression


@dataclasses.dataclass(frozen=True, slots=True)
class Unwind:
    """An ``UNWIND`` clause that expands a list into rows.

    Parameters
    ----------
    expression : Expression
        List-valued expression to expand.
    variable : str
        Variable bound to each expanded element.
    index : str | None, optional
        Variable bound to the element position, by default ``None``.
    ordinality : OrdinalityKind | None, optional
        Whether the position is one-based or zero-based, by default ``None``.
    """

    expression: Expression
    variable: str
    index: str | None = None
    ordinality: OrdinalityKind | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Merge:
    """A ``MERGE`` clause with optional conditional updates.

    Parameters
    ----------
    pattern : PathPattern
        Pattern that is matched as a whole or created.
    on_create : Set | None, optional
        Assignments applied to rows the clause creates, by default ``None``.
    on_match : Set | None, optional
        Assignments applied to rows the clause matches, by default ``None``.
    """

    pattern: PathPattern
    on_create: Set | None = None
    on_match: Set | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class LetAssignment:
    """One ``LET name = expression`` assignment.

    Parameters
    ----------
    name : str
        Variable introduced by the assignment.
    expression : Expression
        Row-wise expression supplying the value.
    """

    name: str
    expression: Expression


@dataclasses.dataclass(frozen=True, slots=True)
class Let:
    """A ``LET`` clause that adds row-wise bindings.

    Parameters
    ----------
    assignments : tuple[LetAssignment, ...]
        Assignments in evaluation order.
    """

    assignments: tuple[LetAssignment, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Next:
    """The ``NEXT`` separator between two linear segments."""


@dataclasses.dataclass(frozen=True, slots=True)
class YieldItem:
    """One column selected by ``NEXT YIELD``.

    Parameters
    ----------
    name : str
        Column name from the preceding result.
    alias : str | None, optional
        Output name, by default the source name.
    """

    name: str
    alias: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Yield:
    """A ``YIELD`` projection attached to ``NEXT``.

    Parameters
    ----------
    items : tuple[YieldItem, ...]
        Selected columns in output order.
    """

    items: tuple[YieldItem, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Finish:
    """A ``FINISH`` clause that ends a statement without a result."""


type Clause = (
    Match
    | With
    | Unwind
    | Filter
    | Create
    | Merge
    | Set
    | Remove
    | Delete
    | Return
    | Let
    | Next
    | Yield
    | Finish
)


@dataclasses.dataclass(frozen=True, slots=True)
class Statement:
    """One linear statement as an ordered clause sequence.

    Parameters
    ----------
    clauses : tuple[Clause, ...]
        Clauses in source order.
    """

    clauses: tuple[Clause, ...]


class SetOperation(Enum):
    """Set operator between two linear query terms."""

    UNION = "UNION"
    UNION_ALL = "UNION ALL"
    INTERSECT = "INTERSECT"
    EXCEPT = "EXCEPT"


@dataclasses.dataclass(frozen=True, slots=True)
class CompoundStatement(Statement):
    """A compound query made of read-only linear statements.

    Parameters
    ----------
    terms : tuple[Statement, ...]
        Linear query terms in source order.
    operators : tuple[SetOperation, ...]
        Set operators between adjacent terms.
    order_by : tuple[SortItem, ...], optional
        Compound-level ordering keys, by default none.
    skip : Expression | None, optional
        Compound-level skip expression, by default ``None``.
    limit : Expression | None, optional
        Compound-level limit expression, by default ``None``.
    """

    terms: tuple[Statement, ...]
    operators: tuple[SetOperation, ...]
    order_by: tuple[SortItem, ...] = ()
    skip: Expression | None = None
    limit: Expression | None = None


type ParsedStatement = Statement


__all__ = [
    "Binary",
    "Case",
    "CaseBranch",
    "Clause",
    "CompoundStatement",
    "Create",
    "Delete",
    "EdgeDirection",
    "Expression",
    "Filter",
    "Finish",
    "FunctionCall",
    "GroupedPathTerm",
    "HopRange",
    "IsNull",
    "LabelAssignment",
    "LabelRemoval",
    "Let",
    "LetAssignment",
    "ListAccess",
    "ListComprehension",
    "ListLiteral",
    "ListSlice",
    "Literal",
    "MapEntry",
    "MapLiteral",
    "Match",
    "MatchMode",
    "Merge",
    "Next",
    "NodePattern",
    "Operators",
    "OrdinalityKind",
    "Parameter",
    "ParsedStatement",
    "PathMode",
    "PathPattern",
    "PathSearch",
    "PathSearchKind",
    "PathTerm",
    "Property",
    "PropertyAssignment",
    "PropertyEntry",
    "PropertyRemoval",
    "RelationshipPattern",
    "Remove",
    "Return",
    "ReturnItem",
    "Set",
    "SetOperation",
    "SimplePathTerm",
    "SortItem",
    "Star",
    "Statement",
    "Subquery",
    "SubqueryKind",
    "Unary",
    "Unwind",
    "Variable",
    "With",
    "Yield",
    "YieldItem",
]
