# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Static analysis for parsed query statements."""

import dataclasses
from collections.abc import Iterable, Mapping
from enum import Enum
from types import MappingProxyType

from pygrafito.engine.query.ast import (
    Binary,
    Expression,
    FunctionCall,
    IsNull,
    ListLiteral,
    Literal,
    Operators,
    Parameter,
    PathPattern,
    Property,
    PropertyEntry,
    ReturnItem,
    SortItem,
    Star,
    Statement,
    Unary,
    Variable,
)
from pygrafito.engine.query.values import (
    ArgumentKind,
    FunctionCatalog,
    FunctionSpec,
)
from pygrafito.model import QuerySemanticError


class VariableKind(Enum):
    """Kind of value bound to one pattern variable."""

    NODE = "node"
    RELATIONSHIP = "relationship"
    PATH = "path"


@dataclasses.dataclass(frozen=True, slots=True)
class ReturnColumn:
    """One analysed projection column.

    Parameters
    ----------
    expression : Expression
        Projected expression.
    name : str
        Final column name from the alias or expression text.
    text : str
        Source text used when no alias was supplied.
    aggregate : bool
        Whether the expression contains an aggregate call.
    """

    expression: Expression
    name: str
    text: str
    aggregate: bool


@dataclasses.dataclass(frozen=True, slots=True)
class SortSpec:
    """One resolved ordering key.

    Parameters
    ----------
    descending : bool
        Whether the key sorts descending.
    column : int | None, optional
        Projected column index when the key resolves to a projection.
    expression : Expression | None, optional
        Expression evaluated against the match binding.
    """

    descending: bool
    column: int | None = None
    expression: Expression | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Analysis:
    """Result of lexing, parsing, and static analysis.

    Parameters
    ----------
    statement : Statement
        Parsed statement.
    columns : tuple[str, ...]
        Final result column names in projection order.
    items : tuple[ReturnColumn, ...]
        Analysed projection columns.
    variable_kinds : Mapping[str, VariableKind]
        Kind of every variable bound by the pattern.
    parameters : frozenset[str]
        Parameter names referenced by the statement.
    has_aggregates : bool
        Whether any projected expression contains an aggregate.
    grouping : tuple[Expression, ...]
        Implicit grouping-key expressions.
    sorts : tuple[SortSpec, ...]
        Resolved ordering keys in significance order.
    """

    statement: Statement
    columns: tuple[str, ...]
    items: tuple[ReturnColumn, ...]
    variable_kinds: Mapping[str, VariableKind]
    parameters: frozenset[str]
    has_aggregates: bool
    grouping: tuple[Expression, ...]
    sorts: tuple[SortSpec, ...]

    def require_parameters(self, parameters: Mapping[str, object]) -> None:
        """Reject a parameter mapping that omits a referenced parameter.

        Parameters
        ----------
        parameters : Mapping[str, object]
            Supplied parameter values.

        Raises
        ------
        QuerySemanticError
            If a referenced parameter is missing.
        """
        missing = sorted(self.parameters - set(parameters))
        if missing:
            message = f"missing query parameter ${missing[0]}"
            raise QuerySemanticError(message)


class SemanticAnalyzer:
    """Validate a statement and derive its output contract.

    Parameters
    ----------
    statement : Statement
        Parsed statement to analyse.
    """

    AGGREGATE_NAMES: frozenset[str] = FunctionCatalog.AGGREGATES

    def __init__(self, statement: Statement) -> None:
        self._statement = statement
        self._kinds: dict[str, VariableKind] = {}
        self._parameters: set[str] = set()

    @classmethod
    def analyze(cls, statement: Statement) -> Analysis:
        """Analyse one parsed statement.

        Parameters
        ----------
        statement : Statement
            Parsed statement.

        Returns
        -------
        Analysis
            Output contract and resolved ordering keys.
        """
        return cls(statement).run()

    def run(self) -> Analysis:
        """Run every static check and build the analysis.

        Returns
        -------
        Analysis
            Output contract and resolved ordering keys.
        """
        self._bind_pattern(self._statement.pattern)
        if self._statement.where is not None:
            self._validate_expression(self._statement.where, aggregates_allowed=False)
        items = tuple(self._column(item) for item in self._statement.return_items)
        self._require_unique_columns(items)
        has_aggregates = any(item.aggregate for item in items)
        grouping = tuple(item.expression for item in items if not item.aggregate)
        if has_aggregates:
            self._validate_grouping(items, grouping)
        self._validate_pagination(self._statement.skip, "SKIP")
        self._validate_pagination(self._statement.limit, "LIMIT")
        sorts = self._resolve_sorts(
            self._statement.order_by,
            items,
            grouping,
            has_aggregates,
        )
        return Analysis(
            statement=self._statement,
            columns=tuple(item.name for item in items),
            items=items,
            variable_kinds=MappingProxyType(dict(self._kinds)),
            parameters=frozenset(self._parameters),
            has_aggregates=has_aggregates,
            grouping=grouping,
            sorts=sorts,
        )

    def _bind_pattern(self, pattern: PathPattern) -> None:
        """Register every pattern variable and validate property maps.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to bind.
        """
        if pattern.variable is not None:
            self._register(pattern.variable, VariableKind.PATH)
        for node in pattern.nodes:
            if node.variable is not None:
                self._register(node.variable, VariableKind.NODE)
            self._validate_property_map(node.properties)
        for relationship in pattern.relationships:
            if relationship.variable is not None:
                self._register(relationship.variable, VariableKind.RELATIONSHIP)
            self._validate_property_map(relationship.properties)

    def _register(self, name: str, kind: VariableKind) -> None:
        """Register one variable, rejecting kind conflicts.

        Parameters
        ----------
        name : str
            Variable name.
        kind : VariableKind
            Kind required at this position.

        Raises
        ------
        QuerySemanticError
            If the variable was already bound with another kind.
        """
        existing = self._kinds.get(name)
        if existing is None:
            self._kinds[name] = kind
            return
        if existing is not kind:
            message = (
                f"variable {name!r} is already bound as a "
                f"{existing.value} and cannot be a {kind.value}"
            )
            raise QuerySemanticError(message)

    def _validate_property_map(self, entries: Iterable[PropertyEntry]) -> None:
        """Require pattern property values to be constant expressions.

        Parameters
        ----------
        entries : Iterable[PropertyEntry]
            Property-map entries to validate.
        """
        for entry in entries:
            self._require_constant(entry.value)
            self._collect_parameters(entry.value)

    def _require_constant(self, expression: Expression) -> None:
        """Require a constant expression.

        Parameters
        ----------
        expression : Expression
            Expression to validate.

        Raises
        ------
        QuerySemanticError
            If the expression references a variable or is not a supported
            constant form.
        """
        if isinstance(expression, (Literal, Parameter)):
            return
        if isinstance(expression, ListLiteral):
            for item in expression.items:
                self._require_constant(item)
            return
        message = "pattern property values must be literals or parameters"
        raise QuerySemanticError(message)

    def _collect_parameters(self, expression: Expression) -> None:
        """Record every parameter reference in an expression.

        Parameters
        ----------
        expression : Expression
            Expression to inspect.
        """
        if isinstance(expression, Parameter):
            self._parameters.add(expression.name)
            return
        for child in self._children(expression):
            self._collect_parameters(child)

    def _column(self, item: ReturnItem) -> ReturnColumn:
        """Validate one projection and derive its column name.

        Parameters
        ----------
        item : ReturnItem
            Projection to validate.

        Returns
        -------
        ReturnColumn
            Analysed projection column.
        """
        self._validate_expression(item.expression, aggregates_allowed=True)
        text = item.text or self._expression_text(item.expression)
        name = item.alias or text
        return ReturnColumn(
            expression=item.expression,
            name=name,
            text=text,
            aggregate=self._contains_aggregate(item.expression),
        )

    @staticmethod
    def _require_unique_columns(items: Iterable[ReturnColumn]) -> None:
        """Reject duplicate projected column names.

        Parameters
        ----------
        items : Iterable[ReturnColumn]
            Analysed projection columns.

        Raises
        ------
        QuerySemanticError
            If two columns share a name.
        """
        seen: set[str] = set()
        for item in items:
            if item.name in seen:
                message = f"duplicate result column {item.name!r}"
                raise QuerySemanticError(message)
            seen.add(item.name)

    def _validate_grouping(
        self,
        items: Iterable[ReturnColumn],
        grouping: Iterable[Expression],
    ) -> None:
        """Require aggregate projections to group every non-aggregate leaf.

        Parameters
        ----------
        items : Iterable[ReturnColumn]
            Analysed projection columns.
        grouping : Iterable[Expression]
            Implicit grouping-key expressions.
        """
        grouping_keys = {self._expression_key(expression) for expression in grouping}
        for item in items:
            if item.aggregate:
                self._validate_grouped(item.expression, grouping_keys)

    def _validate_grouped(
        self,
        expression: Expression,
        grouping_keys: set[tuple[object, ...]],
    ) -> None:
        """Validate one expression inside an aggregate projection.

        Parameters
        ----------
        expression : Expression
            Expression to validate.
        grouping_keys : set[tuple[object, ...]]
            Canonical grouping keys.

        Raises
        ------
        QuerySemanticError
            If a non-grouped expression is mixed with an aggregate.
        """
        if self._expression_key(expression) in grouping_keys:
            return
        if isinstance(expression, (Literal, Parameter)):
            return
        if isinstance(expression, FunctionCall) and FunctionCatalog.is_aggregate(expression.name):
            return
        if isinstance(expression, ListLiteral):
            for item in expression.items:
                if not isinstance(item, (Literal, Parameter)):
                    self._validate_grouped(item, grouping_keys)
            return
        if isinstance(expression, (Binary, Unary, IsNull)):
            for child in self._children(expression):
                if not isinstance(child, (Literal, Parameter)):
                    self._validate_grouped(child, grouping_keys)
            return
        if isinstance(expression, FunctionCall):
            for argument in expression.arguments:
                if not isinstance(argument, (Literal, Parameter, Star)):
                    self._validate_grouped(argument, grouping_keys)
            return
        message = "a non-aggregate expression in an aggregate projection must be a grouping key"
        raise QuerySemanticError(message)

    def _resolve_sorts(
        self,
        sort_items: Iterable[SortItem],
        items: tuple[ReturnColumn, ...],
        grouping: tuple[Expression, ...],
        has_aggregates: bool,
    ) -> tuple[SortSpec, ...]:
        """Resolve ordering aliases and validate sort expressions.

        Parameters
        ----------
        sort_items : Iterable[SortItem]
            Parsed ordering keys.
        items : tuple[ReturnColumn, ...]
            Analysed projection columns.
        grouping : tuple[Expression, ...]
            Implicit grouping-key expressions.
        has_aggregates : bool
            Whether the query contains aggregates.

        Returns
        -------
        tuple[SortSpec, ...]
            Resolved ordering keys.
        """
        aliases = {item.name: index for index, item in enumerate(items)}
        expression_indexes = {
            self._expression_key(item.expression): index for index, item in enumerate(items)
        }
        grouping_keys = {self._expression_key(expression) for expression in grouping}
        specs: list[SortSpec] = []
        for sort in sort_items:
            if isinstance(sort.expression, Variable) and sort.expression.name in aliases:
                specs.append(
                    SortSpec(
                        descending=sort.descending,
                        column=aliases[sort.expression.name],
                    )
                )
                continue
            key = self._expression_key(sort.expression)
            if key in expression_indexes:
                specs.append(SortSpec(descending=sort.descending, column=expression_indexes[key]))
                continue
            self._validate_expression(sort.expression, aggregates_allowed=False)
            if has_aggregates:
                self._validate_grouped(sort.expression, grouping_keys)
            specs.append(SortSpec(descending=sort.descending, expression=sort.expression))
        return tuple(specs)

    def _validate_pagination(self, expression: Expression | None, clause: str) -> None:
        """Validate a ``SKIP`` or ``LIMIT`` expression.

        Parameters
        ----------
        expression : Expression | None
            Pagination expression.
        clause : str
            Clause name used in error messages.

        Raises
        ------
        QuerySemanticError
            If the expression is neither a non-negative integer literal nor a
            parameter.
        """
        if expression is None:
            return
        if isinstance(expression, Literal):
            value = expression.value
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return
            message = f"{clause} must be a non-negative integer or a parameter"
            raise QuerySemanticError(message)
        if isinstance(expression, Parameter):
            self._parameters.add(expression.name)
            return
        message = f"{clause} must be a non-negative integer or a parameter"
        raise QuerySemanticError(message)

    def _validate_expression(
        self,
        expression: Expression,
        *,
        aggregates_allowed: bool,
        inside_aggregate: bool = False,
    ) -> None:
        """Validate one expression recursively.

        Parameters
        ----------
        expression : Expression
            Expression to validate.
        aggregates_allowed : bool
            Whether aggregates may appear at this position.
        inside_aggregate : bool, optional
            Whether the expression is an aggregate argument, by default
            ``False``.
        """
        if isinstance(expression, Literal):
            return
        if isinstance(expression, ListLiteral):
            for item in expression.items:
                self._validate_expression(
                    item,
                    aggregates_allowed=aggregates_allowed,
                    inside_aggregate=inside_aggregate,
                )
            return
        if isinstance(expression, Variable):
            self._validate_variable(expression)
            return
        if isinstance(expression, Parameter):
            self._parameters.add(expression.name)
            return
        if isinstance(expression, Property):
            if (
                isinstance(expression.target, Variable)
                and self._kinds.get(expression.target.name) is VariableKind.PATH
            ):
                message = "path variables do not have properties"
                raise QuerySemanticError(message)
            self._validate_expression(
                expression.target,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            return
        if isinstance(expression, FunctionCall):
            self._validate_call(
                expression,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            return
        if isinstance(expression, Unary):
            self._validate_expression(
                expression.operand,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            if expression.operator in {Operators.NEGATE, Operators.POSITIVE}:
                self._require_kind(expression.operand, ArgumentKind.NUMBER)
            return
        if isinstance(expression, Binary):
            self._validate_expression(
                expression.left,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            self._validate_expression(
                expression.right,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            if expression.operator in {
                Operators.ADD,
                Operators.SUBTRACT,
                Operators.MULTIPLY,
                Operators.DIVIDE,
                Operators.MODULO,
            }:
                self._require_kind(expression.left, ArgumentKind.NUMBER)
                self._require_kind(expression.right, ArgumentKind.NUMBER)
            if expression.operator in {
                Operators.STARTS_WITH,
                Operators.ENDS_WITH,
                Operators.CONTAINS,
            }:
                self._require_kind(expression.left, ArgumentKind.STRING)
                self._require_kind(expression.right, ArgumentKind.STRING)
            return
        if isinstance(expression, IsNull):
            self._validate_expression(
                expression.operand,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            return
        if isinstance(expression, Star):
            message = "'*' is only valid as the argument of count(*)"
            raise QuerySemanticError(message)
        message = f"unsupported expression form: {type(expression).__name__}"
        raise QuerySemanticError(message)

    def _validate_variable(self, expression: Variable) -> None:
        """Require a variable to be bound by the pattern.

        Parameters
        ----------
        expression : Variable
            Variable reference.

        Raises
        ------
        QuerySemanticError
            If the variable is not bound.
        """
        if expression.name in self._kinds:
            return
        message = f"variable {expression.name!r} is not bound"
        raise QuerySemanticError(
            message,
            line=expression.span.line if expression.span else None,
            column=expression.span.column if expression.span else None,
        )

    def _validate_call(
        self,
        expression: FunctionCall,
        *,
        aggregates_allowed: bool,
        inside_aggregate: bool,
    ) -> None:
        """Validate a scalar or aggregate function call.

        Parameters
        ----------
        expression : FunctionCall
            Function call to validate.
        aggregates_allowed : bool
            Whether aggregates may appear at this position.
        inside_aggregate : bool
            Whether the call is an aggregate argument.
        """
        spec = FunctionCatalog.spec(expression.name)
        if spec is None:
            message = f"unknown function {expression.name!r}"
            raise QuerySemanticError(
                message,
                line=expression.span.line if expression.span else None,
                column=expression.span.column if expression.span else None,
            )
        aggregate = FunctionCatalog.is_aggregate(expression.name)
        if aggregate:
            if not aggregates_allowed:
                message = "aggregate functions are not allowed in this position"
                raise QuerySemanticError(message)
            if inside_aggregate:
                message = "aggregate functions cannot be nested"
                raise QuerySemanticError(message)
        elif expression.distinct:
            message = "DISTINCT is only valid in an aggregate function call"
            raise QuerySemanticError(message)
        stars = [argument for argument in expression.arguments if isinstance(argument, Star)]
        if stars:
            if not (aggregate and expression.name.lower() == "count"):
                message = "'*' is only valid as the argument of count(*)"
                raise QuerySemanticError(message)
            if expression.distinct:
                message = "count(DISTINCT *) is not a valid aggregate"
                raise QuerySemanticError(message)
        if not spec.accepts_arity(len(expression.arguments)):
            message = (
                f"function {expression.name}() expects "
                f"{self._arity_text(spec)}; got {len(expression.arguments)}"
            )
            raise QuerySemanticError(message)
        for index, argument in enumerate(expression.arguments):
            if isinstance(argument, Star):
                continue
            self._validate_expression(
                argument,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate or aggregate,
            )
            self._require_kind(argument, spec.kind_at(index))

    def _require_kind(self, expression: Expression, expected: ArgumentKind) -> None:
        """Reject a statically known argument kind mismatch.

        Parameters
        ----------
        expression : Expression
            Expression whose kind is checked.
        expected : ArgumentKind
            Required kind.

        Raises
        ------
        QuerySemanticError
            If the expression's static kind cannot satisfy the requirement.
        """
        if expected is ArgumentKind.ANY:
            return
        actual = self._static_kind(expression)
        if actual is None or actual is ArgumentKind.ANY:
            return
        compatible = actual is expected
        if expected is ArgumentKind.ENTITY:
            compatible = actual in {ArgumentKind.NODE, ArgumentKind.RELATIONSHIP}
        if not compatible:
            message = f"expected {expected.value}; got {actual.value}"
            raise QuerySemanticError(message)

    def _static_kind(self, expression: Expression) -> ArgumentKind | None:
        """Infer the static kind of an expression when it is known.

        Parameters
        ----------
        expression : Expression
            Expression to classify.

        Returns
        -------
        ArgumentKind | None
            Known kind, or ``None`` when only runtime evaluation can decide.
        """
        if isinstance(expression, Literal):
            value = expression.value
            if value is None:
                return ArgumentKind.ANY
            if isinstance(value, bool):
                return ArgumentKind.BOOLEAN
            if isinstance(value, (int, float)):
                return ArgumentKind.NUMBER
            return ArgumentKind.STRING
        if isinstance(expression, ListLiteral):
            return ArgumentKind.LIST
        if isinstance(expression, Variable):
            kind = self._kinds.get(expression.name)
            if kind is VariableKind.NODE:
                return ArgumentKind.NODE
            if kind is VariableKind.RELATIONSHIP:
                return ArgumentKind.RELATIONSHIP
            if kind is VariableKind.PATH:
                return ArgumentKind.PATH
            return None
        if isinstance(expression, FunctionCall):
            return self._function_kind(expression.name)
        if isinstance(expression, Binary):
            if expression.operator in {
                Operators.AND,
                Operators.OR,
                Operators.IN,
                Operators.STARTS_WITH,
                Operators.ENDS_WITH,
                Operators.CONTAINS,
                Operators.EQUAL,
                Operators.NOT_EQUAL,
                Operators.LESS,
                Operators.LESS_EQUAL,
                Operators.GREATER,
                Operators.GREATER_EQUAL,
            }:
                return ArgumentKind.BOOLEAN
            return ArgumentKind.NUMBER
        if isinstance(expression, Unary):
            if expression.operator == Operators.NOT:
                return ArgumentKind.BOOLEAN
            return ArgumentKind.NUMBER
        if isinstance(expression, IsNull):
            return ArgumentKind.BOOLEAN
        return None

    @staticmethod
    def _function_kind(name: str) -> ArgumentKind | None:
        """Infer the result kind of a known function.

        Parameters
        ----------
        name : str
            Function name.

        Returns
        -------
        ArgumentKind | None
            Known result kind, or ``None`` when it depends on the input.
        """
        normalized = name.lower()
        if normalized in {"id", "size", "count", "sum", "avg", "abs", "tointeger", "tofloat"}:
            return ArgumentKind.NUMBER
        if normalized in {"labels", "keys", "collect"}:
            return ArgumentKind.LIST
        if normalized in {"type", "lower", "upper", "trim", "tostring", "concat"}:
            return ArgumentKind.STRING
        if normalized == "properties":
            return ArgumentKind.MAP
        if normalized in {"startnode", "endnode"}:
            return ArgumentKind.NODE
        return None

    @staticmethod
    def _arity_text(spec: FunctionSpec) -> str:
        """Describe a function's accepted argument count.

        Parameters
        ----------
        spec : FunctionSpec
            Function signature.

        Returns
        -------
        str
            Human-readable arity description.
        """
        if spec.maximum_arguments is None:
            return f"at least {spec.minimum_arguments} argument(s)"
        if spec.minimum_arguments == spec.maximum_arguments:
            return f"{spec.minimum_arguments} argument(s)"
        return f"between {spec.minimum_arguments} and {spec.maximum_arguments} arguments"

    @classmethod
    def _contains_aggregate(cls, expression: Expression) -> bool:
        """Report whether an expression contains an aggregate call.

        Parameters
        ----------
        expression : Expression
            Expression to inspect.

        Returns
        -------
        bool
            ``True`` when an aggregate appears anywhere in the expression.
        """
        if isinstance(expression, FunctionCall) and FunctionCatalog.is_aggregate(expression.name):
            return True
        return any(cls._contains_aggregate(child) for child in cls._children(expression))

    @staticmethod
    def _children(expression: Expression) -> tuple[Expression, ...]:
        """Return direct child expressions.

        Parameters
        ----------
        expression : Expression
            Parent expression.

        Returns
        -------
        tuple[Expression, ...]
            Child expressions in evaluation order.
        """
        if isinstance(expression, ListLiteral):
            return expression.items
        if isinstance(expression, Property):
            return (expression.target,)
        if isinstance(expression, FunctionCall):
            return expression.arguments
        if isinstance(expression, Unary):
            return (expression.operand,)
        if isinstance(expression, Binary):
            return (expression.left, expression.right)
        if isinstance(expression, IsNull):
            return (expression.operand,)
        return ()

    @classmethod
    def _expression_key(cls, expression: Expression) -> tuple[object, ...]:
        """Build a structural key that ignores source positions.

        Parameters
        ----------
        expression : Expression
            Expression to canonicalize.

        Returns
        -------
        tuple[object, ...]
            Hashable structural representation.
        """
        if isinstance(expression, Literal):
            return ("literal", type(expression.value).__name__, expression.value)
        if isinstance(expression, ListLiteral):
            return ("list", tuple(cls._expression_key(item) for item in expression.items))
        if isinstance(expression, Variable):
            return ("variable", expression.name)
        if isinstance(expression, Parameter):
            return ("parameter", expression.name)
        if isinstance(expression, Property):
            return ("property", cls._expression_key(expression.target), expression.key)
        if isinstance(expression, FunctionCall):
            return (
                "call",
                expression.name.lower(),
                expression.distinct,
                tuple(cls._expression_key(item) for item in expression.arguments),
            )
        if isinstance(expression, Unary):
            return ("unary", expression.operator, cls._expression_key(expression.operand))
        if isinstance(expression, Binary):
            return (
                "binary",
                expression.operator,
                cls._expression_key(expression.left),
                cls._expression_key(expression.right),
            )
        if isinstance(expression, IsNull):
            return ("is_null", expression.negated, cls._expression_key(expression.operand))
        return ("star",)

    @classmethod
    def _expression_text(cls, expression: Expression) -> str:
        """Render an expression when no source text is available.

        Parameters
        ----------
        expression : Expression
            Expression to render.

        Returns
        -------
        str
            Approximate source text of the expression.
        """
        if isinstance(expression, Literal):
            return repr(expression.value)
        if isinstance(expression, ListLiteral):
            return "[" + ", ".join(cls._expression_text(item) for item in expression.items) + "]"
        if isinstance(expression, Variable):
            return expression.name
        if isinstance(expression, Parameter):
            return f"${expression.name}"
        if isinstance(expression, Property):
            return f"{cls._expression_text(expression.target)}.{expression.key}"
        if isinstance(expression, FunctionCall):
            arguments = ", ".join(cls._expression_text(item) for item in expression.arguments)
            prefix = "DISTINCT " if expression.distinct else ""
            return f"{expression.name}({prefix}{arguments})"
        if isinstance(expression, Unary):
            return f"{expression.operator} {cls._expression_text(expression.operand)}"
        if isinstance(expression, Binary):
            return (
                f"{cls._expression_text(expression.left)} {expression.operator} "
                f"{cls._expression_text(expression.right)}"
            )
        if isinstance(expression, IsNull):
            suffix = " IS NOT NULL" if expression.negated else " IS NULL"
            return f"{cls._expression_text(expression.operand)}{suffix}"
        return "*"


__all__ = [
    "Analysis",
    "ReturnColumn",
    "SemanticAnalyzer",
    "SortSpec",
    "VariableKind",
]
