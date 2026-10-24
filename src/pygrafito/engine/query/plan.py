# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Logical and physical planning for query execution."""

import dataclasses
import typing

from pygrafito.engine.query.ast import Binary, Create, Delete, Operators, Remove, Set
from pygrafito.engine.query.semantic import (
    Analysis,
    MatchStage,
    OptionalMatchStage,
    ReadStage,
    WithStage,
)


class PlanOperator:
    """Constants naming one operator in the physical plan pipeline."""

    MATCH: str = "match"
    OPTIONAL_MATCH: str = "optional_match"
    FILTER: str = "filter"
    CREATE: str = "create"
    SET: str = "set"
    REMOVE: str = "remove"
    DELETE: str = "delete"
    WITH: str = "with"
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
class Plan:
    """Planned operator pipeline for one analysed statement.

    Parameters
    ----------
    analysis : Analysis
        Static analysis that drives the operators.
    stages : tuple[PlanStage, ...]
        Read stages in execution order.
    write_operators : tuple[str, ...]
        Operators applied after every read stage, in source order.
    return_operators : tuple[str, ...]
        Operators applied by the final ``RETURN`` clause.
    """

    analysis: Analysis
    stages: tuple[PlanStage, ...]
    write_operators: tuple[str, ...] = ()
    return_operators: tuple[str, ...] = ()

    @property
    def operators(self) -> tuple[str, ...]:
        """Return the flattened operator sequence.

        Returns
        -------
        tuple[str, ...]
            Stage operators followed by write and return operators.
        """
        stage_operators = tuple(operator for stage in self.stages for operator in stage.operators)
        return stage_operators + self.write_operators + self.return_operators

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


class PlanBuilder:
    """Build the operator pipeline from a static analysis."""

    _MUTATIONS: typing.ClassVar[dict[type[object], str]] = {
        Create: PlanOperator.CREATE,
        Set: PlanOperator.SET,
        Remove: PlanOperator.REMOVE,
        Delete: PlanOperator.DELETE,
    }

    @classmethod
    def build(cls, analysis: Analysis) -> Plan:
        """Build the physical plan for an analysed statement.

        Parameters
        ----------
        analysis : Analysis
            Static analysis of the statement.

        Returns
        -------
        Plan
            Read stages, trailing write operators, and final projection
            operators.
        """
        stages = cls._build_stages(analysis.stages)
        write_operators = tuple(
            operator
            for clause in analysis.write_clauses
            if (operator := cls._MUTATIONS.get(type(clause))) is not None
        )
        return_operators = cls._return_operators(analysis)
        return Plan(
            analysis=analysis,
            stages=stages,
            write_operators=write_operators,
            return_operators=return_operators,
        )

    @classmethod
    def _build_stages(cls, stages: tuple[ReadStage, ...]) -> tuple[PlanStage, ...]:
        """Fuse adjacent mandatory matches and plan every read stage.

        Parameters
        ----------
        stages : tuple[ReadStage, ...]
            Analysed read stages in source order.

        Returns
        -------
        tuple[PlanStage, ...]
            Planned read stages.
        """
        planned: list[PlanStage] = []
        pending: MatchStage | None = None
        for stage in stages:
            if isinstance(stage, MatchStage):
                pending = cls._merge_match(pending, stage)
                continue
            if pending is not None:
                planned.append(cls._stage(pending))
                pending = None
            planned.append(cls._stage(stage))
        if pending is not None:
            planned.append(cls._stage(pending))
        return tuple(planned)

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
        return MatchStage(patterns=left.patterns + right.patterns, where=where)

    @classmethod
    def _stage(cls, stage: ReadStage) -> PlanStage:
        """Build the operators for one read stage.

        Parameters
        ----------
        stage : ReadStage
            Analysed read stage.

        Returns
        -------
        PlanStage
            Planned read stage.
        """
        operators: list[str] = []
        if isinstance(stage, MatchStage):
            operators.append(PlanOperator.MATCH)
            if stage.where is not None:
                operators.append(PlanOperator.FILTER)
        elif isinstance(stage, OptionalMatchStage):
            operators.append(PlanOperator.OPTIONAL_MATCH)
            if stage.where is not None:
                operators.append(PlanOperator.FILTER)
        elif isinstance(stage, WithStage):
            operators.append(PlanOperator.WITH)
            operators.append(PlanOperator.PROJECT)
            if stage.has_aggregates:
                operators.append(PlanOperator.AGGREGATE)
            if stage.distinct:
                operators.append(PlanOperator.DISTINCT)
            if stage.order_by:
                operators.append(PlanOperator.ORDER)
            if stage.skip is not None:
                operators.append(PlanOperator.SKIP)
            if stage.limit is not None:
                operators.append(PlanOperator.LIMIT)
        return PlanStage(stage=stage, operators=tuple(operators))

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
        if analysis.has_aggregates:
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
    "Plan",
    "PlanBuilder",
    "PlanOperator",
    "PlanStage",
]
