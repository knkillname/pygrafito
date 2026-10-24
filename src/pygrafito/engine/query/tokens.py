# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Token kinds, keywords, and source positions for the query language."""

import dataclasses
import typing
from collections.abc import Mapping
from enum import Enum


class TokenKind(Enum):
    """Category of one lexed token."""

    KEYWORD = "keyword"
    IDENTIFIER = "identifier"
    QUOTED_IDENTIFIER = "quoted_identifier"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    PARAMETER = "parameter"
    OPERATOR = "operator"
    PUNCTUATION = "punctuation"
    COMMENT = "comment"
    EOF = "end_of_input"


class Keyword(Enum):
    """Reserved words recognized by the lexer."""

    MATCH = "MATCH"
    WHERE = "WHERE"
    RETURN = "RETURN"
    DISTINCT = "DISTINCT"
    AS = "AS"
    ORDER = "ORDER"
    BY = "BY"
    ASC = "ASC"
    DESC = "DESC"
    SKIP = "SKIP"
    LIMIT = "LIMIT"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    IN = "IN"
    IS = "IS"
    NULL = "NULL"
    TRUE = "TRUE"
    FALSE = "FALSE"
    STARTS = "STARTS"
    ENDS = "ENDS"
    WITH = "WITH"
    CONTAINS = "CONTAINS"
    OPTIONAL = "OPTIONAL"
    UNWIND = "UNWIND"
    CREATE = "CREATE"
    MERGE = "MERGE"
    SET = "SET"
    REMOVE = "REMOVE"
    DELETE = "DELETE"
    DETACH = "DETACH"
    CASE = "CASE"
    CALL = "CALL"
    ON = "ON"


class KeywordIndex:
    """Map keyword spellings to their canonical members."""

    BY_NAME: typing.ClassVar[Mapping[str, Keyword]] = {member.value: member for member in Keyword}

    @classmethod
    def lookup(cls, text: str) -> Keyword | None:
        """Resolve a case-insensitive keyword spelling.

        Parameters
        ----------
        text : str
            Source text of the candidate keyword.

        Returns
        -------
        Keyword | None
            The canonical keyword, or ``None`` when the text is not reserved.
        """
        return cls.BY_NAME.get(text.upper())


@dataclasses.dataclass(frozen=True, slots=True)
class Span:
    """Position of one token in the source text.

    Parameters
    ----------
    line : int
        One-based starting line.
    column : int
        One-based starting column.
    offset : int
        Zero-based starting character offset.
    end : int
        Zero-based exclusive ending character offset.
    """

    line: int
    column: int
    offset: int
    end: int


@dataclasses.dataclass(frozen=True, slots=True)
class Token:
    """One lexical token with its source text and position.

    Parameters
    ----------
    kind : TokenKind
        Category of the token.
    value : str | int | float
        Decoded value: keyword name, identifier, string contents, number, or
        parameter name without ``$``.
    text : str
        Exact source text of the token.
    span : Span
        Position of the token in the source text.
    """

    kind: TokenKind
    value: str | int | float
    text: str
    span: Span

    def is_keyword(self, keyword: Keyword) -> bool:
        """Report whether this token is the given keyword.

        Parameters
        ----------
        keyword : Keyword
            Keyword to compare against.

        Returns
        -------
        bool
            ``True`` when the token is that keyword.
        """
        return self.kind is TokenKind.KEYWORD and self.value == keyword.value


__all__ = [
    "Keyword",
    "KeywordIndex",
    "Span",
    "Token",
    "TokenKind",
]
