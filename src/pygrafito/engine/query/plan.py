# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Logical and physical planning for query execution."""

import dataclasses
from enum import Enum

from pygrafito.engine.query.semantic import Analysis


class PlanOperator(Enum):
    """One operator in the physical plan pipeline."""

    MATCH = "match"
    FILTER = "filter"
    PROJECT = "project"
    AGGREGATE = "aggregate"
    DISTINCT = "distinct"
    ORDER = "order"
    SKIP = "skip"
    LIMIT = "limit"


@dataclasses.dataclass(frozen=True, slots=True)
class Plan:
    """Planned operator pipeline for one analysed statement.

    Parameters
    ----------
    analysis : Analysis
        Static analysis that drives the operators.
    operators : tuple[PlanOperator, ...]
        Operators in execution order.
    """

    analysis: Analysis
    operators: tuple[PlanOperator, ...]

    def includes(self, operator: PlanOperator) -> bool:
        """Report whether the plan contains an operator.

        Parameters
        ----------
        operator : PlanOperator
            Operator to look for.

        Returns
        -------
        bool
            ``True`` when the operator is part of the pipeline.
        """
        return operator in self.operators


class PlanBuilder:
    """Build the operator pipeline from a static analysis."""

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
            Operator pipeline from match to pagination.
        """
        operators: list[PlanOperator] = [PlanOperator.MATCH]
        if analysis.statement.where is not None:
            operators.append(PlanOperator.FILTER)
        operators.append(PlanOperator.PROJECT)
        if analysis.has_aggregates:
            operators.append(PlanOperator.AGGREGATE)
        if analysis.statement.distinct:
            operators.append(PlanOperator.DISTINCT)
        if analysis.sorts:
            operators.append(PlanOperator.ORDER)
        if analysis.statement.skip is not None:
            operators.append(PlanOperator.SKIP)
        if analysis.statement.limit is not None:
            operators.append(PlanOperator.LIMIT)
        return Plan(analysis=analysis, operators=tuple(operators))


__all__ = [
    "Plan",
    "PlanBuilder",
    "PlanOperator",
]
