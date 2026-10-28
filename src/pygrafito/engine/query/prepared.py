# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Prepared query statements with reusable parsed plans."""

from collections.abc import Mapping

from pygrafito.engine.query.executor import QueryExecutor
from pygrafito.engine.query.plan import PlannedStatement
from pygrafito.engine.query.results import QueryResult
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import QueryBudget


class PreparedQuery:
    """A parsed, analysed, and planned query that can run repeatedly.

    Parameters
    ----------
    executor : QueryExecutor
        Executor bound to the graph that prepared the query.
    text : str
        Original query source text.
    plan : PlannedStatement
        Planned query reused by every execution.
    """

    def __init__(self, executor: QueryExecutor, text: str, plan: PlannedStatement) -> None:
        self._executor = executor
        self._text = text
        self._plan = plan

    @property
    def text(self) -> str:
        """Return the source text of the prepared statement.

        Returns
        -------
        str
            Original query source text.
        """
        return self._text

    @property
    def columns(self) -> tuple[str, ...]:
        """Return the projected column names.

        Returns
        -------
        tuple[str, ...]
            Column names in projection order, available before execution.
        """
        return self._plan.analysis.columns

    @property
    def is_write(self) -> bool:
        """Return whether the prepared statement changes data.

        Returns
        -------
        bool
            ``True`` when the statement contains a write clause.
        """
        return self._plan.analysis.is_write

    @property
    def parameters(self) -> frozenset[str]:
        """Return the parameter names referenced by the statement.

        Returns
        -------
        frozenset[str]
            Parameter names without the leading ``$``.
        """
        return self._plan.analysis.parameters

    def execute(
        self,
        parameters: Mapping[str, QueryValue] | None = None,
        *,
        budget: QueryBudget | None = None,
    ) -> QueryResult:
        """Execute the prepared statement with one parameter mapping.

        Parameters
        ----------
        parameters : Mapping[str, QueryValue] | None, optional
            Query parameter values, by default none.
        budget : QueryBudget | None, optional
            Budget for this execution, by default the graph default.

        Returns
        -------
        QueryResult
            Materialized result.
        """
        values: Mapping[str, QueryValue] = {} if parameters is None else parameters
        return self._executor.execute_graph(self._plan, values, budget)


__all__ = ["PreparedQuery"]
