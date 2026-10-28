# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the per-execution query budget."""

import typing

import pytest

from pygrafito import (
    Graph,
    QueryBudget,
    QueryBudgetExceededError,
    ValidationError,
)


class TestQueryBudgetValue:
    """Check the value object defaults and validation."""

    def test_documented_defaults(self) -> None:
        """Expose the documented expansion and row defaults."""
        budget = QueryBudget()
        assert budget.max_expansions == 1_000_000
        assert budget.max_rows == 100_000
        assert budget.max_seconds is None

    def test_none_is_unlimited(self) -> None:
        """Treat a missing counter as unlimited."""
        budget = QueryBudget(max_expansions=None, max_rows=None, max_seconds=None)
        assert budget.max_expansions is None
        assert budget.max_rows is None
        assert budget.max_seconds is None

    def test_negative_counters_are_rejected(self) -> None:
        """Reject negative counters."""
        with pytest.raises(ValidationError):
            QueryBudget(max_expansions=-1)
        with pytest.raises(ValidationError):
            QueryBudget(max_rows=-1)
        with pytest.raises(ValidationError):
            QueryBudget(max_seconds=-0.5)

    def test_boolean_and_fractional_counters_are_rejected(self) -> None:
        """Reject booleans and fractional counts."""
        with pytest.raises(ValidationError):
            QueryBudget(max_expansions=True)
        with pytest.raises(ValidationError):
            QueryBudget(max_rows=typing.cast(int, 1.5))
        with pytest.raises(ValidationError):
            QueryBudget(max_seconds=True)


class TestBudgetExecution:
    """Check counters, overrides, and the error contract."""

    @staticmethod
    def make_graph() -> Graph:
        """Return an in-memory graph with a small TRON program chain.

        Returns
        -------
        Graph
            Open graph with two programs and one trust relationship.
        """
        graph = Graph.open(":memory:")
        kevin = graph.add_node("Program", designation="Kevin Flynn")
        quorra = graph.add_node("Program", designation="Quorra")
        graph.add_relationship(kevin, "TRUSTS", quorra)
        return graph

    def test_row_limit_stops_a_read(self) -> None:
        """Raise when a stage produces more rows than the limit."""
        with self.make_graph() as graph, pytest.raises(QueryBudgetExceededError) as raised:
            graph.query(
                "FOR value IN [1, 2, 3] RETURN value",
                budget=QueryBudget(max_rows=2),
            )
        assert raised.value.counter == "rows"
        assert raised.value.limit == 2
        assert "rows" in str(raised.value)
        assert "2" in str(raised.value)

    def test_expansion_limit_stops_a_walk(self) -> None:
        """Raise when a path expands more relationships than allowed."""
        with self.make_graph() as graph, pytest.raises(QueryBudgetExceededError) as raised:
            graph.query(
                "MATCH (a:Program)-[:TRUSTS*1..2]->(b) RETURN b",
                budget=QueryBudget(max_expansions=0),
            )
        assert raised.value.counter == "expansions"
        assert raised.value.limit == 0

    def test_time_limit_is_deterministic_at_zero(self) -> None:
        """Raise before executing when no time is allowed."""
        with self.make_graph() as graph, pytest.raises(QueryBudgetExceededError) as raised:
            graph.query(
                "MATCH (n:Program) RETURN n",
                budget=QueryBudget(max_seconds=0),
            )
        assert raised.value.counter == "seconds"
        assert raised.value.limit == 0

    def test_no_partial_result(self) -> None:
        """Return no rows when a read exceeds the budget."""
        with self.make_graph() as graph:
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    "MATCH (n:Program) RETURN n",
                    budget=QueryBudget(max_rows=1),
                )
            result = graph.query("MATCH (n:Program) RETURN n")
        assert len(result.rows) == 2

    def test_graph_default_applies(self) -> None:
        """Use the graph default when no override is supplied."""
        graph = Graph.open(":memory:", budget=QueryBudget(max_rows=0))
        try:
            with pytest.raises(QueryBudgetExceededError):
                graph.query("FOR value IN [1] RETURN value")
        finally:
            graph.close()

    def test_per_query_override_wins(self) -> None:
        """Use the override for one execution and keep the default."""
        graph = Graph.open(":memory:", budget=QueryBudget(max_rows=0))
        try:
            result = graph.query(
                "FOR value IN [1, 2] RETURN value",
                budget=QueryBudget(max_rows=10),
            )
            assert len(result.rows) == 2
            with pytest.raises(QueryBudgetExceededError):
                graph.query("FOR value IN [1] RETURN value")
        finally:
            graph.close()

    def test_prepared_execution_override(self) -> None:
        """Apply the override supplied to each prepared execution."""
        with self.make_graph() as graph:
            prepared = graph.prepare("FOR value IN [1, 2, 3] RETURN value")
            with pytest.raises(QueryBudgetExceededError):
                prepared.execute(budget=QueryBudget(max_rows=2))
            result = prepared.execute(budget=QueryBudget(max_rows=5))
        assert len(result.rows) == 3


class TestBudgetRollback:
    """Check that a budget failure never leaves a partial write."""

    def test_write_rolls_back(self) -> None:
        """Undo every mutation of a write statement that exceeds the budget."""
        with Graph.open(":memory:") as graph:
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    "CREATE (n:Program {designation: 'Quorra'})",
                    budget=QueryBudget(max_rows=0),
                )
            result = graph.query("MATCH (n:Program) RETURN n")
        assert result.rows == ()

    def test_handle_remains_usable(self) -> None:
        """Accept a later statement after a budget failure."""
        with Graph.open(":memory:") as graph:
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    "CREATE (n:Program {designation: 'Quorra'})",
                    budget=QueryBudget(max_rows=0),
                )
            created = graph.query(
                "CREATE (n:Program {designation: 'Tron'}) RETURN n.designation AS name",
                budget=QueryBudget(max_rows=10),
            )
        assert created.rows[0]["name"] == "Tron"

    def test_active_transaction_survives(self) -> None:
        """Undo only the failing statement inside an active transaction."""
        with Graph.open(":memory:") as graph:
            with graph.transaction() as transaction:
                with pytest.raises(QueryBudgetExceededError):
                    transaction.query(
                        "CREATE (n:Program {designation: 'Rinzler'})",
                        budget=QueryBudget(max_rows=0),
                    )
                transaction.query("CREATE (n:Program {designation: 'Tron'})")
            result = graph.query("MATCH (n:Program) RETURN n.designation AS name")
        assert [row["name"] for row in result.rows] == ["Tron"]
