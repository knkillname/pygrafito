# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Execute planned queries against SQLite and assemble results."""

import contextlib
import dataclasses
import functools
import json
import sqlite3
import typing
from collections.abc import Mapping, Sequence
from sqlite3 import Connection

from pygrafito.engine.query.ast import (
    Binary,
    Expression,
    FunctionCall,
    IsNull,
    ListLiteral,
    Literal,
    Match,
    NodePattern,
    Parameter,
    PathPattern,
    Property,
    Star,
    Unary,
    Variable,
)
from pygrafito.engine.query.budget import BudgetTracker
from pygrafito.engine.query.compiler import (
    CompiledMatch,
    Compiler,
    NodeColumn,
    RelationshipColumns,
)
from pygrafito.engine.query.mutation import MutationExecutor
from pygrafito.engine.query.pattern import PatternEngine
from pygrafito.engine.query.plan import Plan
from pygrafito.engine.query.results import QueryResult, Row
from pygrafito.engine.query.semantic import (
    FilterStage,
    MatchStage,
    OptionalMatchStage,
    ReturnColumn,
    SortSpec,
    UnwindStage,
    WithStage,
)
from pygrafito.engine.query.values import (
    Aggregates,
    ExpressionEvaluator,
    FunctionCatalog,
    PatternValueResolver,
    QueryValue,
    ScalarFunctions,
    SnapshotSource,
    ValueKey,
    Values,
)
from pygrafito.model import (
    ConnectedNodeError,
    Constraint,
    ConstraintViolationError,
    Node,
    NotFoundError,
    Path,
    QueryBudget,
    QueryError,
    QueryExecutionError,
    QuerySemanticError,
    Relationship,
    TransactionError,
    ValidationError,
)
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.constraints import ConstraintRegistry
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository


class RepositorySnapshots(SnapshotSource):
    """Load element snapshots on demand from the repositories.

    Parameters
    ----------
    nodes : NodeRepository
        Source for node snapshots.
    relationships : RelationshipRepository
        Source for relationship snapshots.
    """

    def __init__(
        self,
        nodes: NodeRepository,
        relationships: RelationshipRepository,
    ) -> None:
        self._nodes = nodes
        self._relationships = relationships
        self._node_cache: dict[int, Node] = {}
        self._relationship_cache: dict[int, Relationship] = {}

    @typing.override
    def node(self, node_id: int) -> Node:
        """Read a cached node snapshot.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        Node
            Node snapshot.
        """
        cached = self._node_cache.get(node_id)
        if cached is None:
            cached = self._nodes.get(node_id)
            self._node_cache[node_id] = cached
        return cached

    @typing.override
    def relationship(self, relationship_id: int) -> Relationship:
        """Read a cached relationship snapshot.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.

        Returns
        -------
        Relationship
            Relationship snapshot.
        """
        cached = self._relationship_cache.get(relationship_id)
        if cached is None:
            cached = self._relationships.get(relationship_id)
            self._relationship_cache[relationship_id] = cached
        return cached


class GroupEvaluator:
    """Evaluate a projection over one aggregate input group.

    Parameters
    ----------
    evaluator : ExpressionEvaluator
        Scalar expression evaluator.
    functions : ScalarFunctions
        Scalar function implementation.
    parameters : Mapping[str, QueryValue]
        Query parameter values.
    """

    def __init__(
        self,
        evaluator: ExpressionEvaluator,
        functions: ScalarFunctions,
        parameters: Mapping[str, QueryValue],
    ) -> None:
        self._evaluator = evaluator
        self._functions = functions
        self._parameters = parameters

    def evaluate(
        self,
        expression: Expression,
        group: Sequence[Mapping[str, QueryValue]],
    ) -> QueryValue:
        """Evaluate one projection expression over a group.

        Parameters
        ----------
        expression : Expression
            Projection expression.
        group : Sequence[Mapping[str, QueryValue]]
            Input bindings belonging to the group.

        Returns
        -------
        QueryValue
            Projected value.
        """
        if isinstance(expression, FunctionCall):
            if FunctionCatalog.is_aggregate(expression.name):
                return self._aggregate(expression, group)
            arguments = [self.evaluate(item, group) for item in expression.arguments]
            return self._functions.call(expression.name, arguments)
        if isinstance(expression, ListLiteral):
            return [self.evaluate(item, group) for item in expression.items]
        if isinstance(expression, (Literal, Parameter)):
            return self._evaluator.evaluate(expression, {}, self._parameters)
        if isinstance(expression, Star):
            message = "'*' is only valid as the argument of count(*)"
            raise QuerySemanticError(message)
        if isinstance(expression, Variable):
            return self._evaluator.evaluate(
                expression,
                self._representative(group),
                self._parameters,
            )
        if isinstance(expression, Property):
            target = self.evaluate(expression.target, group)
            return self._evaluator.apply_property(target, expression.key)
        if isinstance(expression, Unary):
            return self._evaluator.apply_unary(
                expression.operator,
                self.evaluate(expression.operand, group),
            )
        if isinstance(expression, Binary):
            return self._evaluator.apply_binary(
                expression.operator,
                self.evaluate(expression.left, group),
                self.evaluate(expression.right, group),
            )
        if isinstance(expression, IsNull):
            return self._evaluator.apply_is_null(
                self.evaluate(expression.operand, group),
                expression.negated,
            )
        message = "cannot evaluate this expression form"
        raise QueryExecutionError(message)

    def _aggregate(
        self,
        expression: FunctionCall,
        group: Sequence[Mapping[str, QueryValue]],
    ) -> QueryValue:
        """Evaluate one aggregate call over a group.

        Parameters
        ----------
        expression : FunctionCall
            Aggregate call.
        group : Sequence[Mapping[str, QueryValue]]
            Input bindings belonging to the group.

        Returns
        -------
        QueryValue
            Aggregate result.
        """
        name = expression.name.lower()
        if len(expression.arguments) == 1 and isinstance(expression.arguments[0], Star):
            return Aggregates.count_rows(len(group))
        argument = expression.arguments[0]
        values = [
            self._evaluator.evaluate(argument, binding, self._parameters) for binding in group
        ]
        return Aggregates.compute(name, values, distinct=expression.distinct)

    @staticmethod
    def _representative(
        group: Sequence[Mapping[str, QueryValue]],
    ) -> Mapping[str, QueryValue]:
        """Return the binding that represents a non-empty group.

        Parameters
        ----------
        group : Sequence[Mapping[str, QueryValue]]
            Input bindings belonging to the group.

        Returns
        -------
        Mapping[str, QueryValue]
            First binding in the group.

        Raises
        ------
        QueryExecutionError
            If the group is empty, so a variable cannot be evaluated.
        """
        if not group:
            message = "variable evaluation requires aggregate input rows"
            raise QueryExecutionError(message)
        return group[0]


@dataclasses.dataclass(frozen=True, slots=True)
class ProjectedRow:
    """One projected row together with the binding that produced it.

    Parameters
    ----------
    binding : Mapping[str, QueryValue]
        Match binding, or the representative binding for an aggregate group.
    values : tuple[QueryValue, ...]
        Projected values in column order.
    """

    binding: Mapping[str, QueryValue]
    values: tuple[QueryValue, ...]


class QueryExecutor:
    """Run planned queries on one SQLite connection.

    Parameters
    ----------
    connection : Connection
        Connection used to execute compiled SQL.
    nodes : NodeRepository
        Repository used to read node snapshots.
    relationships : RelationshipRepository
        Repository used to read relationship snapshots.
    codec : PropertyCodec
        Codec used to decode stored properties.
    database : Database | None, optional
        Database wrapper used for graph-level lifecycle checks, by default
        ``None`` for executors owned by active transactions.
    budget : QueryBudget | None, optional
        Graph-wide default budget, by default the documented defaults.
    """

    def __init__(
        self,
        connection: Connection,
        nodes: NodeRepository,
        relationships: RelationshipRepository,
        codec: PropertyCodec,
        database: Database | None = None,
        budget: QueryBudget | None = None,
    ) -> None:
        self._connection = connection
        self._nodes = nodes
        self._relationships = relationships
        self._codec = codec
        self._database = database
        self._budget = QueryBudget() if budget is None else budget

    def explain(
        self,
        plan: Plan,
        parameters: Mapping[str, QueryValue],
    ) -> tuple[str, ...]:
        """Return the planned access path for a statement without running it.

        Parameters
        ----------
        plan : Plan
            Planned statement.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        tuple[str, ...]
            One detail line per plan row, in plan order.

        Raises
        ------
        QuerySemanticError
            If a referenced parameter is missing.
        QueryExecutionError
            If SQLite cannot plan the statement.
        """
        analysis = plan.analysis
        analysis.require_parameters(parameters)
        if not plan.stages:
            return ()
        snapshots = RepositorySnapshots(self._nodes, self._relationships)
        evaluator = ExpressionEvaluator(ScalarFunctions(snapshots))
        resolver = PatternValueResolver(evaluator, parameters, lenient=True)
        lines: list[str] = []
        for plan_stage in plan.stages:
            lines.extend(self._explain_stage(plan_stage.stage, parameters, resolver))
        return tuple(lines)

    def _explain_stage(
        self,
        stage: MatchStage | OptionalMatchStage | UnwindStage | WithStage | FilterStage,
        parameters: Mapping[str, QueryValue],
        resolver: PatternValueResolver,
    ) -> tuple[str, ...]:
        """Return the planned access path of one read stage.

        Parameters
        ----------
        stage : MatchStage | OptionalMatchStage | UnwindStage | WithStage | FilterStage
            Read stage to inspect.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        resolver : PatternValueResolver
            Lenient evaluator for pattern property expressions.

        Returns
        -------
        tuple[str, ...]
            One detail line per plan row for the stage.

        Raises
        ------
        QueryExecutionError
            If SQLite cannot plan the stage.
        """
        if isinstance(stage, UnwindStage):
            return (f"UNWIND {stage.variable}",)
        if isinstance(stage, WithStage):
            return ()
        if isinstance(stage, FilterStage):
            return ("FILTER",)
        if self._is_quantified(stage.patterns):
            return self._explain_quantified(stage, parameters, resolver)
        match = Match(patterns=stage.patterns, where=stage.where)
        compiled = Compiler(match, self._codec).compile(parameters, resolver=resolver)
        try:
            rows = self._connection.execute(
                f"EXPLAIN QUERY PLAN {compiled.sql}",
                compiled.arguments,
            ).fetchall()
        except sqlite3.Error as error:
            message = "query planning failed"
            raise QueryExecutionError(message) from error
        return tuple(str(row[3]) for row in rows)

    def _explain_quantified(
        self,
        stage: MatchStage | OptionalMatchStage,
        parameters: Mapping[str, QueryValue],
        resolver: PatternValueResolver,
    ) -> tuple[str, ...]:
        """Explain a stage that expands quantified relationships.

        Parameters
        ----------
        stage : MatchStage | OptionalMatchStage
            Stage run by the pattern engine.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        resolver : PatternValueResolver
            Lenient evaluator for pattern property expressions.

        Returns
        -------
        tuple[str, ...]
            Start-node access plans followed by one expansion line.
        """
        lines: list[str] = []
        for pattern in stage.patterns:
            first = pattern.nodes[0]
            synthetic = NodePattern(
                variable="__pygrafito_start",
                labels=first.labels,
                properties=first.properties,
                label_expression=first.label_expression,
            )
            match = Match(patterns=(PathPattern(nodes=(synthetic,)),))
            compiled = Compiler(match, self._codec).compile(parameters, resolver=resolver)
            try:
                rows = self._connection.execute(
                    f"EXPLAIN QUERY PLAN {compiled.sql}",
                    compiled.arguments,
                ).fetchall()
            except sqlite3.Error as error:
                message = "query planning failed"
                raise QueryExecutionError(message) from error
            lines.extend(str(row[3]) for row in rows)
        depth = sum(
            1 if relationship.max_hops is None else relationship.max_hops
            for pattern in stage.patterns
            for relationship in pattern.relationships
        )
        lines.append(f"QUANTIFIED PATTERN max_hops={depth}")
        return tuple(lines)

    def execute_graph(
        self,
        plan: Plan,
        parameters: Mapping[str, QueryValue],
        budget: QueryBudget | None = None,
    ) -> QueryResult:
        """Execute a statement inside its own short transaction.

        Read statements use a deferred transaction; write statements use
        ``BEGIN IMMEDIATE`` so every mutation of the statement commits or rolls
        back as one unit.

        Parameters
        ----------
        plan : Plan
            Planned statement.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        budget : QueryBudget | None, optional
            Budget for this execution, by default the graph default.

        Returns
        -------
        QueryResult
            Materialized result.

        Raises
        ------
        TransactionError
            If the graph handle is closed or an explicit transaction is active.
        QueryExecutionError
            If storage fails while executing the statement.
        """
        selected = self._budget if budget is None else budget
        if self._database is None:
            message = "the executor is not attached to a graph database"
            raise TransactionError(message)
        self._database.ensure_open()
        if plan.analysis.is_write:
            self._database.ensure_writable()
        if self._connection.in_transaction:
            message = "a graph transaction is active; use Transaction.query"
            raise TransactionError(message)
        begin = "BEGIN IMMEDIATE" if plan.analysis.is_write else "BEGIN"
        try:
            self._connection.execute(begin)
        except sqlite3.Error as error:
            message = "could not start a query transaction"
            raise TransactionError(message) from error
        try:
            result = self._execute(plan, parameters, selected)
        except ConstraintViolationError as error:
            self._rollback()
            refreshed = self._refresh_violation(error)
            if refreshed is error:
                raise
            raise refreshed from error
        except QueryError:
            self._rollback()
            raise
        except (ValidationError, NotFoundError, ConnectedNodeError, TransactionError) as error:
            self._rollback()
            raise QueryExecutionError(str(error)) from error
        except sqlite3.Error as error:
            self._rollback()
            message = "query execution failed"
            raise QueryExecutionError(message) from error
        except BaseException:
            self._rollback()
            raise
        try:
            self._connection.execute("COMMIT")
        except sqlite3.Error as error:
            self._rollback()
            message = "could not finish a query transaction"
            raise QueryExecutionError(message) from error
        return result

    def execute_active(
        self,
        plan: Plan,
        parameters: Mapping[str, QueryValue],
        budget: QueryBudget | None = None,
    ) -> QueryResult:
        """Execute a statement on the active transaction's connection.

        A write statement runs inside a savepoint, so a failure undoes only that
        statement's mutations while leaving the caller's transaction usable.

        Parameters
        ----------
        plan : Plan
            Planned statement.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        budget : QueryBudget | None, optional
            Budget for this execution, by default the graph default.

        Returns
        -------
        QueryResult
            Materialized result.

        Raises
        ------
        QueryExecutionError
            If storage fails while executing the statement.
        """
        selected = self._budget if budget is None else budget
        savepoint = plan.analysis.is_write
        if savepoint:
            self._connection.execute("SAVEPOINT pygrafito_statement")
        try:
            result = self._execute(plan, parameters, selected)
        except ConstraintViolationError as error:
            self._release_savepoint(savepoint, rollback=True)
            refreshed = self._refresh_violation(error)
            if refreshed is error:
                raise
            raise refreshed from error
        except QueryError:
            self._release_savepoint(savepoint, rollback=True)
            raise
        except (ValidationError, NotFoundError, ConnectedNodeError, TransactionError) as error:
            self._release_savepoint(savepoint, rollback=True)
            raise QueryExecutionError(str(error)) from error
        except sqlite3.Error as error:
            self._release_savepoint(savepoint, rollback=True)
            message = "query execution failed"
            raise QueryExecutionError(message) from error
        except BaseException:
            self._release_savepoint(savepoint, rollback=True)
            raise
        self._release_savepoint(savepoint, rollback=False)
        return result

    def _refresh_violation(
        self,
        error: ConstraintViolationError,
    ) -> ConstraintViolationError:
        """Recompute the existing holder after a failed statement rolled back.

        The repository translator runs while SQLite has already undone the
        failing SQL statement but before the graph statement rolls back its
        earlier statements. A duplicate created by one of those earlier
        statements therefore looks like a surviving holder until the outer
        rollback. Recomputing afterwards distinguishes a committed holder from
        a duplicate removed with the statement.

        Parameters
        ----------
        error : ConstraintViolationError
            Violation raised while the statement was running.

        Returns
        -------
        ConstraintViolationError
            The same error when the holder survived, otherwise a new error with
            the surviving holder or with none.
        """
        if error.value is None:
            return error
        constraint = Constraint(error.kind, error.scope, error.key)
        existing = ConstraintRegistry(self._connection, self._codec).holder(
            constraint,
            error.value,
        )
        if existing == error.existing:
            return error
        return ConstraintViolationError(
            error.kind,
            error.scope,
            error.key,
            error.value,
            existing,
        )

    def _release_savepoint(self, savepoint: bool, *, rollback: bool) -> None:
        """Finish the statement savepoint used by an active transaction.

        Parameters
        ----------
        savepoint : bool
            Whether a savepoint was opened for this statement.
        rollback : bool
            Whether to roll the savepoint back instead of releasing it.
        """
        if not savepoint:
            return
        statement = (
            "ROLLBACK TO SAVEPOINT pygrafito_statement"
            if rollback
            else "RELEASE SAVEPOINT pygrafito_statement"
        )
        with contextlib.suppress(sqlite3.Error):
            self._connection.execute(statement)
        if rollback:
            with contextlib.suppress(sqlite3.Error):
                self._connection.execute("RELEASE SAVEPOINT pygrafito_statement")

    def _execute(
        self,
        plan: Plan,
        parameters: Mapping[str, QueryValue],
        budget: QueryBudget,
    ) -> QueryResult:
        """Execute one plan and materialize its result.

        Parameters
        ----------
        plan : Plan
            Planned query.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        budget : QueryBudget
            Budget selected for this execution.

        Returns
        -------
        QueryResult
            Materialized result.
        """
        analysis = plan.analysis
        analysis.require_parameters(parameters)
        tracker = BudgetTracker(budget)
        tracker.check_time()
        return_clause = analysis.return_clause
        skip = self._page_value(
            None if return_clause is None else return_clause.skip,
            parameters,
            "SKIP",
        )
        limit = self._page_value(
            None if return_clause is None else return_clause.limit,
            parameters,
            "LIMIT",
        )
        snapshots = RepositorySnapshots(self._nodes, self._relationships)
        functions = ScalarFunctions(snapshots)
        evaluator = ExpressionEvaluator(functions)
        bindings: list[dict[str, QueryValue]] = [{}]
        for plan_stage in plan.stages:
            tracker.check_time()
            bindings = self._run_stage(
                plan_stage.stage,
                bindings,
                evaluator,
                functions,
                parameters,
                tracker,
            )
            tracker.check_time()
        mutations = MutationExecutor(self._nodes, self._relationships)
        if analysis.is_write:
            matcher = functools.partial(
                self._match_merge,
                evaluator=evaluator,
                parameters=parameters,
            )
            bindings = mutations.apply(
                analysis.write_clauses,
                bindings,
                evaluator,
                parameters,
                matcher,
            )
            tracker.consume_rows(len(bindings))
        if return_clause is None:
            return QueryResult(
                columns=(),
                rows=(),
                summary=mutations.summary,
            )
        rows = self._project(
            plan,
            bindings,
            evaluator,
            functions,
            parameters,
        )
        if return_clause.distinct:
            rows = self._distinct(rows)
        if analysis.sorts:
            self._order(rows, analysis.sorts, evaluator, parameters)
        start = 0 if skip is None else skip
        end = None if limit is None else start + limit
        selected = rows[start:end]
        return QueryResult(
            columns=analysis.columns,
            rows=tuple(Row(columns=analysis.columns, row_values=row.values) for row in selected),
            summary=mutations.summary,
        )

    def _run_stage(
        self,
        stage: MatchStage | OptionalMatchStage | UnwindStage | WithStage | FilterStage,
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        functions: ScalarFunctions,
        parameters: Mapping[str, QueryValue],
        tracker: BudgetTracker,
    ) -> list[dict[str, QueryValue]]:
        """Run one read stage over the rows produced by earlier stages.

        Parameters
        ----------
        stage : MatchStage | OptionalMatchStage | WithStage
            Read stage to run.
        bindings : Sequence[Mapping[str, QueryValue]]
            Input rows from earlier stages.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        functions : ScalarFunctions
            Scalar function implementation.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        tracker : BudgetTracker
            Budget counters of this execution.

        Returns
        -------
        list[dict[str, QueryValue]]
            Output rows of the stage.
        """
        if isinstance(stage, MatchStage):
            return self._run_match_stage(stage, bindings, evaluator, parameters, tracker)
        if isinstance(stage, OptionalMatchStage):
            return self._run_optional_match_stage(
                stage,
                bindings,
                evaluator,
                parameters,
                tracker,
            )
        if isinstance(stage, UnwindStage):
            return self._run_unwind_stage(stage, bindings, evaluator, parameters, tracker)
        if isinstance(stage, FilterStage):
            return self._run_filter_stage(stage, bindings, evaluator, parameters, tracker)
        if isinstance(stage, WithStage):
            return self._run_with_stage(
                stage,
                bindings,
                evaluator,
                functions,
                parameters,
                tracker,
            )
        message = f"unsupported read stage: {type(stage).__name__}"
        raise QueryExecutionError(message)

    def _run_unwind_stage(
        self,
        stage: UnwindStage,
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        tracker: BudgetTracker,
    ) -> list[dict[str, QueryValue]]:
        """Expand one list value per input row into output rows.

        Parameters
        ----------
        stage : UnwindStage
            Stage to run.
        bindings : Sequence[Mapping[str, QueryValue]]
            Input rows.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        tracker : BudgetTracker
            Budget counters of this execution.

        Returns
        -------
        list[dict[str, QueryValue]]
            One output row per expanded element, in list order.

        Raises
        ------
        QueryExecutionError
            If the evaluated value is not a list.
        """
        results: list[dict[str, QueryValue]] = []
        for binding in bindings:
            value = evaluator.evaluate(stage.expression, binding, parameters)
            if value is None:
                continue
            if isinstance(value, str) or not isinstance(value, Sequence):
                message = "UNWIND requires a list value"
                raise QueryExecutionError(message)
            for item in value:
                tracker.consume_rows()
                results.append({**binding, stage.variable: item})
        return results

    def _run_match_stage(
        self,
        stage: MatchStage,
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        tracker: BudgetTracker,
    ) -> list[dict[str, QueryValue]]:
        """Run a mandatory match stage.

        Parameters
        ----------
        stage : MatchStage
            Stage to run.
        bindings : Sequence[Mapping[str, QueryValue]]
            Input rows.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        tracker : BudgetTracker
            Budget counters of this execution.

        Returns
        -------
        list[dict[str, QueryValue]]
            One output row per match for every input row.
        """
        results: list[dict[str, QueryValue]] = []
        names = self._pattern_variables(stage.patterns)
        if self._is_quantified(stage.patterns):
            return self._run_pattern_stage(
                stage.patterns,
                stage.where,
                bindings,
                evaluator,
                parameters,
                tracker,
                optional=False,
                introduced=frozenset(),
            )
        for binding in bindings:
            if self._has_null_binding(binding, names):
                continue
            matches = self._match_rows(
                stage.patterns,
                stage.where,
                evaluator,
                parameters,
                binding,
            )
            for match in matches:
                tracker.consume_rows()
                results.append({**binding, **match})
        return results

    def _run_optional_match_stage(
        self,
        stage: OptionalMatchStage,
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        tracker: BudgetTracker,
    ) -> list[dict[str, QueryValue]]:
        """Run an optional match stage as a left join.

        Parameters
        ----------
        stage : OptionalMatchStage
            Stage to run.
        bindings : Sequence[Mapping[str, QueryValue]]
            Input rows.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        tracker : BudgetTracker
            Budget counters of this execution.

        Returns
        -------
        list[dict[str, QueryValue]]
            One output row per match, or the input row with nulls when the
            stage does not match.
        """
        results: list[dict[str, QueryValue]] = []
        names = self._pattern_variables(stage.patterns)
        if self._is_quantified(stage.patterns):
            return self._run_pattern_stage(
                stage.patterns,
                stage.where,
                bindings,
                evaluator,
                parameters,
                tracker,
                optional=True,
                introduced=stage.introduced,
            )
        for binding in bindings:
            if self._has_null_binding(binding, names):
                tracker.consume_rows()
                results.append({**binding, **dict.fromkeys(sorted(stage.introduced))})
                continue
            matches = self._match_rows(
                stage.patterns,
                stage.where,
                evaluator,
                parameters,
                binding,
            )
            if not matches:
                tracker.consume_rows()
                results.append({**binding, **dict.fromkeys(sorted(stage.introduced))})
                continue
            for match in matches:
                tracker.consume_rows()
                results.append({**binding, **match})
        return results

    def _run_filter_stage(
        self,
        stage: FilterStage,
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        tracker: BudgetTracker,
    ) -> list[dict[str, QueryValue]]:
        """Keep only the rows whose predicate is true.

        Parameters
        ----------
        stage : FilterStage
            Stage to run.
        bindings : Sequence[Mapping[str, QueryValue]]
            Input rows.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        tracker : BudgetTracker
            Budget counters of this execution.

        Returns
        -------
        list[dict[str, QueryValue]]
            Rows whose predicate evaluated to ``True``.
        """
        results = [
            dict(binding)
            for binding in bindings
            if evaluator.evaluate(stage.where, binding, parameters) is True
        ]
        tracker.consume_rows(len(results))
        return results

    def _run_with_stage(
        self,
        stage: WithStage,
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        functions: ScalarFunctions,
        parameters: Mapping[str, QueryValue],
        tracker: BudgetTracker,
    ) -> list[dict[str, QueryValue]]:
        """Run a ``WITH`` stage as a row transformer.

        Parameters
        ----------
        stage : WithStage
            Stage to run.
        bindings : Sequence[Mapping[str, QueryValue]]
            Input rows.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        functions : ScalarFunctions
            Scalar function implementation.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        tracker : BudgetTracker
            Budget counters of this execution.

        Returns
        -------
        list[dict[str, QueryValue]]
            Rows projected into the stage's output scope.
        """
        if stage.has_aggregates:
            aggregate_rows = self._aggregate_project(
                stage.items,
                stage.grouping,
                bindings,
                evaluator,
                functions,
                parameters,
            )
            rows = [
                ProjectedRow(
                    binding={
                        item.name: value
                        for item, value in zip(stage.items, row.values, strict=True)
                    },
                    values=row.values,
                )
                for row in aggregate_rows
            ]
        else:
            rows = []
            for binding in bindings:
                values = tuple(
                    evaluator.evaluate(item.expression, binding, parameters) for item in stage.items
                )
                rows.append(
                    ProjectedRow(
                        binding={
                            item.name: value
                            for item, value in zip(stage.items, values, strict=True)
                        },
                        values=values,
                    )
                )
        if stage.where is not None:
            rows = [
                row
                for row in rows
                if evaluator.evaluate(stage.where, row.binding, parameters) is True
            ]
        if stage.distinct:
            rows = self._distinct(rows)
        if stage.order_by:
            self._order(rows, stage.order_by, evaluator, parameters)
        skip = self._page_value(stage.skip, parameters, "SKIP")
        limit = self._page_value(stage.limit, parameters, "LIMIT")
        start = 0 if skip is None else skip
        end = None if limit is None else start + limit
        selected = [dict(row.binding) for row in rows[start:end]]
        tracker.consume_rows(len(selected))
        return selected

    def _run_pattern_stage(
        self,
        patterns: Sequence[PathPattern],
        where: Expression | None,
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        tracker: BudgetTracker,
        *,
        optional: bool,
        introduced: frozenset[str],
    ) -> list[dict[str, QueryValue]]:
        """Run a match stage that contains a quantified relationship.

        Parameters
        ----------
        patterns : Sequence[PathPattern]
            Patterns of the stage.
        where : Expression | None
            Stage filter, or ``None``.
        bindings : Sequence[Mapping[str, QueryValue]]
            Input rows.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        tracker : BudgetTracker
            Budget counters of this execution.
        optional : bool
            Whether the stage is ``OPTIONAL MATCH``.
        introduced : frozenset[str]
            Variables to null when an optional stage does not match.

        Returns
        -------
        list[dict[str, QueryValue]]
            One output row per match, or one null-extended row per input for
            an optional stage without matches.
        """
        engine = PatternEngine(
            self._nodes,
            self._relationships,
            self._select_start_nodes,
            parameters,
            evaluator,
            tracker,
        )
        names = self._pattern_variables(patterns)
        results: list[dict[str, QueryValue]] = []
        for binding in bindings:
            if self._has_null_binding(binding, names):
                if optional:
                    tracker.consume_rows()
                    results.append({**binding, **dict.fromkeys(sorted(introduced))})
                continue
            matches = engine.match(patterns, where, binding)
            if optional and not matches:
                tracker.consume_rows()
                results.append({**binding, **dict.fromkeys(sorted(introduced))})
                continue
            results.extend({**binding, **match} for match in matches)
        return results

    def _select_start_nodes(
        self,
        pattern: NodePattern,
        parameters: Mapping[str, QueryValue],
        evaluator: ExpressionEvaluator,
        binding: Mapping[str, QueryValue],
    ) -> list[Node]:
        """Return candidate start nodes using the indexed node predicates.

        Parameters
        ----------
        pattern : NodePattern
            First node pattern of a path.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        binding : Mapping[str, QueryValue]
            Variables bound before the pattern.

        Returns
        -------
        list[Node]
            Nodes matching the labels and property map.
        """
        synthetic = NodePattern(
            variable="__pygrafito_start",
            labels=pattern.labels,
            properties=pattern.properties,
            label_expression=pattern.label_expression,
        )
        match = Match(patterns=(PathPattern(nodes=(synthetic,)),))
        resolver = PatternValueResolver(evaluator, parameters)
        compiled = Compiler(match, self._codec).compile(parameters, binding, resolver)
        nodes: list[Node] = []
        for row in self._match_bindings(compiled):
            node = row.get("__pygrafito_start")
            if isinstance(node, Node):
                nodes.append(node)
        return nodes

    @staticmethod
    def _is_quantified(patterns: Sequence[PathPattern]) -> bool:
        """Report whether a pattern set contains a quantified relationship.

        Parameters
        ----------
        patterns : Sequence[PathPattern]
            Patterns to inspect.

        Returns
        -------
        bool
            ``True`` when any relationship carries a hop bound.
        """
        return any(
            relationship.min_hops is not None or relationship.max_hops is not None
            for pattern in patterns
            for relationship in pattern.relationships
        )

    @staticmethod
    def _pattern_variables(patterns: Sequence[PathPattern]) -> set[str]:
        """Return every variable referenced by a pattern set.

        Parameters
        ----------
        patterns : Sequence[PathPattern]
            Patterns to inspect.

        Returns
        -------
        set[str]
            Variable names the patterns reference.
        """
        names: set[str] = set()
        for pattern in patterns:
            if pattern.variable is not None:
                names.add(pattern.variable)
            for node in pattern.nodes:
                if node.variable is not None:
                    names.add(node.variable)
            for relationship in pattern.relationships:
                if relationship.variable is not None:
                    names.add(relationship.variable)
        return names

    @staticmethod
    def _has_null_binding(
        binding: Mapping[str, QueryValue],
        names: set[str],
    ) -> bool:
        """Report whether a pattern references a variable bound to null.

        Parameters
        ----------
        binding : Mapping[str, QueryValue]
            Input row.
        names : set[str]
            Variables referenced by the pattern.

        Returns
        -------
        bool
            ``True`` when a referenced variable is present and null.
        """
        return any(name in binding and binding[name] is None for name in names)

    def _match_merge(
        self,
        pattern: PathPattern,
        binding: Mapping[str, QueryValue],
        *,
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> list[dict[str, QueryValue]]:
        """Match one pattern for a ``MERGE`` input row.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to match as a whole.
        binding : Mapping[str, QueryValue]
            Variables bound by earlier stages.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        list[dict[str, QueryValue]]
            One binding per match, or an empty list when the pattern is absent.
        """
        return self._match_rows([pattern], None, evaluator, parameters, binding)

    def _match_rows(
        self,
        patterns: Sequence[PathPattern],
        where: Expression | None,
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        bound: Mapping[str, QueryValue] | None = None,
    ) -> list[dict[str, QueryValue]]:
        """Run one pattern set and return its filtered variable bindings.

        Parameters
        ----------
        patterns : Sequence[PathPattern]
            Path patterns to match as one stage.
        where : Expression | None
            Filter attached to the pattern set, or ``None``.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        bound : Mapping[str, QueryValue] | None, optional
            Values already bound by an earlier stage, by default none.

        Returns
        -------
        list[dict[str, QueryValue]]
            Variable bindings in SQL row order.
        """
        match = Match(patterns=tuple(patterns), where=where)
        resolver = PatternValueResolver(evaluator, parameters)
        compiled = Compiler(match, self._codec).compile(parameters, bound, resolver)
        bindings = self._match_bindings(compiled)
        if compiled.residual is None:
            return bindings
        residual = compiled.residual
        filtered: list[dict[str, QueryValue]] = []
        for binding in bindings:
            scope: Mapping[str, QueryValue] = binding if bound is None else {**bound, **binding}
            if evaluator.evaluate(residual, scope, parameters) is True:
                filtered.append(binding)
        return filtered

    def _match_bindings(self, compiled: CompiledMatch) -> list[dict[str, QueryValue]]:
        """Run the match SQL and build one variable binding per row.

        Parameters
        ----------
        compiled : CompiledMatch
            Compiled match query.

        Returns
        -------
        list[dict[str, QueryValue]]
            Variable bindings in SQL row order.
        """
        cursor = self._connection.execute(compiled.sql, compiled.arguments)
        names = [description[0] for description in cursor.description or ()]
        positions = {name: index for index, name in enumerate(names)}
        records = cursor.fetchall()
        node_ids = {
            typing.cast(int, record[positions[column.column]])
            for record in records
            for column in compiled.node_columns
        }
        nodes_by_id = self._nodes.get_many(node_ids)
        relationship_cache: dict[int, Relationship] = {}
        bindings: list[dict[str, QueryValue]] = []
        for record in records:
            binding: dict[str, QueryValue] = {}
            for column in compiled.node_columns:
                if column.variable is None:
                    continue
                binding[column.variable] = self._node(
                    record,
                    positions,
                    column,
                    nodes_by_id,
                )
            for columns in compiled.relationship_columns:
                relationship = self._relationship(
                    record,
                    positions,
                    columns,
                    relationship_cache,
                )
                if columns.variable is not None:
                    binding[columns.variable] = relationship
            for path in compiled.paths:
                nodes = tuple(
                    self._node_by_column(record, positions, column, nodes_by_id)
                    for column in path.nodes
                )
                relationships = tuple(
                    self._relationship(
                        record,
                        positions,
                        columns,
                        relationship_cache,
                    )
                    for columns in path.relationships
                )
                binding[path.variable] = Path(nodes=nodes, relationships=relationships)
            bindings.append(binding)
        return bindings

    @staticmethod
    def _node(
        record: Sequence[object],
        positions: Mapping[str, int],
        column: NodeColumn,
        nodes_by_id: Mapping[int, Node],
    ) -> Node:
        """Read one node snapshot selected by a column.

        Parameters
        ----------
        record : Sequence[object]
            SQL row.
        positions : Mapping[str, int]
            Column name to index mapping.
        column : NodeColumn
            Node selection.
        nodes_by_id : Mapping[int, Node]
            Batch-loaded node snapshots.

        Returns
        -------
        Node
            Selected node snapshot.
        """
        node_id = typing.cast(int, record[positions[column.column]])
        node = nodes_by_id.get(node_id)
        if node is None:
            message = f"node {node_id} disappeared during query execution"
            raise QueryExecutionError(message)
        return node

    @classmethod
    def _node_by_column(
        cls,
        record: Sequence[object],
        positions: Mapping[str, int],
        column: str,
        nodes_by_id: Mapping[int, Node],
    ) -> Node:
        """Read one node snapshot selected for a path.

        Parameters
        ----------
        record : Sequence[object]
            SQL row.
        positions : Mapping[str, int]
            Column name to index mapping.
        column : str
            Column alias holding the node id.
        nodes_by_id : Mapping[int, Node]
            Batch-loaded node snapshots.

        Returns
        -------
        Node
            Selected node snapshot.
        """
        return cls._node(
            record,
            positions,
            NodeColumn(column=column, variable=None),
            nodes_by_id,
        )

    def _relationship(
        self,
        record: Sequence[object],
        positions: Mapping[str, int],
        columns: RelationshipColumns,
        cache: dict[int, Relationship],
    ) -> Relationship:
        """Decode one relationship selection.

        Parameters
        ----------
        record : Sequence[object]
            SQL row.
        positions : Mapping[str, int]
            Column name to index mapping.
        columns : RelationshipColumns
            Relationship selections.
        cache : dict[int, Relationship]
            Decoded relationships already seen in this execution.

        Returns
        -------
        Relationship
            Decoded relationship snapshot.
        """
        relationship_id = typing.cast(int, record[positions[columns.id]])
        cached = cache.get(relationship_id)
        if cached is not None:
            return cached
        try:
            properties = self._codec.decode_properties(str(record[positions[columns.props]]))
        except ValidationError as error:
            message = "stored relationship properties are not valid"
            raise QueryExecutionError(message) from error
        labels = json.loads(str(record[positions[columns.labels]]))
        relationship = Relationship(
            id=relationship_id,
            start_id=typing.cast(int, record[positions[columns.src]]),
            end_id=typing.cast(int, record[positions[columns.dst]]),
            labels=tuple(str(label) for label in labels),
            directed=bool(record[positions[columns.directed]]),
            properties=properties,
        )
        cache[relationship_id] = relationship
        return relationship

    def _project(
        self,
        plan: Plan,
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        functions: ScalarFunctions,
        parameters: Mapping[str, QueryValue],
    ) -> list[ProjectedRow]:
        """Project matched bindings, optionally with aggregation.

        Parameters
        ----------
        plan : Plan
            Planned query.
        bindings : Sequence[Mapping[str, QueryValue]]
            Filtered match bindings.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        functions : ScalarFunctions
            Scalar function implementation.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        list[ProjectedRow]
            Projected rows before distinct, ordering, and pagination.
        """
        analysis = plan.analysis
        if analysis.has_aggregates:
            return self._aggregate_project(
                analysis.items,
                analysis.grouping,
                bindings,
                evaluator,
                functions,
                parameters,
            )
        rows: list[ProjectedRow] = []
        for binding in bindings:
            values = tuple(
                evaluator.evaluate(item.expression, binding, parameters) for item in analysis.items
            )
            rows.append(ProjectedRow(binding=binding, values=values))
        return rows

    def _aggregate_project(
        self,
        items: Sequence[ReturnColumn],
        grouping: Sequence[Expression],
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        functions: ScalarFunctions,
        parameters: Mapping[str, QueryValue],
    ) -> list[ProjectedRow]:
        """Group bindings and evaluate aggregate projections.

        Parameters
        ----------
        items : Sequence[ReturnColumn]
            Analysed projection columns.
        grouping : Sequence[Expression]
            Implicit grouping-key expressions.
        bindings : Sequence[Mapping[str, QueryValue]]
            Filtered match bindings.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        functions : ScalarFunctions
            Scalar function implementation.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        list[ProjectedRow]
            One projected row per group, or one empty-group row for ungrouped
            aggregates.
        """
        groups = self._groups(grouping, bindings, evaluator, parameters)
        group_evaluator = GroupEvaluator(evaluator, functions, parameters)
        rows: list[ProjectedRow] = []
        for group in groups:
            values = tuple(group_evaluator.evaluate(item.expression, group) for item in items)
            representative = group[0] if group else {}
            rows.append(ProjectedRow(binding=representative, values=values))
        return rows

    @staticmethod
    def _groups(
        grouping: Sequence[Expression],
        bindings: Sequence[Mapping[str, QueryValue]],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> list[list[Mapping[str, QueryValue]]]:
        """Group input bindings by their implicit grouping keys.

        Parameters
        ----------
        grouping : Sequence[Expression]
            Implicit grouping-key expressions.
        bindings : Sequence[Mapping[str, QueryValue]]
            Filtered match bindings.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        list[list[Mapping[str, QueryValue]]]
            Groups in first-seen order; ungrouped aggregates always produce one
            group, even for empty input.
        """
        if not grouping:
            return [list(bindings)]
        groups: dict[tuple[ValueKey, ...], list[Mapping[str, QueryValue]]] = {}
        for binding in bindings:
            key = tuple(
                ValueKey(evaluator.evaluate(expression, binding, parameters))
                for expression in grouping
            )
            groups.setdefault(key, []).append(binding)
        return list(groups.values())

    @staticmethod
    def _distinct(rows: Sequence[ProjectedRow]) -> list[ProjectedRow]:
        """Remove duplicate projected rows.

        Parameters
        ----------
        rows : Sequence[ProjectedRow]
            Projected rows.

        Returns
        -------
        list[ProjectedRow]
            Rows in first-seen order without duplicate projected values.
        """
        seen: set[tuple[ValueKey, ...]] = set()
        result: list[ProjectedRow] = []
        for row in rows:
            key = tuple(ValueKey(value) for value in row.values)
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    @staticmethod
    def _order(
        rows: list[ProjectedRow],
        sorts: Sequence[SortSpec],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> None:
        """Sort projected rows by their resolved ordering keys.

        Parameters
        ----------
        rows : list[ProjectedRow]
            Rows to sort in place.
        sorts : Sequence[SortSpec]
            Resolved ordering keys in significance order.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        """
        for sort in reversed(sorts):
            rows.sort(
                key=lambda row, current=sort: Values.ordering_key(
                    QueryExecutor._sort_value(
                        row,
                        current.column,
                        current.expression,
                        evaluator,
                        parameters,
                    ),
                    descending=current.descending,
                    nulls_first=current.nulls_first,
                ),
                reverse=sort.descending,
            )

    @staticmethod
    def _sort_value(
        row: ProjectedRow,
        column: int | None,
        expression: Expression | None,
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> QueryValue:
        """Return one ordering value for a projected row.

        Parameters
        ----------
        row : ProjectedRow
            Row being ordered.
        column : int | None
            Projected column index, when the key resolves to a column.
        expression : Expression | None
            Expression evaluated against the binding.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        QueryValue
            Value used for ordering.
        """
        if column is not None:
            return row.values[column]
        if expression is not None:
            return evaluator.evaluate(expression, row.binding, parameters)
        message = "ordering key has no expression"
        raise QueryExecutionError(message)

    @staticmethod
    def _page_value(
        expression: Expression | None,
        parameters: Mapping[str, QueryValue],
        clause: str,
    ) -> int | None:
        """Resolve and validate one ``SKIP`` or ``LIMIT`` value.

        Parameters
        ----------
        expression : Expression | None
            Parsed pagination expression.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        clause : str
            Clause name used in error messages.

        Returns
        -------
        int | None
            Validated non-negative integer, or ``None`` when absent.

        Raises
        ------
        QuerySemanticError
            If the value is missing, negative, or not an integer.
        """
        if expression is None:
            return None
        if isinstance(expression, Literal):
            value = expression.value
        elif isinstance(expression, Parameter):
            if expression.name not in parameters:
                message = f"missing query parameter ${expression.name}"
                raise QuerySemanticError(message)
            value = parameters[expression.name]
        else:
            message = f"{clause} must be a non-negative integer or a parameter"
            raise QuerySemanticError(message)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        message = f"{clause} must be a non-negative integer or a parameter"
        raise QuerySemanticError(message)

    def _rollback(self) -> None:
        """Roll back the read transaction when one is still open."""
        if self._connection.in_transaction:
            with contextlib.suppress(sqlite3.Error):
                self._connection.execute("ROLLBACK")
