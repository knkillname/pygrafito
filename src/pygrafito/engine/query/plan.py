# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Logical and physical planning for query execution."""

import dataclasses
import typing
from enum import Enum

from pygrafito.engine.query.ast import Create, Delete, Remove, Set
from pygrafito.engine.query.semantic import Analysis


class PlanOperator(Enum):
    """One operator in the physical plan pipeline."""

    MATCH = "match"
    FILTER = "filter"
    CREATE = "create"
    SET = "set"
    REMOVE = "remove"
    DELETE = "delete"
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

    _MUTATIONS: typing.ClassVar[dict[type[object], PlanOperator]] = {
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
            Operator pipeline from match through mutation and pagination.
        """
        operators: list[PlanOperator] = []
        if analysis.match_clause is not None:
            operators.append(PlanOperator.MATCH)
            if analysis.match_clause.where is not None:
                operators.append(PlanOperator.FILTER)
        for clause in analysis.statement.clauses:
            operator = cls._MUTATIONS.get(type(clause))
            if operator is not None:
                operators.append(operator)
        return_clause = analysis.return_clause
        if return_clause is not None:
            operators.append(PlanOperator.PROJECT)
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
        return Plan(analysis=analysis, operators=tuple(operators))


__all__ = [
    "Plan",
    "PlanBuilder",
    "PlanOperator",
]
