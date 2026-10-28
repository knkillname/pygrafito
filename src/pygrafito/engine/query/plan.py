# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Logical and physical planning for query execution."""

import dataclasses
import typing

from pygrafito.engine.query.ast import (
    Binary,
    Create,
    Delete,
    MatchMode,
    Merge,
    Operators,
    Remove,
    Set,
)
from pygrafito.engine.query.semantic import (
    Analysis,
    CompoundAnalysis,
    FilterStage,
    LetStage,
    MatchStage,
    NextBoundary,
    OptionalMatchStage,
    ReadStage,
    UnwindStage,
    WithStage,
    WriteStage,
    YieldStage,
)


class PlanOperator:
    """Constants naming one operator in the physical plan pipeline."""

    MATCH: str = "match"
    OPTIONAL_MATCH: str = "optional_match"
    PATH_SEARCH: str = "path_search"
    GROUP: str = "group"
    DIFFERENT_EDGES: str = "different_edges"
    UNWIND: str = "unwind"
    FILTER: str = "filter"
    LET: str = "let"
    YIELD: str = "yield"
    NEXT: str = "next"
    FINISH: str = "finish"
    CREATE: str = "create"
    MERGE: str = "merge"
    SET: str = "set"
    REMOVE: str = "remove"
    DELETE: str = "delete"
    WITH: str = "with"
    RETURN: str = "return"
    PROJECT: str = "project"
    AGGREGATE: str = "aggregate"
    DISTINCT: str = "distinct"
    ORDER: str = "order"
    SKIP: str = "skip"
    LIMIT: str = "limit"


@dataclasses.dataclass(frozen=True, slots=True)
class PlanStage:
    """One planned read stage.

    Parameters
    ----------
    stage : ReadStage
        Analysed stage this plan entry executes.
    operators : tuple[str, ...]
        Operators the stage applies, in execution order.
    """

    stage: ReadStage
    operators: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class PlanEntry:
    """One entry in the ordered operation pipeline.

    Parameters
    ----------
    operation : ReadStage | WriteStage | NextBoundary
        Operation this entry executes.
    operators : tuple[str, ...]
        Operators the entry applies, in execution order.
    """

    operation: ReadStage | WriteStage | NextBoundary
    operators: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Plan:
    """Planned operator pipeline for one analysed statement.

    Parameters
    ----------
    analysis : Analysis
        Static analysis that drives the operators.
    entries : tuple[PlanEntry, ...]
        Ordered operations, including write stages and segment boundaries.
    return_operators : tuple[str, ...]
        Operators applied by the final ``RETURN`` or ``FINISH`` clause.
    """

    analysis: Analysis
    entries: tuple[PlanEntry, ...]
    return_operators: tuple[str, ...] = ()

    @property
    def stages(self) -> tuple[PlanStage, ...]:
        """Return the planned read stages.

        Returns
        -------
        tuple[PlanStage, ...]
            Read-stage entries in execution order.
        """
        return tuple(
            PlanStage(stage=entry.operation, operators=entry.operators)
            for entry in self.entries
            if isinstance(
                entry.operation,
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

    @property
    def write_operators(self) -> tuple[str, ...]:
        """Return the write operators in execution order.

        Returns
        -------
        tuple[str, ...]
            One operator per write stage.
        """
        return tuple(
            operator
            for entry in self.entries
            if isinstance(entry.operation, WriteStage)
            for operator in entry.operators
        )

    @property
    def operators(self) -> tuple[str, ...]:
        """Return the flattened operator sequence.

        Returns
        -------
        tuple[str, ...]
            Entry operators followed by the final result operators.
        """
        return (
            tuple(operator for entry in self.entries for operator in entry.operators)
            + self.return_operators
        )

    def includes(self, operator: str) -> bool:
        """Report whether the plan contains an operator.

        Parameters
        ----------
        operator : str
            Operator to look for.

        Returns
        -------
        bool
            ``True`` when the operator is part of the pipeline.
        """
        return operator in self.operators


@dataclasses.dataclass(frozen=True, slots=True)
class CompoundPlan:
    """Planned set-operation pipeline for one compound analysis.

    Parameters
    ----------
    analysis : CompoundAnalysis
        Static analysis that drives the compound.
    terms : tuple[Plan, ...]
        Planned linear operands in source order.
    """

    analysis: CompoundAnalysis
    terms: tuple[Plan, ...]

    @property
    def operators(self) -> tuple[str, ...]:
        """Return the set operators and projection operators.

        Returns
        -------
        tuple[str, ...]
            Set operators between operands followed by the compound
            projection pipeline.
        """
        operators: list[str] = [self.analysis.operators[0].value]
        for operator in self.analysis.operators[1:]:
            operators.append(operator.value)
        return tuple(operators)


type PlannedStatement = Plan | CompoundPlan


class PlanBuilder:
    """Build the operator pipeline from a static analysis."""

    _MUTATIONS: typing.ClassVar[dict[type[object], str]] = {
        Create: PlanOperator.CREATE,
        Merge: PlanOperator.MERGE,
        Set: PlanOperator.SET,
        Remove: PlanOperator.REMOVE,
        Delete: PlanOperator.DELETE,
    }

    @classmethod
    def build(cls, analysis: Analysis | CompoundAnalysis) -> PlannedStatement:
        """Build the physical plan for an analysed statement.

        Parameters
        ----------
        analysis : Analysis | CompoundAnalysis
            Static analysis of the statement.

        Returns
        -------
        PlannedStatement
            Ordered operations and final projection operators.
        """
        if isinstance(analysis, CompoundAnalysis):
            return CompoundPlan(
                analysis=analysis,
                terms=tuple(typing.cast(Plan, cls.build(term)) for term in analysis.terms),
            )
        entries = cls._build_entries(analysis.operations)
        return_operators = (
            (PlanOperator.FINISH,) if analysis.finish else cls._return_operators(analysis)
        )
        return Plan(
            analysis=analysis,
            entries=entries,
            return_operators=return_operators,
        )

    @classmethod
    def _build_entries(
        cls,
        operations: tuple[ReadStage | WriteStage | NextBoundary, ...],
    ) -> tuple[PlanEntry, ...]:
        """Fuse adjacent mandatory matches and plan every operation.

        Parameters
        ----------
        operations : tuple[ReadStage | WriteStage | NextBoundary, ...]
            Analysed operations in source order.

        Returns
        -------
        tuple[PlanEntry, ...]
            Planned operation entries.
        """
        entries: list[PlanEntry] = []
        pending: MatchStage | None = None
        for operation in operations:
            if isinstance(operation, MatchStage):
                if pending is not None and cls._separate_clauses(pending, operation):
                    entries.append(cls._entry(pending))
                    pending = None
                pending = cls._merge_match(pending, operation)
                continue
            if pending is not None:
                entries.append(cls._entry(pending))
                pending = None
            entries.append(cls._entry(operation))
        if pending is not None:
            entries.append(cls._entry(pending))
        return tuple(entries)

    @staticmethod
    def _separate_clauses(left: MatchStage, right: MatchStage) -> bool:
        """Report whether two match stages must stay separate clauses.

        Parameters
        ----------
        left : MatchStage
            Pending stage.
        right : MatchStage
            Stage to append.

        Returns
        -------
        bool
            ``True`` when either clause enforces ``DIFFERENT EDGES``, whose
            scope must not cross the clause boundary.
        """
        return (
            left.match_mode is MatchMode.DIFFERENT_EDGES
            or right.match_mode is MatchMode.DIFFERENT_EDGES
        )

    @classmethod
    def _merge_match(cls, left: MatchStage | None, right: MatchStage) -> MatchStage:
        """Fuse one mandatory match stage into the pending one.

        Parameters
        ----------
        left : MatchStage | None
            Pending stage, or ``None`` when this is the first match.
        right : MatchStage
            Stage to append.

        Returns
        -------
        MatchStage
            Stage containing both pattern sets and both filters.
        """
        if left is None:
            return right
        where = left.where
        if right.where is not None:
            where = (
                right.where
                if where is None
                else Binary(left=where, operator=Operators.AND, right=right.where)
            )
        return MatchStage(
            patterns=left.patterns + right.patterns,
            where=where,
            match_mode=left.match_mode,
        )

    @classmethod
    def _entry(cls, operation: ReadStage | WriteStage | NextBoundary) -> PlanEntry:
        """Build the operators for one operation.

        Parameters
        ----------
        operation : ReadStage | WriteStage | NextBoundary
            Operation to plan.

        Returns
        -------
        PlanEntry
            Planned operation.
        """
        if isinstance(operation, NextBoundary):
            return PlanEntry(operation=operation, operators=(PlanOperator.NEXT,))
        if isinstance(operation, WriteStage):
            operator = cls._MUTATIONS[type(operation.clause)]
            return PlanEntry(operation=operation, operators=(operator,))
        return PlanEntry(operation=operation, operators=cls._stage_operators(operation))

    @classmethod
    def _stage_operators(cls, stage: ReadStage) -> tuple[str, ...]:
        """Build the operators for one read stage.

        Parameters
        ----------
        stage : ReadStage
            Analysed read stage.

        Returns
        -------
        tuple[str, ...]
            Operators the stage applies.
        """
        operators: list[str] = []
        if isinstance(stage, MatchStage):
            operators.append(PlanOperator.MATCH)
            if any(pattern.search is not None for pattern in stage.patterns):
                operators.append(PlanOperator.PATH_SEARCH)
            if any(not pattern.is_simple for pattern in stage.patterns):
                operators.append(PlanOperator.GROUP)
            if stage.match_mode is MatchMode.DIFFERENT_EDGES:
                operators.append(PlanOperator.DIFFERENT_EDGES)
            if stage.where is not None:
                operators.append(PlanOperator.FILTER)
        elif isinstance(stage, OptionalMatchStage):
            operators.append(PlanOperator.OPTIONAL_MATCH)
            if any(pattern.search is not None for pattern in stage.patterns):
                operators.append(PlanOperator.PATH_SEARCH)
            if any(not pattern.is_simple for pattern in stage.patterns):
                operators.append(PlanOperator.GROUP)
            if stage.match_mode is MatchMode.DIFFERENT_EDGES:
                operators.append(PlanOperator.DIFFERENT_EDGES)
            if stage.where is not None:
                operators.append(PlanOperator.FILTER)
        elif isinstance(stage, UnwindStage):
            operators.append(PlanOperator.UNWIND)
        elif isinstance(stage, FilterStage):
            operators.append(PlanOperator.FILTER)
        elif isinstance(stage, LetStage):
            operators.append(PlanOperator.LET)
        elif isinstance(stage, YieldStage):
            operators.append(PlanOperator.YIELD)
        elif isinstance(stage, WithStage):
            operators.append(PlanOperator.RETURN if stage.segment_return else PlanOperator.WITH)
            operators.append(PlanOperator.PROJECT)
            if stage.has_aggregates or stage.grouping_explicit:
                operators.append(PlanOperator.AGGREGATE)
            if stage.distinct:
                operators.append(PlanOperator.DISTINCT)
            if stage.order_by:
                operators.append(PlanOperator.ORDER)
            if stage.skip is not None:
                operators.append(PlanOperator.SKIP)
            if stage.limit is not None:
                operators.append(PlanOperator.LIMIT)
        return tuple(operators)

    @classmethod
    def _return_operators(cls, analysis: Analysis) -> tuple[str, ...]:
        """Build the operators of the final ``RETURN`` clause.

        Parameters
        ----------
        analysis : Analysis
            Static analysis of the statement.

        Returns
        -------
        tuple[str, ...]
            Projection, aggregation, distinct, ordering, and pagination
            operators in execution order.
        """
        return_clause = analysis.return_clause
        if return_clause is None:
            return ()
        operators: list[str] = [PlanOperator.PROJECT]
        if analysis.has_aggregates or analysis.grouping_explicit:
            operators.append(PlanOperator.AGGREGATE)
        if return_clause.distinct:
            operators.append(PlanOperator.DISTINCT)
        if analysis.sorts:
            operators.append(PlanOperator.ORDER)
        if return_clause.skip is not None:
            operators.append(PlanOperator.SKIP)
        if return_clause.limit is not None:
            operators.append(PlanOperator.LIMIT)
        return tuple(operators)


__all__ = [
    "CompoundPlan",
    "Plan",
    "PlanBuilder",
    "PlanEntry",
    "PlanOperator",
    "PlanStage",
    "PlannedStatement",
]
