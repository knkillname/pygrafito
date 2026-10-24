# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Compile fixed-length patterns and filters into indexed SQL."""

import dataclasses
import typing
from collections.abc import Mapping

from pygrafito.engine.query.ast import (
    Binary,
    Expression,
    IsNull,
    ListLiteral,
    Literal,
    Match,
    NodePattern,
    Operators,
    Parameter,
    PathPattern,
    Property,
    PropertyEntry,
    RelationshipPattern,
    Unary,
    Variable,
)
from pygrafito.engine.query.values import PatternValueResolver, QueryValue, Values
from pygrafito.model import (
    Direction,
    Node,
    QuerySemanticError,
    Relationship,
    ValidationError,
)
from pygrafito.storage.codec import PropertyCodec


@dataclasses.dataclass(frozen=True, slots=True)
class NodeColumn:
    """SQL selection for one node position.

    Parameters
    ----------
    column : str
        SQL column alias holding the node id.
    variable : str | None
        Bound variable, or ``None`` for an anonymous node.
    """

    column: str
    variable: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipColumns:
    """SQL selections for one relationship position.

    Parameters
    ----------
    id : str
        SQL column alias holding the relationship id.
    src : str
        SQL column alias holding the start node id.
    dst : str
        SQL column alias holding the end node id.
    rel_type : str
        SQL column alias holding the relationship type.
    props : str
        SQL column alias holding the encoded properties.
    variable : str | None
        Bound variable, or ``None`` for an anonymous relationship.
    """

    id: str
    src: str
    dst: str
    rel_type: str
    props: str
    variable: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class PathSelection:
    """Selection needed to assemble one path variable.

    Parameters
    ----------
    variable : str
        Path variable name.
    nodes : tuple[str, ...]
        Node-id column aliases from the start of the path to its end.
    relationships : tuple[RelationshipColumns, ...]
        Relationship selections in traversal order.
    """

    variable: str
    nodes: tuple[str, ...]
    relationships: tuple[RelationshipColumns, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class CompiledMatch:
    """SQL match query and the selections needed to decode its rows.

    Parameters
    ----------
    sql : str
        Parameterized SQL text.
    arguments : tuple[object, ...]
        Values bound to the SQL placeholders.
    node_columns : tuple[NodeColumn, ...]
        Node selections present in each row.
    relationship_columns : tuple[RelationshipColumns, ...]
        Relationship selections present in each row.
    paths : tuple[PathSelection, ...]
        Path selections present in each row.
    residual : Expression | None
        Filter expression that must be evaluated in Python.
    """

    sql: str
    arguments: tuple[object, ...]
    node_columns: tuple[NodeColumn, ...]
    relationship_columns: tuple[RelationshipColumns, ...]
    paths: tuple[PathSelection, ...]
    residual: Expression | None


class ConstantEvaluator:
    """Evaluate constant expressions used by patterns and pushdown.

    Parameters
    ----------
    parameters : Mapping[str, QueryValue]
        Query parameter values.
    """

    def __init__(self, parameters: Mapping[str, QueryValue]) -> None:
        self._parameters = parameters

    def evaluate(self, expression: Expression) -> QueryValue:
        """Evaluate a constant expression.

        Parameters
        ----------
        expression : Expression
            Expression containing only literals, parameters, list literals,
            and unary signs.

        Returns
        -------
        QueryValue
            Constant value.

        Raises
        ------
        QuerySemanticError
            If the expression is not constant or a parameter is missing.
        """
        if isinstance(expression, Literal):
            return expression.value
        if isinstance(expression, Parameter):
            if expression.name not in self._parameters:
                message = f"missing query parameter ${expression.name}"
                raise QuerySemanticError(message)
            return self._parameters[expression.name]
        if isinstance(expression, ListLiteral):
            return [self.evaluate(item) for item in expression.items]
        if isinstance(expression, Unary) and expression.operator in {
            Operators.NEGATE,
            Operators.POSITIVE,
        }:
            value = self.evaluate(expression.operand)
            if value is None:
                return None
            if not Values.is_number(value):
                message = "constant arithmetic requires numeric operands"
                raise QuerySemanticError(message)
            number = typing.cast(int | float, value)
            result = -number if expression.operator == Operators.NEGATE else number
            if isinstance(result, int) and not (Values.INTEGER_MIN <= result <= Values.INTEGER_MAX):
                message = "integer literal overflows the signed 64-bit range"
                raise QuerySemanticError(message)
            return result
        message = "expected a constant expression"
        raise QuerySemanticError(message)

    @classmethod
    def is_constant(cls, expression: Expression) -> bool:
        """Report whether an expression is a supported constant form.

        Parameters
        ----------
        expression : Expression
            Expression to inspect.

        Returns
        -------
        bool
            ``True`` for literals, parameters, constant list literals, and
            unary signs applied to constants.
        """
        if isinstance(expression, (Literal, Parameter)):
            return True
        if isinstance(expression, ListLiteral):
            return all(cls.is_constant(item) for item in expression.items)
        return (
            isinstance(expression, Unary)
            and expression.operator
            in {
                Operators.NEGATE,
                Operators.POSITIVE,
            }
            and cls.is_constant(expression.operand)
        )

    @classmethod
    def is_literal(cls, expression: Expression) -> bool:
        """Report whether an expression is a literal without parameters.

        Parameters
        ----------
        expression : Expression
            Expression to inspect.

        Returns
        -------
        bool
            ``True`` for literals and unary signs applied to literals.
        """
        if isinstance(expression, Literal):
            return True
        if isinstance(expression, ListLiteral):
            return all(cls.is_literal(item) for item in expression.items)
        return (
            isinstance(expression, Unary)
            and expression.operator
            in {
                Operators.NEGATE,
                Operators.POSITIVE,
            }
            and cls.is_literal(expression.operand)
        )


class PredicateCompiler:
    """Build SQL predicates from property values and operators.

    Parameters
    ----------
    codec : PropertyCodec
        Codec used to validate values and build quoted JSON paths.
    parameters : Mapping[str, QueryValue]
        Query parameter values.
    arguments : list[object]
        Accumulated SQL placeholder values.
    """

    def __init__(
        self,
        codec: PropertyCodec,
        parameters: Mapping[str, QueryValue],
        arguments: list[object],
    ) -> None:
        self._codec = codec
        self._constants = ConstantEvaluator(parameters)
        self._arguments = arguments

    def equality(self, table: str, key: str, value: QueryValue) -> str:
        """Build an equality predicate for one property.

        Parameters
        ----------
        table : str
            Table alias whose ``props`` column is filtered.
        key : str
            Exact property key.
        value : QueryValue
            Expected value.

        Returns
        -------
        str
            SQL predicate.

        Raises
        ------
        QuerySemanticError
            If the value is not a storable property value.
        """
        path = self._literal_path(key)
        if value is None:
            return "0"
        try:
            validated = self._codec.validate_value(value)
        except ValidationError as error:
            message = "query value is not a storable property value"
            raise QuerySemanticError(message) from error
        if isinstance(validated, bool):
            json_type = "true" if validated else "false"
            return self._add(
                f"json_type({table}.props, {path}) = ? AND json_extract({table}.props, {path}) = ?",
                json_type,
                int(validated),
            )
        if isinstance(validated, (int, float)):
            return self._add(
                f"json_type({table}.props, {path}) IN ('integer', 'real') "
                f"AND json_extract({table}.props, {path}) = ?",
                validated,
            )
        if isinstance(validated, str):
            return self._add(
                f"json_type({table}.props, {path}) = 'text' "
                f"AND json_extract({table}.props, {path}) = ?",
                validated,
            )
        return self._add(
            f"json_type({table}.props, {path}) = 'array' "
            f"AND json_extract({table}.props, {path}) = ?",
            self._codec.comparison_value(validated),
        )

    def comparison(
        self,
        table: str,
        key: str,
        operator: str,
        value: QueryValue,
    ) -> str | None:
        """Build a comparison predicate when SQL can express it.

        Parameters
        ----------
        table : str
            Table alias whose ``props`` column is filtered.
        key : str
            Exact property key.
        operator : str
            Comparison operator spelling.
        value : QueryValue
            Right-hand constant value.

        Returns
        -------
        str | None
            SQL predicate, or ``None`` when the comparison has to stay in
            Python.
        """
        if operator in {Operators.EQUAL, Operators.NOT_EQUAL}:
            if value is None:
                return "NULL"
            symbolic = self.equality(table, key, value)
            if operator == Operators.EQUAL:
                return symbolic
            return f"NOT ({symbolic})"
        if value is None:
            return "NULL"
        path = self._literal_path(key)
        if Values.is_number(value):
            return self._add(
                f"json_type({table}.props, {path}) IN ('integer', 'real') "
                f"AND json_extract({table}.props, {path}) {operator} ?",
                value,
            )
        if isinstance(value, str):
            return self._add(
                f"json_type({table}.props, {path}) = 'text' "
                f"AND json_extract({table}.props, {path}) {operator} ?",
                value,
            )
        return None

    def string_predicate(
        self,
        table: str,
        key: str,
        operator: str,
        value: QueryValue,
    ) -> str | None:
        """Build a case-sensitive string predicate.

        Parameters
        ----------
        table : str
            Table alias whose ``props`` column is filtered.
        key : str
            Exact property key.
        operator : str
            String predicate spelling.
        value : QueryValue
            Prefix, suffix, or substring.

        Returns
        -------
        str | None
            SQL predicate, or ``None`` when the value is not a string.
        """
        if value is None:
            return "NULL"
        if not isinstance(value, str):
            return None
        path = self._literal_path(key)
        guard = f"json_type({table}.props, {path}) = 'text'"
        if operator == Operators.STARTS_WITH:
            return self._add(
                f"{guard} AND instr(json_extract({table}.props, {path}), ?) = 1",
                value,
            )
        if operator == Operators.ENDS_WITH:
            if not value:
                return self._add(guard)
            return self._add(
                f"{guard} AND substr(json_extract({table}.props, {path}), -length(?)) = ?",
                value,
                value,
            )
        if operator == Operators.CONTAINS:
            return self._add(
                f"{guard} AND instr(json_extract({table}.props, {path}), ?) > 0",
                value,
            )
        return None

    def is_null(self, table: str, key: str, *, negated: bool) -> str:
        """Build a null-test predicate for one property.

        Parameters
        ----------
        table : str
            Table alias whose ``props`` column is filtered.
        key : str
            Exact property key.
        negated : bool
            Whether to test for a non-null property.

        Returns
        -------
        str
            SQL predicate.
        """
        operator = "IS NOT NULL" if negated else "IS NULL"
        return f"json_type({table}.props, {self._literal_path(key)}) {operator}"

    def _literal_path(self, key: str) -> str:
        """Render a key as an embeddable SQL literal holding its JSON path.

        Parameters
        ----------
        key : str
            Exact property key.

        Returns
        -------
        str
            SQL string literal such as ``'$."a.b"'``.
        """
        return self._codec.sql_json_path(key)

    def _add(self, template: str, *values: object) -> str:
        """Append placeholder values and return the SQL fragment.

        Parameters
        ----------
        template : str
            SQL fragment with one placeholder per value.
        *values : object
            Values bound to the placeholders in order.

        Returns
        -------
        str
            The SQL fragment.
        """
        self._arguments.extend(values)
        return template


class PushdownAnalyzer:
    """Split a ``WHERE`` expression into SQL predicates and a residual.

    Parameters
    ----------
    aliases : Mapping[str, tuple[str, bool]]
        Variable name mapped to its table alias and whether it is a
        relationship.
    predicates : PredicateCompiler
        Builder for SQL property predicates.
    constants : ConstantEvaluator
        Evaluator for literal and parameter operands.
    """

    def __init__(
        self,
        aliases: Mapping[str, tuple[str, bool]],
        predicates: PredicateCompiler,
        constants: ConstantEvaluator,
    ) -> None:
        self._aliases = aliases
        self._predicates = predicates
        self._constants = constants

    def split(self, expression: Expression) -> tuple[str | None, Expression | None]:
        """Split one expression into pushable and residual parts.

        Parameters
        ----------
        expression : Expression
            Filter expression to split.

        Returns
        -------
        tuple[str | None, Expression | None]
            SQL predicate and residual expression; each may be ``None``.
        """
        if isinstance(expression, Binary) and expression.operator == Operators.AND:
            left_sql, left_residual = self.split(expression.left)
            right_sql, right_residual = self.split(expression.right)
            return self._combine_and(left_sql, left_residual, right_sql, right_residual)
        if isinstance(expression, Binary) and expression.operator == Operators.OR:
            left_sql, left_residual = self.split(expression.left)
            right_sql, right_residual = self.split(expression.right)
            if (
                left_sql is not None
                and right_sql is not None
                and left_residual is None
                and right_residual is None
            ):
                return f"({left_sql}) OR ({right_sql})", None
            return None, expression
        if isinstance(expression, Unary) and expression.operator == Operators.NOT:
            operand_sql, operand_residual = self.split(expression.operand)
            if operand_sql is not None and operand_residual is None:
                return f"NOT ({operand_sql})", None
            return None, expression
        predicate = self._leaf(expression)
        return predicate, None if predicate is not None else expression

    @staticmethod
    def _combine_and(
        left_sql: str | None,
        left_residual: Expression | None,
        right_sql: str | None,
        right_residual: Expression | None,
    ) -> tuple[str | None, Expression | None]:
        """Combine two ``AND`` halves.

        Parameters
        ----------
        left_sql : str | None
            SQL predicate for the left half.
        left_residual : Expression | None
            Residual expression for the left half.
        right_sql : str | None
            SQL predicate for the right half.
        right_residual : Expression | None
            Residual expression for the right half.

        Returns
        -------
        tuple[str | None, Expression | None]
            Combined SQL predicate and residual.
        """
        sql_parts = [part for part in (left_sql, right_sql) if part is not None]
        sql = " AND ".join(f"({part})" for part in sql_parts) if sql_parts else None
        if left_residual is not None and right_residual is not None:
            residual: Expression | None = Binary(
                left=left_residual,
                operator=Operators.AND,
                right=right_residual,
            )
        else:
            residual = left_residual if left_residual is not None else right_residual
        return sql, residual

    def _leaf(self, expression: Expression) -> str | None:
        """Compile one leaf predicate when possible.

        Parameters
        ----------
        expression : Expression
            Candidate leaf expression.

        Returns
        -------
        str | None
            SQL predicate, or ``None`` when the leaf remains residual.
        """
        if isinstance(expression, IsNull):
            target = self._property_target(expression.operand)
            if target is None:
                return None
            return self._predicates.is_null(target[0], target[1], negated=expression.negated)
        if isinstance(expression, Binary):
            if expression.operator == Operators.IN:
                return self._membership(expression)
            if expression.operator in {
                Operators.STARTS_WITH,
                Operators.ENDS_WITH,
                Operators.CONTAINS,
            }:
                target = self._property_target(expression.left)
                if target is None or not ConstantEvaluator.is_constant(expression.right):
                    return None
                value = self._constants.evaluate(expression.right)
                return self._predicates.string_predicate(
                    target[0],
                    target[1],
                    expression.operator,
                    value,
                )
            if expression.operator in {
                Operators.EQUAL,
                Operators.NOT_EQUAL,
                Operators.LESS,
                Operators.LESS_EQUAL,
                Operators.GREATER,
                Operators.GREATER_EQUAL,
            }:
                return self._comparison(expression)
        return None

    def _comparison(self, expression: Binary) -> str | None:
        """Compile one comparison whose property side is known.

        Parameters
        ----------
        expression : Binary
            Comparison expression.

        Returns
        -------
        str | None
            SQL predicate, or ``None`` when it remains residual.
        """
        left = self._property_target(expression.left)
        if left is not None and ConstantEvaluator.is_constant(expression.right):
            value = self._constants.evaluate(expression.right)
            return self._predicates.comparison(
                left[0],
                left[1],
                expression.operator,
                value,
            )
        right = self._property_target(expression.right)
        if right is not None and ConstantEvaluator.is_constant(expression.left):
            value = self._constants.evaluate(expression.left)
            return self._predicates.comparison(
                right[0],
                right[1],
                self._flip(expression.operator),
                value,
            )
        return None

    def _membership(self, expression: Binary) -> str | None:
        """Compile an ``IN`` predicate with a literal list.

        Parameters
        ----------
        expression : Binary
            ``IN`` expression.

        Returns
        -------
        str | None
            SQL predicate, or ``None`` when the list is not a literal list.
        """
        target = self._property_target(expression.left)
        if target is None or not isinstance(expression.right, ListLiteral):
            return None
        parts: list[str] = []
        for item in expression.right.items:
            if not ConstantEvaluator.is_literal(item):
                return None
            parts.append(
                self._predicates.comparison(
                    target[0],
                    target[1],
                    Operators.EQUAL,
                    self._constants.evaluate(item),
                )
                or "NULL"
            )
        if not parts:
            return "0"
        return " OR ".join(f"({part})" for part in parts)

    def _property_target(self, expression: Expression) -> tuple[str, str] | None:
        """Resolve a property access on a bound variable.

        Parameters
        ----------
        expression : Expression
            Candidate property access.

        Returns
        -------
        tuple[str, str] | None
            Table alias and property key when the target is a bound variable.
        """
        if not isinstance(expression, Property):
            return None
        if not isinstance(expression.target, Variable):
            return None
        alias = self._aliases.get(expression.target.name)
        if alias is None:
            return None
        return alias[0], expression.key

    @staticmethod
    def _flip(operator: str) -> str:
        """Reverse a comparison operator.

        Parameters
        ----------
        operator : str
            Original operator.

        Returns
        -------
        str
            Operator with operands reversed.
        """
        return {
            Operators.LESS: Operators.GREATER,
            Operators.LESS_EQUAL: Operators.GREATER_EQUAL,
            Operators.GREATER: Operators.LESS,
            Operators.GREATER_EQUAL: Operators.LESS_EQUAL,
        }.get(operator, operator)


class Compiler:
    """Compile one match clause and its pushed-down filter.

    Parameters
    ----------
    match : Match
        Parsed match clause to compile.
    codec : PropertyCodec, optional
        Codec used to build quoted JSON paths and encode values.
    """

    def __init__(
        self,
        match: Match,
        codec: PropertyCodec | None = None,
    ) -> None:
        self._match = match
        self._codec = PropertyCodec() if codec is None else codec
        self._columns: list[str] = []
        self._arguments: list[object] = []
        self._joins: list[str] = []
        self._predicates: list[str] = []
        self._node_columns: list[NodeColumn] = []
        self._relationship_columns: list[RelationshipColumns] = []
        self._node_aliases: dict[str, str] = {}
        self._relationship_aliases: dict[str, str] = {}
        self._node_column_by_alias: dict[str, str] = {}
        self._relationship_by_alias: dict[str, RelationshipColumns] = {}
        self._path_node_aliases: list[str] = []
        self._path_relationships: list[RelationshipColumns] = []
        self._node_counter = 0
        self._relationship_counter = 0
        self._label_counter = 0
        self._parameters: Mapping[str, QueryValue] = {}
        self._bound: Mapping[str, QueryValue] = {}
        self._resolver: PatternValueResolver | None = None
        self._predicates_builder: PredicateCompiler | None = None

    def compile(
        self,
        parameters: Mapping[str, QueryValue],
        bound: Mapping[str, QueryValue] | None = None,
        resolver: PatternValueResolver | None = None,
    ) -> CompiledMatch:
        """Compile the match clause against one parameter mapping.

        Parameters
        ----------
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        bound : Mapping[str, QueryValue] | None, optional
            Values already bound by an earlier stage, by default none.
        resolver : PatternValueResolver | None, optional
            Evaluator for pattern property expressions, by default none for a
            constant-only compilation.

        Returns
        -------
        CompiledMatch
            SQL text, arguments, and row selections.
        """
        self._reset(parameters)
        self._bound = {} if bound is None else bound
        self._resolver = resolver
        paths: list[PathSelection] = []
        for pattern in self._match.patterns:
            node_start = len(self._path_node_aliases)
            relationship_start = len(self._path_relationships)
            self._compile_pattern(pattern)
            paths.extend(self._build_paths(pattern, node_start, relationship_start))
        residual = self._compile_where()
        sql = self._build_sql()
        return CompiledMatch(
            sql=sql,
            arguments=tuple(self._arguments),
            node_columns=tuple(self._node_columns),
            relationship_columns=tuple(self._relationship_columns),
            paths=tuple(paths),
            residual=residual,
        )

    def _reset(self, parameters: Mapping[str, QueryValue]) -> None:
        """Reset compilation state for one execution.

        Parameters
        ----------
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        """
        self._columns = []
        self._arguments = []
        self._joins = []
        self._predicates = []
        self._node_columns = []
        self._relationship_columns = []
        self._node_aliases = {}
        self._relationship_aliases = {}
        self._node_column_by_alias = {}
        self._relationship_by_alias = {}
        self._path_node_aliases = []
        self._path_relationships = []
        self._node_counter = 0
        self._relationship_counter = 0
        self._label_counter = 0
        self._parameters = parameters
        self._bound = {}
        self._predicates_builder = PredicateCompiler(
            self._codec,
            parameters,
            self._arguments,
        )

    def _compile_pattern(self, pattern: PathPattern) -> None:
        """Compile every node and relationship position of a path pattern.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to compile.
        """
        current = self._bind_node(pattern.nodes[0], None)
        self._path_node_aliases.append(current)
        for index, relationship in enumerate(pattern.relationships):
            next_id, relationship_columns = self._bind_relationship(relationship, current)
            self._path_relationships.append(relationship_columns)
            current = self._bind_node(pattern.nodes[index + 1], next_id)
            self._path_node_aliases.append(current)

    def _bind_node(self, pattern: NodePattern, expected_id: str | None) -> str:
        """Bind one node pattern to a table alias and its predicates.

        Parameters
        ----------
        pattern : NodePattern
            Node pattern to bind.
        expected_id : str | None
            SQL expression the node id must equal, or ``None`` for the first
            node.

        Returns
        -------
        str
            Table alias for the node.
        """
        alias = self._node_aliases.get(pattern.variable) if pattern.variable is not None else None
        if alias is None:
            alias = f"n{self._node_counter}"
            self._node_counter += 1
            if expected_id is None:
                if self._joins:
                    self._joins.append(f"CROSS JOIN nodes AS {alias}")
                else:
                    self._joins.append(f"nodes AS {alias}")
            else:
                self._joins.append(f"JOIN nodes AS {alias} ON {alias}.id = {expected_id}")
            column = self._select(f"{alias}.id")
            self._node_columns.append(NodeColumn(column=column, variable=pattern.variable))
            self._node_column_by_alias[alias] = column
            if pattern.variable is not None:
                self._node_aliases[pattern.variable] = alias
                self._add_bound_entity(alias, pattern.variable)
        elif expected_id is not None:
            self._predicates.append(f"{alias}.id = {expected_id}")
        self._add_node_predicates(alias, pattern)
        return alias

    def _add_node_predicates(self, alias: str, pattern: NodePattern) -> None:
        """Add label and property predicates for a node alias.

        Parameters
        ----------
        alias : str
            Node table alias.
        pattern : NodePattern
            Node pattern carrying the constraints.
        """
        for label in pattern.labels:
            label_alias = f"label_{self._label_counter}"
            self._label_counter += 1
            self._predicates.append(
                f"EXISTS (SELECT 1 FROM node_labels AS {label_alias} "
                f"WHERE {label_alias}.node_id = {alias}.id AND {label_alias}.label = ?)"
            )
            self._arguments.append(label)
        self._add_property_predicates(alias, pattern.properties)

    def _bind_relationship(
        self,
        pattern: RelationshipPattern,
        current_id: str,
    ) -> tuple[str, RelationshipColumns]:
        """Bind one relationship pattern and return its next-node expression.

        Parameters
        ----------
        pattern : RelationshipPattern
            Relationship pattern to bind.
        current_id : str
            Table alias of the node before the relationship.

        Returns
        -------
        tuple[str, RelationshipColumns]
            SQL expression for the next node id and the row selection.
        """
        builder = self._predicates_builder
        if builder is None:
            message = "compiler was not initialized"
            raise QuerySemanticError(message)
        alias = (
            self._relationship_aliases.get(pattern.variable)
            if pattern.variable is not None
            else None
        )
        columns = self._relationship_by_alias.get(alias) if alias is not None else None
        if alias is None or columns is None:
            alias = f"r{self._relationship_counter}"
            self._relationship_counter += 1
            condition = self._direction_condition(pattern.direction, alias, current_id)
            self._joins.append(f"JOIN relationships AS {alias} ON {condition}")
            columns = RelationshipColumns(
                id=self._select(f"{alias}.id"),
                src=self._select(f"{alias}.src"),
                dst=self._select(f"{alias}.dst"),
                rel_type=self._select(f"{alias}.rel_type"),
                props=self._select(f"{alias}.props"),
                variable=pattern.variable,
            )
            self._relationship_columns.append(columns)
            self._relationship_by_alias[alias] = columns
            if pattern.variable is not None:
                self._relationship_aliases[pattern.variable] = alias
                self._add_bound_entity(alias, pattern.variable)
        else:
            condition = self._direction_condition(pattern.direction, alias, current_id)
            self._predicates.append(condition)
        if pattern.types:
            placeholders = ", ".join("?" for _ in pattern.types)
            self._predicates.append(f"{alias}.rel_type IN ({placeholders})")
            self._arguments.extend(pattern.types)
        self._add_property_predicates(alias, pattern.properties)
        return self._next_id(pattern.direction, alias, current_id), columns

    @staticmethod
    def _direction_condition(direction: Direction, alias: str, current_id: str) -> str:
        """Build the join condition for one relationship direction.

        Parameters
        ----------
        direction : Direction
            Direction relative to the previous node.
        alias : str
            Relationship table alias.
        current_id : str
            Table alias of the previous node.

        Returns
        -------
        str
            SQL condition.
        """
        if direction is Direction.OUTGOING:
            return f"{alias}.src = {current_id}.id"
        if direction is Direction.INCOMING:
            return f"{alias}.dst = {current_id}.id"
        return f"({alias}.src = {current_id}.id OR {alias}.dst = {current_id}.id)"

    @staticmethod
    def _next_id(direction: Direction, alias: str, current_id: str) -> str:
        """Build the SQL expression for the next node id.

        Parameters
        ----------
        direction : Direction
            Direction relative to the previous node.
        alias : str
            Relationship table alias.
        current_id : str
            Table alias of the previous node.

        Returns
        -------
        str
            SQL expression identifying the next node.
        """
        if direction is Direction.OUTGOING:
            return f"{alias}.dst"
        if direction is Direction.INCOMING:
            return f"{alias}.src"
        return f"CASE WHEN {alias}.src = {current_id}.id THEN {alias}.dst ELSE {alias}.src END"

    def _add_property_predicates(
        self,
        alias: str,
        entries: tuple[PropertyEntry, ...],
    ) -> None:
        """Add equality predicates for a pattern property map.

        Parameters
        ----------
        alias : str
            Table alias whose ``props`` column is filtered.
        entries : tuple[PropertyEntry, ...]
            Property entries to compile.
        """
        builder = self._predicates_builder
        if builder is None:
            message = "compiler was not initialized"
            raise QuerySemanticError(message)
        constants = ConstantEvaluator(self._parameters)
        for entry in entries:
            if self._resolver is None:
                value = constants.evaluate(entry.value)
            else:
                value = self._resolver.resolve(entry.value, self._bound)
            self._predicates.append(builder.equality(alias, entry.key, value))

    def _compile_where(self) -> Expression | None:
        """Push down the ``WHERE`` clause and return its residual.

        Returns
        -------
        Expression | None
            Residual filter expression, if any.
        """
        if self._match.where is None:
            return None
        builder = self._predicates_builder
        if builder is None:
            message = "compiler was not initialized"
            raise QuerySemanticError(message)
        aliases: dict[str, tuple[str, bool]] = {}
        for variable, alias in self._node_aliases.items():
            aliases[variable] = (alias, False)
        for variable, alias in self._relationship_aliases.items():
            aliases[variable] = (alias, True)
        analyzer = PushdownAnalyzer(
            aliases,
            builder,
            ConstantEvaluator(self._parameters),
        )
        sql, residual = analyzer.split(self._match.where)
        if sql is not None:
            self._predicates.append(sql)
        return residual

    def _add_bound_entity(self, alias: str, variable: str) -> None:
        """Constrain one alias to an element bound by an earlier stage.

        Parameters
        ----------
        alias : str
            Table alias for the element.
        variable : str
            Variable already bound by an earlier stage.
        """
        if variable not in self._bound:
            return
        self._predicates.append(f"{alias}.id = ?")
        self._arguments.append(self._bound_id(variable))

    def _bound_id(self, variable: str) -> int:
        """Return the element id of a value bound by an earlier stage.

        Parameters
        ----------
        variable : str
            Variable already bound by an earlier stage.

        Returns
        -------
        int
            Node or relationship id.

        Raises
        ------
        QuerySemanticError
            If the bound value is not a node or relationship.
        """
        value = self._bound[variable]
        if isinstance(value, (Node, Relationship)):
            return value.id
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        message = f"variable {variable!r} cannot be used as a pattern element"
        raise QuerySemanticError(message)

    def _build_paths(
        self,
        pattern: PathPattern,
        node_start: int,
        relationship_start: int,
    ) -> tuple[PathSelection, ...]:
        """Build path-variable selections from compiled positions.

        Parameters
        ----------
        pattern : PathPattern
            Compiled path pattern.
        node_start : int
            Index of the pattern's first node selection.
        relationship_start : int
            Index of the pattern's first relationship selection.

        Returns
        -------
        tuple[PathSelection, ...]
            One selection when the path has a variable, otherwise empty.
        """
        if pattern.variable is None:
            return ()
        nodes = tuple(
            self._node_column_by_alias[alias] for alias in self._path_node_aliases[node_start:]
        )
        return (
            PathSelection(
                variable=pattern.variable,
                nodes=nodes,
                relationships=tuple(self._path_relationships[relationship_start:]),
            ),
        )

    def _select(self, expression: str) -> str:
        """Add one SELECT expression and return its column alias.

        Parameters
        ----------
        expression : str
            SQL expression to select.

        Returns
        -------
        str
            Generated column alias.
        """
        alias = f"c{len(self._columns)}"
        self._columns.append(f"{expression} AS {alias}")
        return alias

    def _build_sql(self) -> str:
        """Assemble the final SQL statement.

        Returns
        -------
        str
            Complete parameterized SQL text.
        """
        sql = f"SELECT {', '.join(self._columns)} FROM {self._joins[0]}"
        for join in self._joins[1:]:
            sql += f" {join}"
        if self._predicates:
            joined = " AND ".join(f"({predicate})" for predicate in self._predicates)
            sql += f" WHERE {joined}"
        return sql
