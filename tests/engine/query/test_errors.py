# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the query error hierarchy and source positions."""

import pytest

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
