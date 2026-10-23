# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the public query API and lifecycle integration."""

from collections.abc import Iterator

import pytest

import pygrafito
import pygrafito.engine.query.ast
import pygrafito.engine.query.compiler
import pygrafito.engine.query.executor
import pygrafito.engine.query.lexer
import pygrafito.engine.query.parser
import pygrafito.engine.query.plan
import pygrafito.engine.query.prepared
import pygrafito.engine.query.results
import pygrafito.engine.query.semantic
import pygrafito.engine.query.tokens
import pygrafito.engine.query.values
from pygrafito import (
    Graph,
    GraphClosedError,
    PreparedQuery,
    QueryExecutionError,
    QueryResult,
    QuerySemanticError,
    QuerySyntaxError,
    Row,
    TransactionError,
)


class TestPublicApi:
    """Verify Graph.query, Graph.prepare, and PreparedQuery."""

    @pytest.fixture
    def graph(self) -> Iterator[Graph]:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node("Program", designation="Quorra", cycles=37)
            tron = graph.add_node("Program", designation="Tron", cycles=40)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            graph.add_relationship(quorra, "ALLIES_WITH", tron)
            yield graph

    def test_query_returns_result(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) RETURN n.designation AS name")
        assert isinstance(result, QueryResult)
        assert result.columns == ("name",)
        assert isinstance(result.rows[0], Row)

    def test_prepared_query_columns_before_execution(self, graph: Graph) -> None:
        prepared = graph.prepare("MATCH (n:Program) RETURN n.designation AS name")
        assert isinstance(prepared, PreparedQuery)
        assert prepared.columns == ("name",)
        assert "MATCH" in prepared.text

    def test_prepared_query_reuses_the_statement(self, graph: Graph) -> None:
        prepared = graph.prepare(
            "MATCH (n:Program) WHERE n.cycles > $minimum RETURN n.designation AS name ORDER BY name"
        )
        first = prepared.execute({"minimum": 36})
        second = prepared.execute({"minimum": 39})
        assert [row["name"] for row in first] == ["Quorra", "Tron"]
        assert [row["name"] for row in second] == ["Tron"]

    def test_extra_parameters_are_ignored(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n) RETURN n",
            {"unused": 1},
        )
        assert len(result) == 3

    def test_missing_parameter_raises(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError):
            graph.query("MATCH (n) WHERE n.cycles > $cycles RETURN n")

    def test_syntax_error_at_query_and_prepare(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError):
            graph.query("MATCH (n) RETURN")
        with pytest.raises(QuerySyntaxError):
            graph.prepare("MATCH (n) RETURN")

    def test_semantic_error_at_prepare(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError):
            graph.prepare("MATCH (n) RETURN missing")

    def test_execution_error_from_query(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("MATCH (n) RETURN 1 / 0")

    def test_query_defaults_to_no_parameters(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) RETURN count(*) AS total")
        assert result.rows[0]["total"] == 3

    def test_closed_graph_query_and_prepare(self) -> None:
        graph = Graph.open(":memory:")
        prepared = graph.prepare("MATCH (n) RETURN n")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.query("MATCH (n) RETURN n")
        with pytest.raises(GraphClosedError):
            graph.prepare("MATCH (n) RETURN n")
        with pytest.raises(GraphClosedError):
            prepared.execute()

    def test_active_transaction_guard(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            with pytest.raises(TransactionError):
                graph.query("MATCH (n) RETURN n")
            prepared = graph.prepare("MATCH (n) RETURN n")
            with pytest.raises(TransactionError):
                prepared.execute()
            transaction.add_node("ISO", designation="Quorra")

    def test_prepared_query_observes_later_commits(self, graph: Graph) -> None:
        prepared = graph.prepare("MATCH (n:ISO) RETURN n.designation")
        assert prepared.execute().rows == ()
        graph.add_node("ISO", designation="Quorra")
        result = prepared.execute()
        assert result.rows[0]["n.designation"] == "Quorra"


class TestPackageExports:
    """Verify the query surface is exported from the package root."""

    def test_query_exports(self) -> None:
        expected = {
            "PreparedQuery",
            "QueryError",
            "QueryExecutionError",
            "QueryResult",
            "QuerySemanticError",
            "QuerySyntaxError",
            "Row",
        }
        assert expected <= set(pygrafito.__all__)
        for name in expected:
            assert hasattr(pygrafito, name)

    def test_query_modules_import(self) -> None:
        modules = (
            pygrafito.engine.query,
            pygrafito.engine.query.ast,
            pygrafito.engine.query.compiler,
            pygrafito.engine.query.executor,
            pygrafito.engine.query.lexer,
            pygrafito.engine.query.parser,
            pygrafito.engine.query.plan,
            pygrafito.engine.query.prepared,
            pygrafito.engine.query.results,
            pygrafito.engine.query.semantic,
            pygrafito.engine.query.tokens,
            pygrafito.engine.query.values,
        )
        assert all(module.__name__.startswith("pygrafito") for module in modules)
