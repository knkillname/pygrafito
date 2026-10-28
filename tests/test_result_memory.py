# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the materialized result and memory-budget contract."""

import pytest

from pygrafito import Graph, QueryBudget, QueryBudgetExceededError, QueryResult


class TestResultMemory:
    """Verify that results are materialized and bounded by the row budget."""

    def test_rows_are_materialized_tuples(self) -> None:
        """Expose every row before the call returns."""
        with Graph.open(":memory:") as graph:
            result = graph.query("FOR value IN [1, 2, 3] RETURN value")
        assert isinstance(result, QueryResult)
        assert isinstance(result.rows, tuple)
        assert [row["value"] for row in result.rows] == [1, 2, 3]

    def test_result_survives_handle_close(self) -> None:
        """Keep materialized rows usable after the graph closes."""
        graph = Graph.open(":memory:")
        result = graph.query("FOR value IN [1, 2, 3] RETURN value")
        graph.close()
        assert len(result.rows) == 3

    def test_max_rows_bounds_the_result(self) -> None:
        """Reject a result that would exceed a lowered row budget."""
        statement = "FOR value IN [1, 2, 3] RETURN value"
        with Graph.open(":memory:") as graph:
            with pytest.raises(QueryBudgetExceededError):
                graph.query(statement, budget=QueryBudget(max_rows=2))
            result = graph.query(statement, budget=QueryBudget(max_rows=3))
        assert len(result.rows) == 3

    def test_default_row_limit_is_explicit(self) -> None:
        """Expose the documented default row limit."""
        assert QueryBudget().max_rows == 100_000

    def test_no_streaming_result_api(self) -> None:
        """Keep streaming out of the 1.x public surface."""
        with Graph.open(":memory:") as graph:
            names = dir(graph)
        assert "stream" not in names
        assert "iter_rows" not in names
        assert "fetchmany" not in names
        assert not hasattr(QueryResult, "__next__")
