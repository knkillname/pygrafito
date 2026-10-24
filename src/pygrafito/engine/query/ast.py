# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Frozen abstract syntax tree nodes for the query language."""

import dataclasses

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
    """

    variable: str | None = None
    labels: tuple[str, ...] = ()
    properties: tuple[PropertyEntry, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipPattern:
    """One relationship position inside a path pattern.

    Parameters
    ----------
    variable : str | None, optional
        Bound variable, or ``None`` for an anonymous relationship.
    types : tuple[str, ...], optional
        Accepted relationship types, by default any type.
    direction : Direction, optional
        Traversal direction relative to the previous node, by default
        outgoing.
    properties : tuple[PropertyEntry, ...], optional
        Property map every match must satisfy, by default none.
    min_hops : int | None, optional
        Minimum relationship count for a quantified pattern, by default
        ``None`` for an ordinary one-hop relationship.
    max_hops : int | None, optional
        Maximum relationship count for a quantified pattern, by default
        ``None`` for an ordinary one-hop relationship.
    """

    variable: str | None = None
    types: tuple[str, ...] = ()
    direction: Direction = Direction.OUTGOING
    properties: tuple[PropertyEntry, ...] = ()
    min_hops: int | None = None
    max_hops: int | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class PathPattern:
    """One linear path pattern.

    Parameters
    ----------
    variable : str | None, optional
        Path variable, or ``None`` when the path is not bound.
    nodes : tuple[NodePattern, ...]
        Nodes from the start of the path to its end.
    relationships : tuple[RelationshipPattern, ...]
        Relationships in traversal order.
    """

    nodes: tuple[NodePattern, ...]
    relationships: tuple[RelationshipPattern, ...] = ()
    variable: str | None = None


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
    """

    patterns: tuple[PathPattern, ...]
    where: Expression | None = None
    optional: bool = False


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
    """

    items: tuple[ReturnItem, ...]
    distinct: bool = False
    order_by: tuple[SortItem, ...] = ()
    skip: Expression | None = None
    limit: Expression | None = None


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
    """

    items: tuple[ReturnItem, ...]
    distinct: bool = False
    where: Expression | None = None
    order_by: tuple[SortItem, ...] = ()
    skip: Expression | None = None
    limit: Expression | None = None


type Clause = Match | With | Create | Set | Remove | Delete | Return


@dataclasses.dataclass(frozen=True, slots=True)
class Statement:
    """One complete statement as an ordered clause sequence.

    Parameters
    ----------
    clauses : tuple[Clause, ...]
        Clauses in source order.
    """

    clauses: tuple[Clause, ...]


__all__ = [
    "Binary",
    "Clause",
    "Create",
    "Delete",
    "Expression",
    "FunctionCall",
    "IsNull",
    "LabelAssignment",
    "LabelRemoval",
    "ListLiteral",
    "Literal",
    "Match",
    "NodePattern",
    "Operators",
    "Parameter",
    "PathPattern",
    "Property",
    "PropertyAssignment",
    "PropertyEntry",
    "PropertyRemoval",
    "RelationshipPattern",
    "Remove",
    "Return",
    "ReturnItem",
    "Set",
    "SortItem",
    "Star",
    "Statement",
    "Unary",
    "Variable",
    "With",
]
