# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Static analysis for parsed query statements."""

import dataclasses
import typing
from collections.abc import Iterable, Mapping
from enum import Enum
from types import MappingProxyType

from pygrafito.engine.query.ast import (
    Binary,
    Case,
    Clause,
    CompoundStatement,
    Create,
    Delete,
    EdgeDirection,
    Expression,
    Filter,
    Finish,
    FunctionCall,
    GroupedPathTerm,
    HopRange,
    IsNull,
    Let,
    LetAssignment,
    ListAccess,
    ListComprehension,
    ListLiteral,
    ListSlice,
    Literal,
    MapLiteral,
    Match,
    MatchMode,
    Merge,
    Next,
    NodePattern,
    Operators,
    OrdinalityKind,
    Parameter,
    ParsedStatement,
    PathMode,
    PathPattern,
    PathSearch,
    PathSearchKind,
    Property,
    PropertyEntry,
    RelationshipPattern,
    Remove,
    Return,
    ReturnItem,
    Set,
    SetOperation,
    SimplePathTerm,
    SortItem,
    Star,
    Statement,
    Subquery,
    SubqueryKind,
    Unary,
    Unwind,
    Variable,
    With,
    Yield,
)
from pygrafito.engine.query.labels import LabelExpressions
from pygrafito.engine.query.tokens import Span
from pygrafito.engine.query.values import (
    ArgumentKind,
    FunctionCatalog,
    FunctionSpec,
)
from pygrafito.model import QuerySemanticError


class VariableKind(Enum):
    """Kind of value bound to one pattern variable."""

    NODE = "node"
    NODE_LIST = "node list"
    RELATIONSHIP = "relationship"
    RELATIONSHIP_LIST = "relationship list"
    PATH = "path"
    SCALAR = "scalar"


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
    nulls_first : bool | None, optional
        Explicit null placement, or ``None`` for the direction default.
    """

    descending: bool
    column: int | None = None
    expression: Expression | None = None
    nulls_first: bool | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class MatchStage:
    """One mandatory ``MATCH`` stage.

    Parameters
    ----------
    patterns : tuple[PathPattern, ...]
        Path patterns evaluated together as one stage.
    where : Expression | None
        Filter attached to the stage, or ``None``.
    match_mode : MatchMode, optional
        Relationship-sharing rule of the clause, by default
        ``MatchMode.REPEATABLE_ELEMENTS``.
    """

    patterns: tuple[PathPattern, ...]
    where: Expression | None
    match_mode: MatchMode = MatchMode.REPEATABLE_ELEMENTS


@dataclasses.dataclass(frozen=True, slots=True)
class OptionalMatchStage:
    """One ``OPTIONAL MATCH`` stage with left-join semantics.

    Parameters
    ----------
    patterns : tuple[PathPattern, ...]
        Path patterns evaluated together as one stage.
    where : Expression | None
        Filter attached to the optional stage, or ``None``.
    introduced : frozenset[str]
        Variables the stage introduces, which are null when it does not match.
    match_mode : MatchMode, optional
        Relationship-sharing rule of the clause, by default
        ``MatchMode.REPEATABLE_ELEMENTS``.
    """

    patterns: tuple[PathPattern, ...]
    where: Expression | None
    introduced: frozenset[str]
    match_mode: MatchMode = MatchMode.REPEATABLE_ELEMENTS


@dataclasses.dataclass(frozen=True, slots=True)
class WithStage:
    """One ``WITH`` stage that projects rows into a new scope.

    Parameters
    ----------
    items : tuple[ReturnColumn, ...]
        Analysed projection columns of the stage.
    where : Expression | None
        Filter evaluated against the projected scope, or ``None``.
    distinct : bool
        Whether duplicate projected rows are removed.
    order_by : tuple[SortSpec, ...]
        Resolved ordering keys of the stage.
    skip : Expression | None
        Pagination offset expression, or ``None``.
    limit : Expression | None
        Pagination limit expression, or ``None``.
    grouping : tuple[Expression, ...]
        Grouping-key expressions of the stage.
    has_aggregates : bool
        Whether any projected expression contains an aggregate.
    grouping_explicit : bool, optional
        Whether the grouping keys came from an explicit ``GROUP BY``, by
        default ``False``.
    segment_return : bool, optional
        Whether the stage came from a non-final ``RETURN``, by default
        ``False``.
    """

    items: tuple[ReturnColumn, ...]
    where: Expression | None
    distinct: bool
    order_by: tuple[SortSpec, ...]
    skip: Expression | None
    limit: Expression | None
    grouping: tuple[Expression, ...]
    has_aggregates: bool
    grouping_explicit: bool = False
    segment_return: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class LetStage:
    """One ``LET`` stage that adds row-wise bindings.

    Parameters
    ----------
    assignments : tuple[LetAssignment, ...]
        Assignments in evaluation order.
    """

    assignments: tuple[LetAssignment, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class YieldColumn:
    """One column selected by a ``YIELD`` stage.

    Parameters
    ----------
    source : str
        Column name in the preceding result.
    name : str
        Output column name.
    """

    source: str
    name: str


@dataclasses.dataclass(frozen=True, slots=True)
class YieldStage:
    """One ``YIELD`` stage that narrows the visible scope.

    Parameters
    ----------
    items : tuple[YieldColumn, ...]
        Selected columns in output order.
    """

    items: tuple[YieldColumn, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class UnwindStage:
    """One ``UNWIND`` stage that expands a list into rows.

    Parameters
    ----------
    expression : Expression
        List-valued expression to evaluate per input row.
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
class FilterStage:
    """One ``FILTER`` stage that keeps rows whose predicate is true.

    Parameters
    ----------
    where : Expression
        Boolean expression evaluated against the current row.
    """

    where: Expression


type ReadStage = (
    MatchStage | OptionalMatchStage | UnwindStage | WithStage | FilterStage | LetStage | YieldStage
)
type WriteClause = Create | Merge | Set | Remove | Delete


@dataclasses.dataclass(frozen=True, slots=True)
class WriteStage:
    """One write clause in the ordered operation pipeline.

    Parameters
    ----------
    clause : WriteClause
        Write clause applied by the stage.
    """

    clause: WriteClause


@dataclasses.dataclass(frozen=True, slots=True)
class NextBoundary:
    """A segment boundary introduced by ``NEXT``."""


type Operation = ReadStage | WriteStage | NextBoundary


@dataclasses.dataclass(frozen=True, slots=True)
class Analysis:
    """Result of lexing, parsing, and static analysis.

    Parameters
    ----------
    statement : Statement
        Parsed statement.
    stages : tuple[ReadStage, ...]
        Read stages in source order.
    write_clauses : tuple[WriteClause, ...]
        Write clauses in source order.
    return_clause : Return | None
        Final return clause of the statement, if any.
    is_write : bool
        Whether the statement contains any write clause.
    columns : tuple[str, ...]
        Final result column names in projection order.
    items : tuple[ReturnColumn, ...]
        Analysed final projection columns.
    variable_kinds : Mapping[str, VariableKind]
        Kind of every variable bound after every read stage.
    parameters : frozenset[str]
        Parameter names referenced by the statement.
    has_aggregates : bool
        Whether any final projected expression contains an aggregate.
    grouping : tuple[Expression, ...]
        Grouping-key expressions of the final projection.
    sorts : tuple[SortSpec, ...]
        Resolved final ordering keys in significance order.
    operations : tuple[Operation, ...]
        Read stages, writes, and segment boundaries in source order.
    finish : bool, optional
        Whether the statement ends with ``FINISH``, by default ``False``.
    grouping_explicit : bool, optional
        Whether the final projection uses an explicit ``GROUP BY``, by default
        ``False``.
    """

    statement: Statement
    stages: tuple[ReadStage, ...]
    write_clauses: tuple[WriteClause, ...]
    return_clause: Return | None
    is_write: bool
    columns: tuple[str, ...]
    items: tuple[ReturnColumn, ...]
    variable_kinds: Mapping[str, VariableKind]
    parameters: frozenset[str]
    has_aggregates: bool
    grouping: tuple[Expression, ...]
    sorts: tuple[SortSpec, ...]
    operations: tuple[Operation, ...] = ()
    finish: bool = False
    grouping_explicit: bool = False
    subquery_analyses: Mapping[int, "Analysis"] = dataclasses.field(default_factory=dict)

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


@dataclasses.dataclass(frozen=True, slots=True)
class CompoundAnalysis:
    """Static analysis of a compound set-operation query.

    Parameters
    ----------
    statement : CompoundStatement
        Parsed compound statement.
    terms : tuple[Analysis, ...]
        Per-operand analyses in source order.
    operators : tuple[SetOperation, ...]
        Operators between adjacent terms.
    columns : tuple[str, ...]
        Result column names, taken from the first operand.
    parameters : frozenset[str]
        Parameter names referenced by any operand or compound pagination.
    sorts : tuple[SortSpec, ...]
        Compound ordering keys resolved to output columns.
    skip : Expression | None
        Compound skip expression, or ``None``.
    limit : Expression | None
        Compound limit expression, or ``None``.
    """

    statement: CompoundStatement
    terms: tuple[Analysis, ...]
    operators: tuple[SetOperation, ...]
    columns: tuple[str, ...]
    parameters: frozenset[str]
    sorts: tuple[SortSpec, ...]
    skip: Expression | None
    limit: Expression | None
    subquery_analyses: Mapping[int, Analysis] = dataclasses.field(default_factory=dict)

    @property
    def is_write(self) -> bool:
        """Return whether the compound statement changes data.

        Returns
        -------
        bool
            Always ``False`` because set operands are read-only.
        """
        return False

    @property
    def finish(self) -> bool:
        """Return whether the compound statement ends with ``FINISH``.

        Returns
        -------
        bool
            Always ``False`` because set operands cannot use ``FINISH``.
        """
        return False

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
    DEFAULT_PATH_MODE: PathMode = PathMode.WALK
    MINIMUM_SET_OPERANDS: typing.ClassVar[int] = 2

    def __init__(self, statement: Statement) -> None:
        self._statement = statement
        self._kinds: dict[str, VariableKind] = {}
        self._parameters: set[str] = set()
        self._subqueries: dict[int, Analysis] = {}

    @classmethod
    def analyze(cls, statement: ParsedStatement) -> Analysis | CompoundAnalysis:
        """Analyse one parsed statement.

        Parameters
        ----------
        statement : ParsedStatement
            Parsed linear or compound statement.

        Returns
        -------
        Analysis | CompoundAnalysis
            Output contract and resolved ordering keys.
        """
        if isinstance(statement, CompoundStatement):
            return cls._analyze_compound(statement)
        return cls(statement).run()

    @classmethod
    def _analyze_compound(cls, statement: CompoundStatement) -> CompoundAnalysis:
        """Analyse a compound statement.

        Parameters
        ----------
        statement : CompoundStatement
            Compound statement to analyse.

        Returns
        -------
        CompoundAnalysis
            Combined output contract.

        Raises
        ------
        QuerySemanticError
            If an operand is a write, lacks a result, or has incompatible
            columns or ordering.
        """
        if len(statement.terms) < cls.MINIMUM_SET_OPERANDS:
            message = "a set operation requires at least two operands"
            raise QuerySemanticError(message)
        terms: list[Analysis] = []
        for term in statement.terms:
            analysis = cls(term).run()
            if analysis.is_write:
                message = "set operations are read-only"
                raise QuerySemanticError(message)
            if analysis.finish:
                message = "FINISH is not allowed in a set operand"
                raise QuerySemanticError(message)
            if analysis.return_clause is None:
                message = "a set operand must end with RETURN"
                raise QuerySemanticError(message)
            if analysis.return_clause.no_bindings:
                message = "RETURN NO BINDINGS is not allowed in a set operand"
                raise QuerySemanticError(message)
            if (
                analysis.return_clause.order_by
                or analysis.return_clause.skip is not None
                or analysis.return_clause.limit is not None
            ):
                message = "a set operand cannot carry ORDER BY, OFFSET, or LIMIT"
                raise QuerySemanticError(message)
            terms.append(analysis)
        columns = terms[0].columns
        for analysis in terms[1:]:
            if len(analysis.columns) != len(columns):
                message = "set operands must return the same number of columns"
                raise QuerySemanticError(message)
            if analysis.columns != columns:
                message = "set operands must return columns with the same names and order"
                raise QuerySemanticError(message)
        parameters = set().union(*(analysis.parameters for analysis in terms))
        subqueries: dict[int, Analysis] = {}
        for analysis in terms:
            subqueries.update(analysis.subquery_analyses)
        analyzer = cls(statement.terms[0])
        analyzer._validate_pagination(statement.skip, "OFFSET")
        analyzer._validate_pagination(statement.limit, "LIMIT")
        parameters.update(analyzer._parameters)
        sorts = cls._compound_sorts(statement.order_by, columns)
        return CompoundAnalysis(
            statement=statement,
            terms=tuple(terms),
            operators=statement.operators,
            columns=columns,
            parameters=frozenset(parameters),
            sorts=sorts,
            skip=statement.skip,
            limit=statement.limit,
            subquery_analyses=MappingProxyType(subqueries),
        )

    @classmethod
    def _compound_sorts(
        cls,
        sort_items: Iterable[SortItem],
        columns: tuple[str, ...],
    ) -> tuple[SortSpec, ...]:
        """Resolve compound ordering keys to output columns.

        Parameters
        ----------
        sort_items : Iterable[SortItem]
            Parsed compound ordering keys.
        columns : tuple[str, ...]
            Output column names.

        Returns
        -------
        tuple[SortSpec, ...]
            Ordering keys resolved to column indexes.

        Raises
        ------
        QuerySemanticError
            If a key is not an output column.
        """
        indexes = {name: index for index, name in enumerate(columns)}
        specs: list[SortSpec] = []
        for sort in sort_items:
            if not isinstance(sort.expression, Variable) or sort.expression.name not in indexes:
                message = "compound ORDER BY keys must be output column names"
                raise QuerySemanticError(message)
            specs.append(
                SortSpec(
                    descending=sort.descending,
                    column=indexes[sort.expression.name],
                    nulls_first=sort.nulls_first,
                )
            )
        return tuple(specs)

    def run(self) -> Analysis:
        """Run every static check and build the analysis.

        Returns
        -------
        Analysis
            Output contract and resolved ordering keys.
        """
        operations: list[Operation] = []
        write_clauses: list[WriteClause] = []
        return_clause: Return | None = None
        finish = False
        items: tuple[ReturnColumn, ...] = ()
        grouping: tuple[Expression, ...] = ()
        grouping_explicit = False
        sorts: tuple[SortSpec, ...] = ()
        has_aggregates = False
        segment_ended_with_return = False
        yield_allowed = False
        clauses = self._statement.clauses
        for index, clause in enumerate(clauses):
            if isinstance(clause, Next):
                operations.append(NextBoundary())
                yield_allowed = segment_ended_with_return
                segment_ended_with_return = False
                continue
            if isinstance(clause, Yield):
                if not yield_allowed:
                    message = "YIELD must follow a segment that ends with RETURN"
                    raise QuerySemanticError(message)
                stage = self._bind_yield(clause)
                operations.append(stage)
                yield_allowed = False
                continue
            if isinstance(clause, Match):
                before = frozenset(self._kinds)
                for pattern in clause.patterns:
                    self._bind_pattern(pattern)
                if clause.where is not None:
                    self._validate_expression(clause.where, aggregates_allowed=False)
                patterns = self._resolve_path_modes(clause)
                if clause.optional:
                    stage = OptionalMatchStage(
                        patterns=patterns,
                        where=clause.where,
                        introduced=frozenset(set(self._kinds) - before),
                        match_mode=clause.match_mode,
                    )
                else:
                    stage = MatchStage(
                        patterns=patterns,
                        where=clause.where,
                        match_mode=clause.match_mode,
                    )
                operations.append(stage)
            elif isinstance(clause, With):
                operations.append(self._bind_with(clause))
            elif isinstance(clause, Unwind):
                operations.append(self._bind_unwind(clause))
            elif isinstance(clause, Filter):
                self._validate_expression(clause.where, aggregates_allowed=False)
                operations.append(FilterStage(where=clause.where))
            elif isinstance(clause, Let):
                operations.append(self._bind_let(clause))
            elif isinstance(clause, Create):
                self._bind_create(clause.pattern)
                write_clauses.append(clause)
                operations.append(WriteStage(clause))
            elif isinstance(clause, Merge):
                self._bind_merge(clause)
                write_clauses.append(clause)
                operations.append(WriteStage(clause))
            elif isinstance(clause, Set):
                self._validate_set(clause)
                write_clauses.append(clause)
                operations.append(WriteStage(clause))
            elif isinstance(clause, Remove):
                self._validate_remove(clause)
                write_clauses.append(clause)
                operations.append(WriteStage(clause))
            elif isinstance(clause, Delete):
                self._validate_delete(clause)
                write_clauses.append(clause)
                operations.append(WriteStage(clause))
            elif isinstance(clause, Return):
                if self._is_followed_by_next(clauses, index):
                    operations.append(self._bind_return_stage(clause))
                    segment_ended_with_return = True
                    continue
                items, grouping, grouping_explicit, sorts, has_aggregates = self._analyze_return(
                    clause
                )
                return_clause = clause
                segment_ended_with_return = True
            elif isinstance(clause, Finish):
                finish = True
                items = ()
                grouping = ()
                grouping_explicit = False
                sorts = ()
                has_aggregates = False
            else:
                message = f"unsupported clause form: {type(clause).__name__}"
                raise QuerySemanticError(message)
        read_stages = tuple(
            operation
            for operation in operations
            if isinstance(
                operation,
                (
                    MatchStage,
                    OptionalMatchStage,
                    UnwindStage,
                    WithStage,
                    FilterStage,
                    LetStage,
                    YieldStage,
                ),
            )
        )
        return Analysis(
            statement=self._statement,
            stages=read_stages,
            write_clauses=tuple(write_clauses),
            return_clause=return_clause,
            is_write=bool(write_clauses),
            columns=tuple(item.name for item in items),
            items=items,
            variable_kinds=MappingProxyType(dict(self._kinds)),
            parameters=frozenset(self._parameters),
            has_aggregates=has_aggregates,
            grouping=grouping,
            sorts=sorts,
            operations=tuple(operations),
            finish=finish,
            grouping_explicit=grouping_explicit,
            subquery_analyses=MappingProxyType(dict(self._subqueries)),
        )

    @staticmethod
    def _is_followed_by_next(clauses: tuple[Clause, ...], index: int) -> bool:
        """Report whether a clause is followed by ``NEXT``.

        Parameters
        ----------
        clauses : tuple[Clause, ...]
            Statement clauses.
        index : int
            Position of the clause being checked.

        Returns
        -------
        bool
            ``True`` when the next clause is ``NEXT``.
        """
        return index + 1 < len(clauses) and isinstance(clauses[index + 1], Next)

    def _return_columns(self, clause: Return | None) -> tuple[ReturnColumn, ...]:
        """Analyse the projection of an optional ``RETURN`` clause.

        Parameters
        ----------
        clause : Return | None
            Return clause, or ``None`` for a write statement without one.

        Returns
        -------
        tuple[ReturnColumn, ...]
            Analysed projection columns, empty without a ``RETURN``.
        """
        if clause is None:
            return ()
        if clause.no_bindings:
            return ()
        if clause.star:
            items = tuple(
                ReturnColumn(
                    expression=Variable(name=name),
                    name=name,
                    text=name,
                    aggregate=False,
                )
                for name in self._kinds
            )
            self._require_unique_columns(items)
            return items
        items = tuple(self._column(item) for item in clause.items)
        self._require_unique_columns(items)
        return items

    def _analyze_return(
        self,
        clause: Return,
    ) -> tuple[
        tuple[ReturnColumn, ...],
        tuple[Expression, ...],
        bool,
        tuple[SortSpec, ...],
        bool,
    ]:
        """Analyse one final ``RETURN`` projection.

        Parameters
        ----------
        clause : Return
            Clause to analyse.

        Returns
        -------
        tuple[tuple[ReturnColumn, ...], tuple[Expression, ...], bool, tuple[SortSpec, ...], bool]
            Projection columns, grouping keys, whether grouping is explicit,
            ordering keys, and whether the projection contains aggregates.

        Raises
        ------
        QuerySemanticError
            If the projection or its grouping is invalid.
        """
        if clause.no_bindings:
            if clause.distinct or clause.star or clause.group_by is not None:
                message = "RETURN NO BINDINGS does not accept modifiers or GROUP BY"
                raise QuerySemanticError(message)
            if clause.order_by or clause.skip is not None or clause.limit is not None:
                message = "RETURN NO BINDINGS does not accept ordering or pagination"
                raise QuerySemanticError(message)
            return (), (), False, (), False
        items = self._return_columns(clause)
        has_aggregates = any(item.aggregate for item in items)
        grouping, grouping_explicit = self._grouping_for(clause, items)
        self._validate_projection_grouping(
            clause,
            items,
            grouping,
            grouping_explicit,
            has_aggregates,
        )
        self._validate_pagination(clause.skip, "SKIP")
        self._validate_pagination(clause.limit, "LIMIT")
        sorts = self._resolve_sorts(
            clause.order_by,
            items,
            grouping,
            has_aggregates,
        )
        return items, grouping, grouping_explicit, sorts, has_aggregates

    def _bind_return_stage(self, clause: Return) -> WithStage:
        """Analyse a non-final ``RETURN`` as a projection stage.

        Parameters
        ----------
        clause : Return
            Return clause followed by ``NEXT``.

        Returns
        -------
        WithStage
            Projection stage that resets the visible scope.

        Raises
        ------
        QuerySemanticError
            If the projection, grouping, or pagination is invalid.
        """
        if clause.no_bindings:
            message = "RETURN NO BINDINGS must be the final clause"
            raise QuerySemanticError(message)
        items, grouping, grouping_explicit, sorts, has_aggregates = self._analyze_return(clause)
        self._kinds = self._projected_kinds(items)
        return WithStage(
            items=items,
            where=None,
            distinct=clause.distinct,
            order_by=sorts,
            skip=clause.skip,
            limit=clause.limit,
            grouping=grouping,
            has_aggregates=has_aggregates,
            grouping_explicit=grouping_explicit,
            segment_return=True,
        )

    def _grouping_for(
        self,
        clause: Return,
        items: tuple[ReturnColumn, ...],
    ) -> tuple[tuple[Expression, ...], bool]:
        """Resolve the grouping keys of one ``RETURN`` projection.

        Parameters
        ----------
        clause : Return
            Return clause being analysed.
        items : tuple[ReturnColumn, ...]
            Analysed projection columns.

        Returns
        -------
        tuple[tuple[Expression, ...], bool]
            Grouping keys and whether they came from an explicit clause.
        """
        if clause.group_by is None:
            return tuple(item.expression for item in items if not item.aggregate), False
        keys: list[Expression] = []
        seen: set[tuple[object, ...]] = set()
        for key in clause.group_by:
            marker = self._expression_key(key)
            if marker in seen:
                continue
            seen.add(marker)
            keys.append(key)
        return tuple(keys), True

    def _validate_projection_grouping(
        self,
        clause: Return,
        items: tuple[ReturnColumn, ...],
        grouping: tuple[Expression, ...],
        grouping_explicit: bool,
        has_aggregates: bool,
    ) -> None:
        """Validate explicit and implicit grouping for a projection.

        Parameters
        ----------
        clause : Return
            Return clause being analysed.
        items : tuple[ReturnColumn, ...]
            Analysed projection columns.
        grouping : tuple[Expression, ...]
            Grouping-key expressions.
        grouping_explicit : bool
            Whether the keys came from an explicit ``GROUP BY``.
        has_aggregates : bool
            Whether the projection contains aggregates.

        Raises
        ------
        QuerySemanticError
            If the grouping and projection do not agree.
        """
        if clause.group_by is not None and (clause.star or clause.no_bindings):
            message = "RETURN * and RETURN NO BINDINGS cannot be combined with GROUP BY"
            raise QuerySemanticError(message)
        if grouping_explicit:
            for key in grouping:
                self._validate_expression(key, aggregates_allowed=False)
            if not grouping and (not has_aggregates or any(not item.aggregate for item in items)):
                message = "GROUP BY () requires at least one aggregate and no non-aggregate item"
                raise QuerySemanticError(message)
            keys = {self._expression_key(key) for key in grouping}
            for item in items:
                if item.aggregate:
                    continue
                if self._expression_key(item.expression) not in keys:
                    message = "a non-aggregate RETURN expression must be a grouping key"
                    raise QuerySemanticError(message)
        if has_aggregates:
            self._validate_grouping(items, grouping)

    def _bind_let(self, clause: Let) -> LetStage:
        """Analyse a ``LET`` clause and extend the visible scope.

        Parameters
        ----------
        clause : Let
            Clause to analyse.

        Returns
        -------
        LetStage
            Analysed stage carrying the ordered assignments.

        Raises
        ------
        QuerySemanticError
            If a name is already bound, repeated in the clause, or the
            expression contains an aggregate.
        """
        seen: set[str] = set()
        for assignment in clause.assignments:
            if assignment.name in self._kinds or assignment.name in seen:
                message = f"variable {assignment.name!r} is already bound"
                raise QuerySemanticError(message)
            seen.add(assignment.name)
            self._validate_expression(assignment.expression, aggregates_allowed=False)
            if isinstance(assignment.expression, Variable):
                kind = self._kinds.get(assignment.expression.name, VariableKind.SCALAR)
            else:
                kind = VariableKind.SCALAR
            self._kinds[assignment.name] = kind
        return LetStage(assignments=clause.assignments)

    def _bind_yield(self, clause: Yield) -> YieldStage:
        """Analyse a ``YIELD`` projection and reset the visible scope.

        Parameters
        ----------
        clause : Yield
            Clause to analyse.

        Returns
        -------
        YieldStage
            Analysed projection stage.

        Raises
        ------
        QuerySemanticError
            If a column is unknown or an output name is repeated.
        """
        columns: list[YieldColumn] = []
        seen: set[str] = set()
        for item in clause.items:
            if item.name not in self._kinds:
                message = f"YIELD column {item.name!r} is not bound"
                raise QuerySemanticError(message)
            name = item.name if item.alias is None else item.alias
            if name in seen:
                message = f"duplicate YIELD column {name!r}"
                raise QuerySemanticError(message)
            seen.add(name)
            columns.append(YieldColumn(source=item.name, name=name))
        self._kinds = {column.name: self._kinds[column.source] for column in columns}
        return YieldStage(items=tuple(columns))

    def _projected_kinds(self, items: tuple[ReturnColumn, ...]) -> dict[str, VariableKind]:
        """Return the scope introduced by a projection.

        Parameters
        ----------
        items : tuple[ReturnColumn, ...]
            Projected columns.

        Returns
        -------
        dict[str, VariableKind]
            Column name to preserved kind.
        """
        return {
            item.name: (
                self._kinds.get(item.expression.name, VariableKind.SCALAR)
                if isinstance(item.expression, Variable)
                else VariableKind.SCALAR
            )
            for item in items
        }

    def _bind_with(self, clause: With) -> WithStage:
        """Analyse a ``WITH`` stage and replace the visible scope.

        Parameters
        ----------
        clause : With
            Clause to analyse.

        Returns
        -------
        WithStage
            Analysed stage with its own projection, grouping, and ordering.

        Raises
        ------
        QuerySemanticError
            If an expression has no alias, two columns share a name, or an
            expression cannot be evaluated in the projected scope.
        """
        if clause.star:
            items = tuple(
                ReturnColumn(
                    expression=Variable(name=name),
                    name=name,
                    text=name,
                    aggregate=False,
                )
                for name in self._kinds
            )
            self._require_unique_columns(items)
        else:
            items = tuple(self._column(item) for item in clause.items)
            for item in clause.items:
                if not isinstance(item.expression, Variable) and item.alias is None:
                    message = "a WITH expression must have an alias"
                    raise QuerySemanticError(message)
            self._require_unique_columns(items)
        has_aggregates = any(item.aggregate for item in items)
        grouping = tuple(item.expression for item in items if not item.aggregate)
        if has_aggregates:
            self._validate_grouping(items, grouping)
        self._kinds = {
            item.name: (
                self._kinds.get(item.expression.name, VariableKind.SCALAR)
                if isinstance(item.expression, Variable)
                else VariableKind.SCALAR
            )
            for item in items
        }
        if clause.where is not None:
            self._validate_expression(clause.where, aggregates_allowed=False)
        self._validate_pagination(clause.skip, "SKIP")
        self._validate_pagination(clause.limit, "LIMIT")
        sorts = self._resolve_sorts(
            clause.order_by,
            items,
            grouping,
            has_aggregates,
        )
        return WithStage(
            items=items,
            where=clause.where,
            distinct=clause.distinct,
            order_by=sorts,
            skip=clause.skip,
            limit=clause.limit,
            grouping=grouping,
            has_aggregates=has_aggregates,
        )

    def _bind_unwind(self, clause: Unwind) -> UnwindStage:
        """Analyse an ``UNWIND`` clause and bind its variable.

        Parameters
        ----------
        clause : Unwind
            Clause to analyse.

        Returns
        -------
        UnwindStage
            Analysed stage.

        Raises
        ------
        QuerySemanticError
            If the variable is already bound, the expression is statically not
            a list, or the expression contains an aggregate.
        """
        if clause.variable in self._kinds:
            message = f"variable {clause.variable!r} is already bound"
            raise QuerySemanticError(message)
        if clause.index is not None:
            if clause.index == clause.variable:
                message = "the ordinality variable must differ from the element variable"
                raise QuerySemanticError(message)
            if clause.index in self._kinds:
                message = f"variable {clause.index!r} is already bound"
                raise QuerySemanticError(message)
        if isinstance(clause.expression, Literal) and clause.expression.value is not None:
            message = "UNWIND requires a list expression"
            raise QuerySemanticError(message)
        self._validate_expression(clause.expression, aggregates_allowed=False)
        self._kinds[clause.variable] = VariableKind.SCALAR
        if clause.index is not None:
            self._kinds[clause.index] = VariableKind.SCALAR
        return UnwindStage(
            expression=clause.expression,
            variable=clause.variable,
            index=clause.index,
            ordinality=clause.ordinality,
        )

    def _bind_merge(self, clause: Merge) -> None:
        """Analyse a ``MERGE`` clause and bind its pattern variables.

        Parameters
        ----------
        clause : Merge
            Clause to analyse.

        Raises
        ------
        QuerySemanticError
            If the pattern is not a creatable fixed-length path, references a
            forward variable, or changes a bound element.
        """
        pattern = clause.pattern
        if pattern.variable is not None:
            message = "MERGE cannot bind a path variable"
            raise QuerySemanticError(message)
        for relationship in pattern.relationships:
            if relationship.min_hops is not None or relationship.max_hops is not None:
                message = "MERGE cannot use a variable-length relationship"
                raise QuerySemanticError(message)
            if len(relationship.types) != 1:
                message = "a merged relationship must have exactly one type"
                raise QuerySemanticError(message)
            if relationship.direction is not EdgeDirection.OUTGOING:
                message = "a merged relationship must use the '-->' direction"
                raise QuerySemanticError(message)
        for node in pattern.nodes:
            self._validate_property_map(node.properties)
            self._validate_created_element(node)
        for relationship in pattern.relationships:
            self._validate_property_map(relationship.properties)
            self._validate_created_element(relationship)
        for node in pattern.nodes:
            if node.variable is None:
                continue
            existing = self._kinds.get(node.variable)
            if existing is None:
                self._register(node.variable, VariableKind.NODE)
                continue
            if existing is not VariableKind.NODE:
                message = f"variable {node.variable!r} is not a node"
                raise QuerySemanticError(message)
            if node.labels or node.properties:
                message = (
                    f"MERGE cannot change bound variable {node.variable!r}; "
                    "use SET for labels and properties"
                )
                raise QuerySemanticError(message)
        for relationship in pattern.relationships:
            if relationship.variable is None:
                continue
            if relationship.variable in self._kinds:
                message = f"MERGE cannot rebind relationship variable {relationship.variable!r}"
                raise QuerySemanticError(message)
            self._register(relationship.variable, VariableKind.RELATIONSHIP)
        if clause.on_create is not None:
            self._validate_set(clause.on_create)
        if clause.on_match is not None:
            self._validate_set(clause.on_match)

    def _bind_create(self, pattern: PathPattern) -> None:
        """Register the variables created by a ``CREATE`` pattern.

        Node patterns with a variable already in scope refer to that node;
        other node patterns create a node. Both endpoints of a created
        relationship must already be in scope.

        Parameters
        ----------
        pattern : PathPattern
            Pattern of the create clause.

        Raises
        ------
        QuerySemanticError
            If the pattern uses a path variable, redefines a bound node, or
            creates a relationship with an unbound endpoint.
        """
        if pattern.variable is not None:
            message = "path variables are not supported in CREATE"
            raise QuerySemanticError(message)
        bound = frozenset(self._kinds)
        for node in pattern.nodes:
            self._validate_property_map(node.properties)
            self._validate_created_element(node)
        for relationship in pattern.relationships:
            self._validate_property_map(relationship.properties)
            self._validate_created_element(relationship)
        for index, _relationship in enumerate(pattern.relationships):
            endpoints = (pattern.nodes[index], pattern.nodes[index + 1])
            for node in endpoints:
                if node.variable is None or node.variable not in bound:
                    message = "both endpoints of a created relationship must be already bound"
                    raise QuerySemanticError(message)
        for node in pattern.nodes:
            if node.variable is None:
                continue
            if node.variable in bound:
                self._register(node.variable, VariableKind.NODE)
                if node.labels or node.properties:
                    message = (
                        f"CREATE cannot change bound variable {node.variable!r}; "
                        "use SET for labels and properties"
                    )
                    raise QuerySemanticError(message)
            else:
                self._register(node.variable, VariableKind.NODE)
        for relationship in pattern.relationships:
            if relationship.min_hops is not None or relationship.max_hops is not None:
                message = "CREATE cannot use a variable-length relationship"
                raise QuerySemanticError(message)
            if len(relationship.types) > 1:
                message = "a created relationship must have at most one label"
                raise QuerySemanticError(message)
            if relationship.direction is not EdgeDirection.OUTGOING:
                message = "a created relationship must use the '-->' direction"
                raise QuerySemanticError(message)
            if relationship.variable is not None:
                self._register(relationship.variable, VariableKind.RELATIONSHIP)

    def _validate_set(self, clause: Set) -> None:
        """Validate a ``SET`` clause.

        Parameters
        ----------
        clause : Set
            Clause to validate.

        Raises
        ------
        QuerySemanticError
            If a target is unbound or not a node or relationship.
        """
        for assignment in clause.assignments:
            self._require_write_target(assignment.variable, assignment.span, "SET")
            self._validate_expression(assignment.value, aggregates_allowed=False)
        for label in clause.labels:
            self._require_write_target(label.variable, label.span, "SET")

    def _validate_remove(self, clause: Remove) -> None:
        """Validate a ``REMOVE`` clause.

        Parameters
        ----------
        clause : Remove
            Clause to validate.

        Raises
        ------
        QuerySemanticError
            If a target is unbound or not a node or relationship.
        """
        for removal in clause.properties:
            self._require_write_target(removal.variable, removal.span, "REMOVE")
        for label in clause.labels:
            self._require_write_target(label.variable, label.span, "REMOVE")

    def _validate_delete(self, clause: Delete) -> None:
        """Validate a ``DELETE`` clause.

        Parameters
        ----------
        clause : Delete
            Clause to validate.

        Raises
        ------
        QuerySemanticError
            If a target is unbound or is a path.
        """
        for name in clause.variables:
            self._require_write_target(name, None, "DELETE")

    def _require_write_target(
        self,
        name: str,
        span: Span | None,
        clause: str,
    ) -> VariableKind:
        """Require a write target to be a bound node or relationship.

        Parameters
        ----------
        name : str
            Variable name.
        span : Span | None
            Source position of the reference.
        clause : str
            Clause name used in error messages.

        Returns
        -------
        VariableKind
            Kind of the bound variable.

        Raises
        ------
        QuerySemanticError
            If the variable is unbound or is a path.
        """
        kind = self._kinds.get(name)
        if kind is None:
            message = f"variable {name!r} is not bound"
            raise QuerySemanticError(
                message,
                line=span.line if span else None,
                column=span.column if span else None,
            )
        if kind in {
            VariableKind.PATH,
            VariableKind.NODE_LIST,
            VariableKind.RELATIONSHIP_LIST,
            VariableKind.SCALAR,
        }:
            message = f"{clause} cannot target {kind.value} variable {name!r}"
            raise QuerySemanticError(
                message,
                line=span.line if span else None,
                column=span.column if span else None,
            )
        return kind

    def _bind_pattern(self, pattern: PathPattern) -> None:
        """Register every pattern variable and validate property maps.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to bind.
        """
        if pattern.variable is not None:
            existing = self._kinds.get(pattern.variable)
            if existing is not None:
                message = f"path variable {pattern.variable!r} is already bound"
                raise QuerySemanticError(message)
        if pattern.search is not None:
            self._validate_search(pattern.search)
        if pattern.variable is not None:
            self._register(pattern.variable, VariableKind.PATH)
        for term in pattern.terms:
            if isinstance(term, SimplePathTerm):
                self._bind_simple_term(
                    term,
                    group_locals=None,
                    visible=frozenset(self._kinds),
                    outer_locals=frozenset(),
                )
            else:
                self._bind_group(
                    term,
                    visible=frozenset(self._kinds),
                    outer_locals=frozenset(),
                )
        if (
            len(pattern.terms) == 1
            and isinstance(pattern.terms[0], GroupedPathTerm)
            and pattern.terms[0].quantifier.min_hops == 0
        ):
            message = "a path pattern cannot consist only of a group with a zero lower bound"
            raise QuerySemanticError(message)

    def _bind_simple_term(
        self,
        term: SimplePathTerm,
        *,
        group_locals: dict[str, VariableKind] | None,
        visible: frozenset[str],
        outer_locals: frozenset[str],
    ) -> None:
        """Bind one simple path term.

        Parameters
        ----------
        term : SimplePathTerm
            Term to bind.
        group_locals : dict[str, VariableKind] | None
            Variables introduced by the enclosing group, or ``None`` outside
            a group.
        visible : frozenset[str]
            Variables bound before the outermost group.
        outer_locals : frozenset[str]
            Variables local to an enclosing group.
        """
        for node in term.nodes:
            self._validate_property_map(node.properties)
            if node.variable is not None:
                kind = VariableKind.NODE if group_locals is None else VariableKind.NODE_LIST
                self._bind_scoped_variable(
                    node.variable,
                    kind,
                    group_locals=group_locals,
                    visible=visible,
                    outer_locals=outer_locals,
                )
        for relationship in term.relationships:
            quantified = relationship.min_hops is not None or relationship.max_hops is not None
            if quantified:
                self._validate_quantifier(relationship)
            self._validate_property_map(relationship.properties)
            if relationship.variable is not None:
                kind = (
                    VariableKind.RELATIONSHIP
                    if group_locals is None and not quantified
                    else VariableKind.RELATIONSHIP_LIST
                )
                self._bind_scoped_variable(
                    relationship.variable,
                    kind,
                    group_locals=group_locals,
                    visible=visible,
                    outer_locals=outer_locals,
                )
        for node in term.nodes:
            if node.where is not None:
                self._validate_expression(node.where, aggregates_allowed=False)
        for relationship in term.relationships:
            if relationship.where is not None:
                self._validate_expression(relationship.where, aggregates_allowed=False)

    def _bind_scoped_variable(
        self,
        name: str,
        kind: VariableKind,
        *,
        group_locals: dict[str, VariableKind] | None,
        visible: frozenset[str],
        outer_locals: frozenset[str],
    ) -> None:
        """Register one variable under the current group scope.

        Parameters
        ----------
        name : str
            Variable name.
        kind : VariableKind
            Kind required at this position.
        group_locals : dict[str, VariableKind] | None
            Variables introduced by the enclosing group, or ``None`` outside
            a group.
        visible : frozenset[str]
            Variables bound before the outermost group.
        outer_locals : frozenset[str]
            Variables local to an enclosing group.

        Raises
        ------
        QuerySemanticError
            If the variable shadows an outer name, repeats inside one group,
            or conflicts with an existing kind.
        """
        if group_locals is None:
            self._register(name, kind)
            return
        if name in outer_locals:
            message = f"nested group cannot reference enclosing group variable {name!r}"
            raise QuerySemanticError(message)
        if name in visible:
            scalar = (
                VariableKind.NODE if kind is VariableKind.NODE_LIST else VariableKind.RELATIONSHIP
            )
            existing = self._kinds.get(name)
            if existing is not scalar:
                message = (
                    f"variable {name!r} is already bound as a "
                    f"{None if existing is None else existing.value} and cannot be a "
                    f"{scalar.value}"
                )
                raise QuerySemanticError(message)
            return
        if name in group_locals:
            message = f"variable {name!r} occurs more than once in one group"
            raise QuerySemanticError(message)
        self._register(name, kind)
        group_locals[name] = kind

    def _bind_group(
        self,
        term: GroupedPathTerm,
        *,
        visible: frozenset[str],
        outer_locals: frozenset[str],
    ) -> dict[str, VariableKind]:
        """Bind one grouped path term and its inner pattern.

        Parameters
        ----------
        term : GroupedPathTerm
            Grouped term to bind.
        visible : frozenset[str]
            Variables bound before the outermost group.
        outer_locals : frozenset[str]
            Variables local to an enclosing group.

        Returns
        -------
        dict[str, VariableKind]
            Variables introduced by this group, including nested groups.

        Raises
        ------
        QuerySemanticError
            If a scope, path variable, quantifier, or progress rule is
            violated.
        """
        self._validate_group_quantifier(term.quantifier)
        if term.pattern.variable is not None:
            message = "a grouped path binds its path variable before the inner pattern"
            raise QuerySemanticError(message)
        if term.pattern.search is not None:
            message = "a path-search prefix is not allowed inside a grouped pattern"
            raise QuerySemanticError(message)
        if term.pattern.minimum_relationships() < 1:
            message = "a grouped path must consume at least one relationship per iteration"
            raise QuerySemanticError(message)
        group_locals: dict[str, VariableKind] = {}
        if term.variable is not None:
            if term.quantifier.min_hops < 1:
                message = "a group path variable requires a positive lower bound"
                raise QuerySemanticError(message)
            if (
                term.variable in visible
                or term.variable in outer_locals
                or term.variable in group_locals
            ):
                message = f"group path variable {term.variable!r} shadows an outer variable"
                raise QuerySemanticError(message)
            self._register(term.variable, VariableKind.PATH)
            group_locals[term.variable] = VariableKind.PATH
        for inner in term.pattern.terms:
            if isinstance(inner, SimplePathTerm):
                self._bind_simple_term(
                    inner,
                    group_locals=group_locals,
                    visible=visible,
                    outer_locals=outer_locals,
                )
                continue
            nested = self._bind_group(
                inner,
                visible=visible,
                outer_locals=outer_locals | frozenset(group_locals),
            )
            for name, kind in nested.items():
                if name in group_locals:
                    message = f"variable {name!r} occurs more than once in one group"
                    raise QuerySemanticError(message)
                group_locals[name] = kind
        return group_locals

    @staticmethod
    def _validate_group_quantifier(quantifier: HopRange) -> None:
        """Validate the bounds of a grouped path term.

        Parameters
        ----------
        quantifier : HopRange
            Group repetition bounds.

        Raises
        ------
        QuerySemanticError
            If a bound is negative or the lower bound exceeds the upper bound.
        """
        if quantifier.min_hops < 0 or (quantifier.max_hops is not None and quantifier.max_hops < 0):
            message = "grouped path bounds must be non-negative"
            raise QuerySemanticError(message)
        if quantifier.max_hops is not None and quantifier.min_hops > quantifier.max_hops:
            message = "the grouped path lower bound cannot exceed the upper bound"
            raise QuerySemanticError(message)

    @staticmethod
    def _validate_search(search: PathSearch) -> None:
        """Validate one path-search prefix.

        Parameters
        ----------
        search : PathSearch
            Parsed prefix.

        Raises
        ------
        QuerySemanticError
            If ``SHORTEST`` carries a missing or negative count.
        """
        if search.kind is not PathSearchKind.SHORTEST:
            return
        if search.k is None or search.k < 0:
            message = "SHORTEST k requires a non-negative integer literal"
            if search.span is None:
                raise QuerySemanticError(message)
            raise QuerySemanticError(
                message,
                line=search.span.line,
                column=search.span.column,
            )

    @staticmethod
    def _validate_quantifier(relationship: RelationshipPattern) -> None:
        """Validate the bounds of a quantified relationship.

        Parameters
        ----------
        relationship : RelationshipPattern
            Relationship pattern carrying the quantifier.

        Raises
        ------
        QuerySemanticError
            If a bound is negative or the lower bound exceeds a present upper
            bound.
        """
        upper = relationship.max_hops
        lower = 1 if relationship.min_hops is None else relationship.min_hops
        if lower < 0 or (upper is not None and upper < 0):
            message = "variable-length bounds must be non-negative"
            raise QuerySemanticError(message)
        if upper is not None and lower > upper:
            message = "the variable-length lower bound cannot exceed the upper bound"
            raise QuerySemanticError(message)

    @classmethod
    def _resolve_path_modes(cls, clause: Match) -> tuple[PathPattern, ...]:
        """Resolve the effective path mode of every pattern in a match clause.

        Parameters
        ----------
        clause : Match
            Match clause whose patterns are resolved.

        Returns
        -------
        tuple[PathPattern, ...]
            Patterns carrying their resolved mode.

        Raises
        ------
        QuerySemanticError
            If one path mixes a legacy and a canonical quantifier without an
            explicit mode.
        """
        return tuple(
            dataclasses.replace(pattern, mode=cls._resolve_path_mode(clause.mode, pattern))
            for pattern in clause.patterns
        )

    @classmethod
    def _resolve_path_mode(
        cls,
        clause_mode: PathMode | None,
        pattern: PathPattern,
    ) -> PathMode:
        """Resolve one path's effective mode.

        Parameters
        ----------
        clause_mode : PathMode | None
            Mode named by the clause, or ``None``.
        pattern : PathPattern
            Pattern whose mode is resolved.

        Returns
        -------
        PathMode
            Explicit per-path mode, explicit clause mode, ``TRAIL`` for a
            legacy quantifier, or the canonical default.

        Raises
        ------
        QuerySemanticError
            If the path mixes both quantifier forms without an explicit mode.
        """
        if pattern.mode is not None:
            return pattern.mode
        if clause_mode is not None:
            return clause_mode
        relationships = pattern.all_relationships()
        legacy = any(
            relationship.canonical_quantifier is False
            and (relationship.min_hops is not None or relationship.max_hops is not None)
            for relationship in relationships
        )
        canonical = any(relationship.canonical_quantifier for relationship in relationships)
        if legacy and canonical:
            message = (
                "a path cannot mix a legacy and a canonical quantifier without an explicit "
                "path mode"
            )
            raise QuerySemanticError(message)
        return PathMode.TRAIL if legacy else cls.DEFAULT_PATH_MODE

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

    @classmethod
    def _validate_created_element(cls, pattern: NodePattern | RelationshipPattern) -> None:
        """Reject unsupported constraints on a created element.

        Parameters
        ----------
        pattern : NodePattern | RelationshipPattern
            Created element pattern.

        Raises
        ------
        QuerySemanticError
            If the pattern carries an inline predicate or a label expression
            that is not a plain conjunction.
        """
        if pattern.where is not None:
            message = "an inline predicate is not supported in a write pattern"
            raise QuerySemanticError(message)
        if (
            pattern.label_expression is not None
            and LabelExpressions.conjunction(pattern.label_expression) is None
        ):
            if isinstance(pattern, RelationshipPattern):
                message = "a created relationship must have at most one label"
            else:
                message = "a written node must use a conjunction of labels"
            raise QuerySemanticError(message)

    def _validate_property_map(self, entries: Iterable[PropertyEntry]) -> None:
        """Validate the expressions of one pattern property map.

        Parameters
        ----------
        entries : Iterable[PropertyEntry]
            Property-map entries to validate.
        """
        for entry in entries:
            self._validate_expression(entry.value, aggregates_allowed=False)

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
        if isinstance(
            expression,
            (Binary, Unary, IsNull, Case, MapLiteral, ListAccess, ListSlice, ListComprehension),
        ):
            for child in self._children(expression):
                if not isinstance(child, (Literal, Parameter)):
                    self._validate_grouped(child, grouping_keys)
            return
        if isinstance(expression, FunctionCall):
            for argument in expression.arguments:
                if not isinstance(argument, (Literal, Parameter, Star)):
                    self._validate_grouped(argument, grouping_keys)
            return
        if isinstance(expression, Subquery):
            message = (
                "a correlated query expression in an aggregate projection must be a grouping key"
            )
            raise QuerySemanticError(message)
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
                        nulls_first=sort.nulls_first,
                    )
                )
                continue
            key = self._expression_key(sort.expression)
            if key in expression_indexes:
                specs.append(
                    SortSpec(
                        descending=sort.descending,
                        column=expression_indexes[key],
                        nulls_first=sort.nulls_first,
                    )
                )
                continue
            self._validate_expression(sort.expression, aggregates_allowed=False)
            if has_aggregates:
                self._validate_grouped(sort.expression, grouping_keys)
            specs.append(
                SortSpec(
                    descending=sort.descending,
                    expression=sort.expression,
                    nulls_first=sort.nulls_first,
                )
            )
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
        if isinstance(expression, Case):
            if expression.operand is not None:
                self._validate_expression(
                    expression.operand,
                    aggregates_allowed=aggregates_allowed,
                    inside_aggregate=inside_aggregate,
                )
            for branch in expression.branches:
                self._validate_expression(
                    branch.match,
                    aggregates_allowed=aggregates_allowed,
                    inside_aggregate=inside_aggregate,
                )
                if expression.operand is None:
                    self._require_kind(branch.match, ArgumentKind.BOOLEAN)
                self._validate_expression(
                    branch.result,
                    aggregates_allowed=aggregates_allowed,
                    inside_aggregate=inside_aggregate,
                )
            if expression.default is not None:
                self._validate_expression(
                    expression.default,
                    aggregates_allowed=aggregates_allowed,
                    inside_aggregate=inside_aggregate,
                )
            return
        if isinstance(expression, MapLiteral):
            for entry in expression.entries:
                self._validate_expression(
                    entry.value,
                    aggregates_allowed=aggregates_allowed,
                    inside_aggregate=inside_aggregate,
                )
            return
        if isinstance(expression, ListAccess):
            self._validate_expression(
                expression.target,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            self._validate_expression(
                expression.index,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            self._require_kind(expression.target, ArgumentKind.LIST)
            self._require_kind(expression.index, ArgumentKind.NUMBER)
            return
        if isinstance(expression, ListSlice):
            self._validate_expression(
                expression.target,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            if expression.start is not None:
                self._validate_expression(
                    expression.start,
                    aggregates_allowed=aggregates_allowed,
                    inside_aggregate=inside_aggregate,
                )
                self._require_kind(expression.start, ArgumentKind.NUMBER)
            if expression.end is not None:
                self._validate_expression(
                    expression.end,
                    aggregates_allowed=aggregates_allowed,
                    inside_aggregate=inside_aggregate,
                )
                self._require_kind(expression.end, ArgumentKind.NUMBER)
            self._require_kind(expression.target, ArgumentKind.LIST)
            return
        if isinstance(expression, ListComprehension):
            self._validate_expression(
                expression.source,
                aggregates_allowed=aggregates_allowed,
                inside_aggregate=inside_aggregate,
            )
            self._require_kind(expression.source, ArgumentKind.LIST)
            if expression.variable in self._kinds:
                message = f"variable {expression.variable!r} is already bound"
                raise QuerySemanticError(message)
            self._kinds[expression.variable] = VariableKind.SCALAR
            try:
                if expression.where is not None:
                    self._validate_expression(
                        expression.where,
                        aggregates_allowed=False,
                        inside_aggregate=inside_aggregate,
                    )
                    self._require_kind(expression.where, ArgumentKind.BOOLEAN)
                if expression.projection is not None:
                    self._validate_expression(
                        expression.projection,
                        aggregates_allowed=False,
                        inside_aggregate=inside_aggregate,
                    )
            finally:
                del self._kinds[expression.variable]
            return
        if isinstance(expression, Subquery):
            self._validate_subquery(expression)
            return
        if isinstance(expression, Variable):
            self._validate_variable(expression)
            return
        if isinstance(expression, Parameter):
            self._parameters.add(expression.name)
            return
        if isinstance(expression, Property):
            if isinstance(expression.target, Variable):
                kind = self._kinds.get(expression.target.name)
                if kind is VariableKind.PATH:
                    message = "path variables do not have properties"
                    raise QuerySemanticError(message)
                if kind is VariableKind.RELATIONSHIP_LIST:
                    message = "relationship lists do not have properties"
                    raise QuerySemanticError(message)
                if kind is VariableKind.NODE_LIST:
                    message = "node lists do not have properties"
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
            if expression.operator == Operators.ADD:
                self._validate_additive_operands(expression.left, expression.right)
            elif expression.operator in {
                Operators.SUBTRACT,
                Operators.MULTIPLY,
                Operators.DIVIDE,
                Operators.MODULO,
            }:
                self._require_kind(expression.left, ArgumentKind.NUMBER)
                self._require_kind(expression.right, ArgumentKind.NUMBER)
            if expression.operator == Operators.CONCAT:
                self._require_kind(expression.left, ArgumentKind.STRING)
                self._require_kind(expression.right, ArgumentKind.STRING)
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

    def _validate_additive_operands(self, left: Expression, right: Expression) -> None:
        """Validate the numeric-or-string form of ``+``.

        Parameters
        ----------
        left : Expression
            Left operand.
        right : Expression
            Right operand.

        Raises
        ------
        QuerySemanticError
            If the statically known operands cannot both be strings or both
            be numbers.
        """
        left_kind = self._static_kind(left)
        right_kind = self._static_kind(right)
        string_kinds = {ArgumentKind.STRING, ArgumentKind.ANY, None}
        if (
            left_kind in string_kinds
            and right_kind in string_kinds
            and (left_kind is ArgumentKind.STRING or right_kind is ArgumentKind.STRING)
        ):
            return
        if left_kind is ArgumentKind.STRING or right_kind is ArgumentKind.STRING:
            message = "operator '+' requires both operands to be strings or both to be numbers"
            raise QuerySemanticError(message)
        self._require_kind(left, ArgumentKind.NUMBER)
        self._require_kind(right, ArgumentKind.NUMBER)

    def _validate_subquery(self, expression: Subquery) -> None:
        """Validate one read-only query expression.

        Parameters
        ----------
        expression : Subquery
            Subquery expression to validate.

        Raises
        ------
        QuerySemanticError
            If the inner block is not a valid read-only row source.
        """
        clauses = expression.clauses
        if any(
            isinstance(clause, (Create, Merge, Set, Remove, Delete, Return, Finish, Next, Yield))
            for clause in clauses
        ):
            message = "a subquery is read-only and cannot contain a result or write clause"
            raise QuerySemanticError(message)
        if not any(isinstance(clause, (Match, Let, Unwind)) for clause in clauses):
            message = "a subquery requires at least one row source"
            raise QuerySemanticError(message)
        inner = SemanticAnalyzer(Statement(clauses=clauses))
        inner._kinds = dict(self._kinds)
        analysis = inner.run()
        self._parameters.update(analysis.parameters)
        self._subqueries[id(expression)] = analysis

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
        if isinstance(expression, MapLiteral):
            return ArgumentKind.MAP
        if isinstance(expression, ListComprehension):
            return ArgumentKind.LIST
        if isinstance(expression, Subquery):
            if expression.kind is SubqueryKind.EXISTS:
                return ArgumentKind.BOOLEAN
            return ArgumentKind.NUMBER
        if isinstance(expression, Case):
            if expression.default is None:
                return None
            kinds = {self._static_kind(branch.result) for branch in expression.branches}
            kinds.add(self._static_kind(expression.default))
            return kinds.pop() if len(kinds) == 1 else None
        if isinstance(expression, (ListAccess, ListSlice)):
            return None
        if isinstance(expression, Variable):
            kind = self._kinds.get(expression.name)
            if kind is VariableKind.NODE:
                return ArgumentKind.NODE
            if kind is VariableKind.RELATIONSHIP:
                return ArgumentKind.RELATIONSHIP
            if kind in {VariableKind.RELATIONSHIP_LIST, VariableKind.NODE_LIST}:
                return ArgumentKind.LIST
            if kind is VariableKind.PATH:
                return ArgumentKind.PATH
            return None
        if isinstance(expression, FunctionCall):
            return self._function_kind(expression.name)
        if isinstance(expression, Binary):
            if expression.operator == Operators.CONCAT:
                return ArgumentKind.STRING
            if expression.operator == Operators.ADD:
                left = self._static_kind(expression.left)
                right = self._static_kind(expression.right)
                if left is ArgumentKind.STRING and right is ArgumentKind.STRING:
                    return ArgumentKind.STRING
                return ArgumentKind.NUMBER
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
        if normalized in {
            "id",
            "size",
            "count",
            "sum",
            "avg",
            "abs",
            "tointeger",
            "tofloat",
            "length",
            "ceil",
            "floor",
            "round",
        }:
            return ArgumentKind.NUMBER
        if normalized in {
            "labels",
            "keys",
            "collect",
            "range",
            "tail",
            "split",
            "nodes",
            "relationships",
        }:
            return ArgumentKind.LIST
        if normalized in {
            "type",
            "lower",
            "upper",
            "trim",
            "tostring",
            "concat",
            "substring",
            "replace",
        }:
            return ArgumentKind.STRING
        if normalized == "properties":
            return ArgumentKind.MAP
        if normalized == "toboolean":
            return ArgumentKind.BOOLEAN
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
        if isinstance(expression, Case):
            children: list[Expression] = []
            if expression.operand is not None:
                children.append(expression.operand)
            for branch in expression.branches:
                children.extend((branch.match, branch.result))
            if expression.default is not None:
                children.append(expression.default)
            return tuple(children)
        if isinstance(expression, MapLiteral):
            return tuple(entry.value for entry in expression.entries)
        if isinstance(expression, ListAccess):
            return (expression.target, expression.index)
        if isinstance(expression, ListSlice):
            bounds = [expression.target]
            if expression.start is not None:
                bounds.append(expression.start)
            if expression.end is not None:
                bounds.append(expression.end)
            return tuple(bounds)
        if isinstance(expression, ListComprehension):
            children = [expression.source]
            if expression.where is not None:
                children.append(expression.where)
            if expression.projection is not None:
                children.append(expression.projection)
            return tuple(children)
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
        if isinstance(expression, Case):
            return (
                "case",
                cls._expression_key(expression.operand) if expression.operand is not None else None,
                tuple(
                    (cls._expression_key(branch.match), cls._expression_key(branch.result))
                    for branch in expression.branches
                ),
                cls._expression_key(expression.default) if expression.default is not None else None,
            )
        if isinstance(expression, MapLiteral):
            return (
                "map",
                tuple(
                    (entry.key, cls._expression_key(entry.value)) for entry in expression.entries
                ),
            )
        if isinstance(expression, ListAccess):
            return (
                "list_access",
                cls._expression_key(expression.target),
                cls._expression_key(expression.index),
            )
        if isinstance(expression, ListSlice):
            return (
                "list_slice",
                cls._expression_key(expression.target),
                cls._expression_key(expression.start) if expression.start is not None else None,
                cls._expression_key(expression.end) if expression.end is not None else None,
            )
        if isinstance(expression, ListComprehension):
            return (
                "comprehension",
                expression.variable,
                cls._expression_key(expression.source),
                cls._expression_key(expression.where) if expression.where is not None else None,
                cls._expression_key(expression.projection)
                if expression.projection is not None
                else None,
            )
        if isinstance(expression, Subquery):
            return ("subquery", expression.kind.value, tuple(map(id, expression.clauses)))
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
        if isinstance(expression, Case):
            prefix = (
                f"CASE {cls._expression_text(expression.operand)}"
                if expression.operand is not None
                else "CASE"
            )
            branches = " ".join(
                f"WHEN {cls._expression_text(branch.match)} THEN "
                f"{cls._expression_text(branch.result)}"
                for branch in expression.branches
            )
            default = (
                f" ELSE {cls._expression_text(expression.default)}"
                if expression.default is not None
                else ""
            )
            return f"{prefix} {branches}{default} END"
        if isinstance(expression, MapLiteral):
            entries = ", ".join(
                f"{entry.key}: {cls._expression_text(entry.value)}" for entry in expression.entries
            )
            return "{" + entries + "}"
        if isinstance(expression, ListAccess):
            target = cls._expression_text(expression.target)
            index = cls._expression_text(expression.index)
            return f"{target}[{index}]"
        if isinstance(expression, ListSlice):
            start = "" if expression.start is None else cls._expression_text(expression.start)
            end = "" if expression.end is None else cls._expression_text(expression.end)
            return f"{cls._expression_text(expression.target)}[{start}:{end}]"
        if isinstance(expression, ListComprehension):
            where = (
                f" WHERE {cls._expression_text(expression.where)}"
                if expression.where is not None
                else ""
            )
            projection = (
                f" | {cls._expression_text(expression.projection)}"
                if expression.projection is not None
                else ""
            )
            return (
                f"[{expression.variable} IN {cls._expression_text(expression.source)}"
                f"{where}{projection}]"
            )
        if isinstance(expression, Subquery):
            return f"{expression.kind.value} {{ ... }}"
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
    "CompoundAnalysis",
    "FilterStage",
    "LetStage",
    "MatchStage",
    "NextBoundary",
    "OptionalMatchStage",
    "ReadStage",
    "ReturnColumn",
    "SemanticAnalyzer",
    "SortSpec",
    "UnwindStage",
    "VariableKind",
    "WithStage",
    "WriteClause",
    "WriteStage",
    "YieldColumn",
    "YieldStage",
]
