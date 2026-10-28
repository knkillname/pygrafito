# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Property tests for the total query input error contract."""

import hypothesis
import hypothesis.strategies

from pygrafito.engine.query.lexer import Lexer
from pygrafito.engine.query.parser import Parser
from pygrafito.model import QueryError


class TestQueryInputProperties:
    """Verify that adversarial query text stays inside the query hierarchy."""

    @hypothesis.given(text=hypothesis.strategies.text(max_size=200))
    @hypothesis.example("MATCH (n) RETURN n")
    @hypothesis.example("RETURN " + "(" * 100 + "1" + ")" * 100)
    @hypothesis.example("RETURN " + "9" * 5000)
    def test_parser_only_raises_query_errors(self, text: str) -> None:
        """Return or raise a query error, never a built-in exception."""
        try:
            Parser.parse_statement(text)
        except QueryError:
            return

    @hypothesis.given(text=hypothesis.strategies.text(max_size=200))
    @hypothesis.example("MATCH (n) RETURN n")
    @hypothesis.example("RETURN " + "9" * 5000)
    def test_lexer_only_raises_query_errors(self, text: str) -> None:
        """Return tokens or raise a query error, never a built-in exception."""
        try:
            Lexer.tokenize(text)
        except QueryError:
            return
