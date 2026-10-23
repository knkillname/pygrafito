# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Prepared query statements with reusable parsed plans."""

from collections.abc import Mapping

from pygrafito.engine.query.executor import QueryExecutor
from pygrafito.engine.query.plan import Plan
from pygrafito.engine.query.results import QueryResult
from pygrafito.engine.query.values import QueryValue


class PreparedQuery:
    """A parsed, analysed, and planned query that can run repeatedly.

    Parameters
    ----------
    executor : QueryExecutor
        Executor bound to the graph that prepared the query.
    text : str
        Original query source text.
    plan : Plan
        Planned query reused by every execution.
    """

    def __init__(self, executor: QueryExecutor, text: str, plan: Plan) -> None:
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

    def execute(
        self,
        parameters: Mapping[str, QueryValue] | None = None,
    ) -> QueryResult:
        """Execute the prepared statement with one parameter mapping.

        Parameters
        ----------
        parameters : Mapping[str, QueryValue] | None, optional
            Query parameter values, by default none.

        Returns
        -------
        QueryResult
            Materialized result.
        """
        values: Mapping[str, QueryValue] = {} if parameters is None else parameters
        return self._executor.execute_graph(self._plan, values)


__all__ = ["PreparedQuery"]
