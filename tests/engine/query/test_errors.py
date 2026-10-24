# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the query error hierarchy and source positions."""

import pytest

from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.semantic import SemanticAnalyzer
from pygrafito.model import (
    PygrafitoError,
    QueryError,
    QueryExecutionError,
    QuerySemanticError,
    QuerySyntaxError,
)


class TestQueryErrors:
    """Verify the query error hierarchy and position attributes."""

    def test_concrete_errors_are_query_errors(self) -> None:
        for error_type in (QuerySyntaxError, QuerySemanticError, QueryExecutionError):
            assert issubclass(error_type, QueryError)
            assert issubclass(error_type, PygrafitoError)

    def test_position_is_recorded_and_formatted(self) -> None:
        error = QuerySyntaxError("unexpected token", line=3, column=7)
        assert error.message == "unexpected token"
        assert error.line == 3
        assert error.column == 7
        assert str(error) == "unexpected token (line 3, column 7)"

    def test_position_is_optional(self) -> None:
        error = QuerySemanticError("unbound variable")
        assert error.line is None
        assert error.column is None
        assert str(error) == "unbound variable"

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(QueryError):
            raise QueryExecutionError("division by zero", line=1, column=12)

    def test_execution_error_is_not_a_syntax_error(self) -> None:
        assert not issubclass(QueryExecutionError, QuerySyntaxError)
        assert not issubclass(QuerySemanticError, QuerySyntaxError)


class TestComposedQueryErrors:
    """Verify the error class and position of new composition failures."""

    @staticmethod
    def analyze(text: str) -> None:
        SemanticAnalyzer.analyze(Parser.parse_statement(text))

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (a)-[:ALLIES_WITH*1.3]->(b) RETURN b",
            "CREATE (n:Program) WITH n RETURN n",
            "MATCH (a) WITH a",
            "MATCH (a) RETURN a CREATE (b:Program)",
        ],
    )
    def test_clause_and_quantifier_syntax_errors_report_positions(self, text: str) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement(text)
        assert caught.value.line is not None
        assert caught.value.column is not None

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (a)-[*]->(b) RETURN b",
            "MATCH (a)-[*3..1]->(b) RETURN b",
            "MATCH (a)-[r*1..2]->(b) RETURN type(r)",
            "MATCH (a:Program) WITH a.cycles + 1 RETURN a",
            "MATCH p = (a), p = (b) RETURN p",
        ],
    )
    def test_semantic_errors_use_the_semantic_class(self, text: str) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze(text)

    def test_unbound_later_reference_reports_a_position(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (a:Program) WITH a.designation AS name RETURN a")
        assert caught.value.line == 1
        assert caught.value.column is not None
