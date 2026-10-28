# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for lexing query source text."""

import dataclasses
import typing

import pytest

from pygrafito.engine.query.lexer import Lexer
from pygrafito.engine.query.tokens import Keyword, Span, Token, TokenKind
from pygrafito.model import QuerySyntaxError


class TestTokens:
    """Verify token construction and spans."""

    def test_token_is_frozen_and_slotted(self) -> None:
        token = Token(
            kind=TokenKind.IDENTIFIER,
            value="Quorra",
            text="Quorra",
            span=Span(line=1, column=1, offset=0, end=6),
        )
        assert not hasattr(token, "__dict__")
        with pytest.raises(dataclasses.FrozenInstanceError):
            token.value = "Tron"  # type: ignore[misc]

    def test_keyword_predicate(self) -> None:
        tokens = Lexer.tokenize("match")
        assert tokens[0].is_keyword(Keyword.MATCH)
        assert not tokens[0].is_keyword(Keyword.RETURN)

    def test_eof_always_terminates(self) -> None:
        tokens = Lexer.tokenize("")
        assert len(tokens) == 1
        assert tokens[0].kind is TokenKind.EOF
        assert tokens[0].span.line == 1
        assert tokens[0].span.column == 1


class TestLexer:
    """Verify every token class and source position."""

    def kinds(self, text: str) -> list[TokenKind]:
        return [token.kind for token in Lexer.tokenize(text)]

    def values(self, text: str) -> list[str | int | float]:
        return [token.value for token in Lexer.tokenize(text)]

    def test_keywords_are_case_insensitive(self) -> None:
        for text in ("MATCH", "match", "MaTcH"):
            tokens = Lexer.tokenize(text)
            assert tokens[0].kind is TokenKind.KEYWORD
            assert tokens[0].value == "MATCH"

    def test_identifiers_are_case_sensitive(self) -> None:
        tokens = Lexer.tokenize("Program program PROGRAM")
        assert [token.value for token in tokens[:-1]] == ["Program", "program", "PROGRAM"]
        assert all(token.kind is TokenKind.IDENTIFIER for token in tokens[:-1])

    def test_quoted_identifier_with_escaped_backtick(self) -> None:
        tokens = Lexer.tokenize("`a.b c``d`")
        assert tokens[0].kind is TokenKind.QUOTED_IDENTIFIER
        assert tokens[0].value == "a.b c`d"
        assert tokens[0].text == "`a.b c``d`"

    def test_keywords_quote_as_identifiers(self) -> None:
        tokens = Lexer.tokenize("`MATCH`")
        assert tokens[0].kind is TokenKind.QUOTED_IDENTIFIER
        assert tokens[0].value == "MATCH"

    def test_strings_single_and_double_quoted(self) -> None:
        tokens = Lexer.tokenize("'Quorra' \"Tron\"")
        assert tokens[0].kind is TokenKind.STRING
        assert tokens[0].value == "Quorra"
        assert tokens[1].kind is TokenKind.STRING
        assert tokens[1].value == "Tron"

    def test_string_escapes(self) -> None:
        tokens = Lexer.tokenize(r"'line\nquote\'slash\\tab\tzero\0unicode\u0041'")
        assert tokens[0].value == "line\nquote'slash\\tab\tzero\0unicodeA"

    def test_integers_and_floats(self) -> None:
        tokens = Lexer.tokenize("0 36 36.0 1e3 1.5e-2")
        assert [token.kind for token in tokens[:-1]] == [
            TokenKind.INTEGER,
            TokenKind.INTEGER,
            TokenKind.FLOAT,
            TokenKind.FLOAT,
            TokenKind.FLOAT,
        ]
        assert [token.value for token in tokens[:-1]] == [0, 36, 36.0, 1000.0, 0.015]

    def test_parameter(self) -> None:
        tokens = Lexer.tokenize("$cycles $under_score")
        assert tokens[0].kind is TokenKind.PARAMETER
        assert tokens[0].value == "cycles"
        assert tokens[1].value == "under_score"

    def test_operators_and_punctuation(self) -> None:
        tokens = Lexer.tokenize("|| <> != <= >= = < > + - * / % ( ) [ ] { } : , . | ;")
        values = [str(token.value) for token in tokens[:-1]]
        assert values[:13] == [
            "||",
            "<>",
            "!=",
            "<=",
            ">=",
            "=",
            "<",
            ">",
            "+",
            "-",
            "*",
            "/",
            "%",
        ]
        assert values[13:] == ["(", ")", "[", "]", "{", "}", ":", ",", ".", "|", ";"]
        assert all(token.kind is TokenKind.OPERATOR for token in tokens[:13])
        assert all(token.kind is TokenKind.PUNCTUATION for token in tokens[13:-1])
        assert tokens[-1].kind is TokenKind.EOF

    def test_line_and_block_comments_are_ignored(self) -> None:
        tokens = Lexer.tokenize("MATCH // comment\n/* block\n comment */ (n)")
        assert [str(token.value) for token in tokens[:-1]] == ["MATCH", "(", "n", ")"]

    def test_comment_kind_exists(self) -> None:
        assert TokenKind.COMMENT.value == "comment"

    def test_positions_track_lines_and_columns(self) -> None:
        tokens = Lexer.tokenize("MATCH\n  (n)")
        positions = [(token.span.line, token.span.column) for token in tokens]
        assert positions == [(1, 1), (2, 3), (2, 4), (2, 5), (2, 6)]

    def test_span_offsets_cover_source_text(self) -> None:
        text = "MATCH (n)"
        for token in Lexer.tokenize(text)[:-1]:
            assert text[token.span.offset : token.span.end] == token.text

    def test_unsupported_clause_keywords_are_tokens(self) -> None:
        unsupported = [
            "OPTIONAL",
            "WITH",
            "UNWIND",
            "CREATE",
            "MERGE",
            "SET",
            "REMOVE",
            "DELETE",
            "DETACH",
            "CASE",
            "ON",
        ]
        for name in unsupported:
            token = Lexer.tokenize(name)[0]
            assert token.kind is TokenKind.KEYWORD
            assert token.value == name

    def test_write_keywords_are_case_insensitive(self) -> None:
        names = ["CREATE", "SET", "REMOVE", "DELETE", "DETACH", "MERGE", "ON"]
        for name in names:
            token = Lexer.tokenize(name.lower())[0]
            assert token.kind is TokenKind.KEYWORD
            assert token.value == name

    @pytest.mark.parametrize(
        "name",
        ["WHEN", "THEN", "ELSE", "END", "UNION", "INTERSECT", "EXCEPT"],
    )
    def test_expression_and_set_keywords_are_reserved(self, name: str) -> None:
        token = Lexer.tokenize(name.lower())[0]
        assert token.kind is TokenKind.KEYWORD
        assert token.value == name

    @pytest.mark.parametrize(
        "name",
        ["DIFFERENT", "EDGES", "REPEATABLE", "ELEMENTS"],
    )
    def test_match_mode_keywords_are_reserved(self, name: str) -> None:
        token = Lexer.tokenize(name.lower())[0]
        assert token.kind is TokenKind.KEYWORD
        assert token.value == name

    def test_match_mode_keywords_quote_as_identifiers(self) -> None:
        tokens = Lexer.tokenize("`different` `edges` `repeatable` `elements`")
        assert all(token.kind is TokenKind.QUOTED_IDENTIFIER for token in tokens[:-1])
        assert [str(token.value) for token in tokens[:-1]] == [
            "different",
            "edges",
            "repeatable",
            "elements",
        ]

    @pytest.mark.parametrize("name", ["ANY", "SHORTEST"])
    def test_search_keywords_are_reserved(self, name: str) -> None:
        token = Lexer.tokenize(name.lower())[0]
        assert token.kind is TokenKind.KEYWORD
        assert token.value == name

    def test_search_keywords_quote_as_identifiers(self) -> None:
        tokens = Lexer.tokenize("`any` `shortest`")
        assert all(token.kind is TokenKind.QUOTED_IDENTIFIER for token in tokens[:-1])
        assert [str(token.value) for token in tokens[:-1]] == ["any", "shortest"]

    def test_new_keywords_quote_as_identifiers(self) -> None:
        tokens = Lexer.tokenize("`when` `then` `else` `end` `union` `intersect` `except`")
        assert len(tokens) == 8
        assert all(token.kind is TokenKind.QUOTED_IDENTIFIER for token in tokens[:-1])
        assert [str(token.value) for token in tokens[:-1]] == [
            "when",
            "then",
            "else",
            "end",
            "union",
            "intersect",
            "except",
        ]

    @pytest.mark.parametrize(
        ("text", "line", "column", "fragment"),
        [
            ("'unterminated", 1, 1, "unterminated string"),
            ('"unterminated', 1, 1, "unterminated string"),
            ("`unterminated", 1, 1, "unterminated quoted identifier"),
            ("/* unterminated", 1, 1, "unterminated block comment"),
            ("MATCH (n) @@", 1, 11, "invalid character"),
            ("1.2.3", 1, 1, "invalid numeric literal"),
            ("1.", 1, 1, "invalid numeric literal"),
            ("1e", 1, 1, "invalid numeric literal"),
            ("1e+", 1, 1, "invalid numeric literal"),
            ("123abc", 1, 1, "invalid numeric literal"),
            ("$", 1, 1, "invalid parameter name"),
            (r"'\q'", 1, 4, "invalid string escape"),
            (r"'\u12'", 1, 7, "invalid unicode escape"),
        ],
    )
    def test_error_positions(
        self,
        text: str,
        line: int,
        column: int,
        fragment: str,
    ) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Lexer.tokenize(text)
        assert fragment in caught.value.message
        assert caught.value.line == line
        assert caught.value.column == column

    def test_range_dots_are_not_part_of_a_number(self) -> None:
        tokens = Lexer.tokenize("1..3")
        assert [token.value for token in tokens[:-1]] == [1, ".", ".", 3]


class TestGqlVocabulary:
    """Verify the GQL keywords and the dash comment rule."""

    KEYWORDS: typing.ClassVar[tuple[str, ...]] = (
        "INSERT",
        "FOR",
        "FILTER",
        "OFFSET",
        "NODETACH",
        "NULLS",
        "FIRST",
        "LAST",
        "ALL",
        "TRAIL",
        "WALK",
        "SIMPLE",
        "ACYCLIC",
        "LET",
        "NEXT",
        "GROUP",
        "ORDINALITY",
    )

    def test_new_keywords_are_reserved(self) -> None:
        """Require every new GQL word to lex as a keyword."""
        for word in self.KEYWORDS:
            token = Lexer.tokenize(word)[0]
            assert token.kind is TokenKind.KEYWORD, word
            assert token.value == word

    def test_similar_identifiers_are_not_keywords(self) -> None:
        """Require longer identifiers to stay identifiers."""
        for word in ("inserts", "foreach", "filtered", "grouping", "offsets", "next_step"):
            assert Lexer.tokenize(word)[0].kind is TokenKind.IDENTIFIER, word

    def test_dash_comment_is_skipped(self) -> None:
        """Require a dash comment to be ignored."""
        tokens = Lexer.tokenize("MATCH (n) -- explanation\nRETURN n")
        assert [token.value for token in tokens[:3]] == ["MATCH", "(", "n"]

    def test_dash_comment_cannot_follow_a_pattern(self) -> None:
        """Require an abutting dash pair after a pattern to fail."""
        with pytest.raises(QuerySyntaxError, match="undirected relationship"):
            Lexer.tokenize("MATCH (a)--(b) RETURN b")
