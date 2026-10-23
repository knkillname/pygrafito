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
    """

    variable: str | None = None
    types: tuple[str, ...] = ()
    direction: Direction = Direction.OUTGOING
    properties: tuple[PropertyEntry, ...] = ()


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
class Statement:
    """One complete read-only query statement.

    Parameters
    ----------
    pattern : PathPattern
        Pattern matched by the query.
    return_items : tuple[ReturnItem, ...]
        Projected expressions in output order.
    where : Expression | None, optional
        Filter predicate, by default ``None``.
    distinct : bool, optional
        Whether ``RETURN DISTINCT`` was requested, by default ``False``.
    order_by : tuple[SortItem, ...], optional
        Sort keys in significant order, by default none.
    skip : Expression | None, optional
        Skip expression, by default ``None``.
    limit : Expression | None, optional
        Limit expression, by default ``None``.
    """

    pattern: PathPattern
    return_items: tuple[ReturnItem, ...]
    where: Expression | None = None
    distinct: bool = False
    order_by: tuple[SortItem, ...] = ()
    skip: Expression | None = None
    limit: Expression | None = None


__all__ = [
    "Binary",
    "Expression",
    "FunctionCall",
    "IsNull",
    "ListLiteral",
    "Literal",
    "NodePattern",
    "Operators",
    "Parameter",
    "PathPattern",
    "Property",
    "PropertyEntry",
    "RelationshipPattern",
    "ReturnItem",
    "SortItem",
    "Star",
    "Statement",
    "Unary",
    "Variable",
]
