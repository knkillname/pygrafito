# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Hand-written lexer for the query language."""

import string
import typing

from pygrafito.engine.query.tokens import (
    KeywordIndex,
    Span,
    Token,
    TokenKind,
)
from pygrafito.model import QuerySyntaxError


class Lexer:
    """Turn query source text into positioned tokens.

    Parameters
    ----------
    text : str
        Query source text.
    """

    OPERATORS: typing.ClassVar[tuple[str, ...]] = (
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
    )
    PUNCTUATION: typing.ClassVar[frozenset[str]] = frozenset("()[]{}:,.|;")
    WHITESPACE: typing.ClassVar[frozenset[str]] = frozenset(" \t\r\n\f\v")
    IDENTIFIER_START: typing.ClassVar[frozenset[str]] = frozenset(string.ascii_letters + "_")
    IDENTIFIER_BODY: typing.ClassVar[frozenset[str]] = frozenset(
        string.ascii_letters + string.digits + "_"
    )
    HEX_DIGITS: typing.ClassVar[frozenset[str]] = frozenset(string.hexdigits)
    UNICODE_ESCAPE_LENGTH: typing.ClassVar[int] = 4
    ESCAPES: typing.ClassVar[dict[str, str]] = {
        "\\": "\\",
        "'": "'",
        '"': '"',
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "b": "\b",
        "f": "\f",
        "0": "\0",
    }

    def __init__(self, text: str) -> None:
        self._text = text
        self._length = len(text)
        self._offset = 0
        self._line = 1
        self._column = 1

    @classmethod
    def tokenize(cls, text: str) -> tuple[Token, ...]:
        """Lex one query source text.

        Parameters
        ----------
        text : str
            Query source text.

        Returns
        -------
        tuple[Token, ...]
            Tokens in source order, ending with an end-of-input token.
        """
        return cls(text).scan()

    def scan(self) -> tuple[Token, ...]:
        """Scan every token in the source text.

        Returns
        -------
        tuple[Token, ...]
            Tokens in source order, ending with an end-of-input token.

        Raises
        ------
        QuerySyntaxError
            If the text contains an invalid or unterminated construct.
        """
        tokens: list[Token] = []
        while True:
            self._skip_ignored()
            if self._at_end():
                tokens.append(
                    self._token(TokenKind.EOF, "", self._offset, self._line, self._column)
                )
                return tuple(tokens)
            start_offset = self._offset
            start_line = self._line
            start_column = self._column
            character = self._peek()
            if character == "`":
                tokens.append(self._quoted_identifier(start_offset, start_line, start_column))
            elif character in {"'", '"'}:
                tokens.append(self._string(start_offset, start_line, start_column, character))
            elif character.isdigit():
                tokens.append(self._number(start_offset, start_line, start_column))
            elif character == "$":
                tokens.append(self._parameter(start_offset, start_line, start_column))
            elif character in self.IDENTIFIER_START:
                tokens.append(self._identifier(start_offset, start_line, start_column))
            elif self._match_operator(tokens, start_offset, start_line, start_column):
                continue
            elif character in self.PUNCTUATION:
                self._advance()
                tokens.append(
                    self._token(
                        TokenKind.PUNCTUATION,
                        character,
                        start_offset,
                        start_line,
                        start_column,
                    )
                )
            else:
                self._fail(f"invalid character {character!r}", start_line, start_column)

    def _skip_ignored(self) -> None:
        """Skip whitespace and comments."""
        while not self._at_end():
            character = self._peek()
            if character in self.WHITESPACE:
                self._advance()
                continue
            if character == "/" and self._peek(1) == "/":
                self._line_comment()
                continue
            if character == "/" and self._peek(1) == "*":
                self._block_comment()
                continue
            return

    def _line_comment(self) -> None:
        """Consume a ``//`` comment up to the end of the line."""
        while not self._at_end() and self._peek() != "\n":
            self._advance()

    def _block_comment(self) -> None:
        """Consume a ``/* ... */`` comment.

        Raises
        ------
        QuerySyntaxError
            If the comment is not terminated before the end of input.
        """
        start_line = self._line
        start_column = self._column
        self._advance()
        self._advance()
        while not self._at_end():
            if self._peek() == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                return
            self._advance()
        self._fail("unterminated block comment", start_line, start_column)

    def _match_operator(
        self,
        tokens: list[Token],
        start_offset: int,
        start_line: int,
        start_column: int,
    ) -> bool:
        """Match an operator at the current position.

        Parameters
        ----------
        tokens : list[Token]
            Token output that receives the operator.
        start_offset : int
            Zero-based offset where the token starts.
        start_line : int
            One-based line where the token starts.
        start_column : int
            One-based column where the token starts.

        Returns
        -------
        bool
            ``True`` when an operator was matched and consumed.
        """
        for operator in self.OPERATORS:
            if self._match(operator):
                tokens.append(
                    self._token(
                        TokenKind.OPERATOR,
                        operator,
                        start_offset,
                        start_line,
                        start_column,
                    )
                )
                return True
        return False

    def _identifier(
        self,
        start_offset: int,
        start_line: int,
        start_column: int,
    ) -> Token:
        """Scan an identifier or keyword.

        Parameters
        ----------
        start_offset : int
            Zero-based offset where the token starts.
        start_line : int
            One-based line where the token starts.
        start_column : int
            One-based column where the token starts.

        Returns
        -------
        Token
            Identifier or keyword token.
        """
        while not self._at_end() and self._peek() in self.IDENTIFIER_BODY:
            self._advance()
        text = self._text[start_offset : self._offset]
        keyword = KeywordIndex.lookup(text)
        if keyword is None:
            return self._token(TokenKind.IDENTIFIER, text, start_offset, start_line, start_column)
        return self._token(TokenKind.KEYWORD, keyword.value, start_offset, start_line, start_column)

    def _quoted_identifier(
        self,
        start_offset: int,
        start_line: int,
        start_column: int,
    ) -> Token:
        """Scan a backtick-quoted identifier.

        Parameters
        ----------
        start_offset : int
            Zero-based offset where the token starts.
        start_line : int
            One-based line where the token starts.
        start_column : int
            One-based column where the token starts.

        Returns
        -------
        Token
            Quoted identifier token with its decoded name as value.

        Raises
        ------
        QuerySyntaxError
            If the identifier is not terminated.
        """
        self._advance()
        characters: list[str] = []
        while not self._at_end():
            character = self._peek()
            if character == "`":
                if self._peek(1) == "`":
                    characters.append("`")
                    self._advance()
                    self._advance()
                    continue
                self._advance()
                return self._token(
                    TokenKind.QUOTED_IDENTIFIER,
                    "".join(characters),
                    start_offset,
                    start_line,
                    start_column,
                )
            characters.append(character)
            self._advance()
        self._fail("unterminated quoted identifier", start_line, start_column)

    def _string(
        self,
        start_offset: int,
        start_line: int,
        start_column: int,
        quote: str,
    ) -> Token:
        """Scan a quoted string literal.

        Parameters
        ----------
        start_offset : int
            Zero-based offset where the token starts.
        start_line : int
            One-based line where the token starts.
        start_column : int
            One-based column where the token starts.
        quote : str
            Opening quote character.

        Returns
        -------
        Token
            String token with its decoded contents as value.

        Raises
        ------
        QuerySyntaxError
            If the string is not terminated or contains an invalid escape.
        """
        self._advance()
        characters: list[str] = []
        while not self._at_end():
            character = self._peek()
            if character == quote:
                self._advance()
                return self._token(
                    TokenKind.STRING,
                    "".join(characters),
                    start_offset,
                    start_line,
                    start_column,
                )
            if character == "\\":
                self._advance()
                characters.append(self._escape(start_line, start_column))
                continue
            characters.append(character)
            self._advance()
        self._fail("unterminated string literal", start_line, start_column)

    def _escape(self, start_line: int, start_column: int) -> str:
        """Decode one backslash escape sequence.

        Parameters
        ----------
        start_line : int
            One-based line where the surrounding string starts.
        start_column : int
            One-based column where the surrounding string starts.

        Returns
        -------
        str
            Decoded escape character.

        Raises
        ------
        QuerySyntaxError
            If the escape is unterminated or unsupported.
        """
        if self._at_end():
            self._fail("unterminated string literal", start_line, start_column)
        character = self._advance()
        if character != "u":
            decoded = self.ESCAPES.get(character)
            if decoded is None:
                self._fail(f"invalid string escape '\\{character}'", self._line, self._column)
            return decoded
        digits = "".join(
            self._advance() for _ in range(self.UNICODE_ESCAPE_LENGTH) if not self._at_end()
        )
        if len(digits) != self.UNICODE_ESCAPE_LENGTH or any(
            digit not in self.HEX_DIGITS for digit in digits
        ):
            self._fail("invalid unicode escape", self._line, self._column)
        return chr(int(digits, 16))

    def _number(
        self,
        start_offset: int,
        start_line: int,
        start_column: int,
    ) -> Token:
        """Scan an integer or float literal.

        Parameters
        ----------
        start_offset : int
            Zero-based offset where the token starts.
        start_line : int
            One-based line where the token starts.
        start_column : int
            One-based column where the token starts.

        Returns
        -------
        Token
            Numeric token.

        Raises
        ------
        QuerySyntaxError
            If the literal is malformed.
        """
        is_float = False
        while not self._at_end() and self._peek().isdigit():
            self._advance()
        if self._peek() == "." and self._peek(1) != ".":
            if not self._peek(1).isdigit():
                self._fail("invalid numeric literal", start_line, start_column)
            is_float = True
            self._advance()
            while not self._at_end() and self._peek().isdigit():
                self._advance()
        if self._peek() in {"e", "E"}:
            is_float = True
            self._advance()
            if self._peek() in {"+", "-"}:
                self._advance()
            if not self._peek().isdigit():
                self._fail("invalid numeric literal", start_line, start_column)
            while not self._at_end() and self._peek().isdigit():
                self._advance()
        if self._peek() in self.IDENTIFIER_BODY or (self._peek() == "." and self._peek(1) != "."):
            self._fail("invalid numeric literal", start_line, start_column)
        text = self._text[start_offset : self._offset]
        kind = TokenKind.FLOAT if is_float else TokenKind.INTEGER
        value: int | float = float(text) if is_float else int(text)
        return self._token(kind, value, start_offset, start_line, start_column)

    def _parameter(
        self,
        start_offset: int,
        start_line: int,
        start_column: int,
    ) -> Token:
        """Scan a ``$name`` parameter.

        Parameters
        ----------
        start_offset : int
            Zero-based offset where the token starts.
        start_line : int
            One-based line where the token starts.
        start_column : int
            One-based column where the token starts.

        Returns
        -------
        Token
            Parameter token whose value is the name without ``$``.

        Raises
        ------
        QuerySyntaxError
            If no valid parameter name follows the dollar sign.
        """
        self._advance()
        if self._peek() not in self.IDENTIFIER_START:
            self._fail("invalid parameter name", start_line, start_column)
        while not self._at_end() and self._peek() in self.IDENTIFIER_BODY:
            self._advance()
        name = self._text[start_offset + 1 : self._offset]
        return self._token(TokenKind.PARAMETER, name, start_offset, start_line, start_column)

    def _token(
        self,
        kind: TokenKind,
        value: str | int | float,
        start_offset: int,
        start_line: int,
        start_column: int,
    ) -> Token:
        """Build one token covering the text consumed since its start.

        Parameters
        ----------
        kind : TokenKind
            Category of the token.
        value : str | int | float
            Decoded token value.
        start_offset : int
            Zero-based offset where the token starts.
        start_line : int
            One-based line where the token starts.
        start_column : int
            One-based column where the token starts.

        Returns
        -------
        Token
            The constructed token.
        """
        return Token(
            kind=kind,
            value=value,
            text=self._text[start_offset : self._offset],
            span=Span(
                line=start_line,
                column=start_column,
                offset=start_offset,
                end=self._offset,
            ),
        )

    def _match(self, text: str) -> bool:
        """Consume the given text when it is the next source text.

        Parameters
        ----------
        text : str
            Exact text to match.

        Returns
        -------
        bool
            ``True`` when the text was present and consumed.
        """
        if not self._text.startswith(text, self._offset):
            return False
        for _ in text:
            self._advance()
        return True

    def _peek(self, distance: int = 0) -> str:
        """Return an upcoming character without consuming it.

        Parameters
        ----------
        distance : int, optional
            Offset from the current position, by default zero.

        Returns
        -------
        str
            The character, or the empty string past the end.
        """
        index = self._offset + distance
        if index >= self._length:
            return ""
        return self._text[index]

    def _advance(self) -> str:
        """Consume one character and update the source position.

        Returns
        -------
        str
            The consumed character.
        """
        character = self._text[self._offset]
        self._offset += 1
        if character == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return character

    def _at_end(self) -> bool:
        """Report whether the scanner reached the end of input.

        Returns
        -------
        bool
            ``True`` at the end of the source text.
        """
        return self._offset >= self._length

    @staticmethod
    def _fail(message: str, line: int, column: int) -> typing.Never:
        """Raise a positioned syntax error.

        Parameters
        ----------
        message : str
            Description of the failure.
        line : int
            One-based source line.
        column : int
            One-based source column.

        Raises
        ------
        QuerySyntaxError
            Always.
        """
        raise QuerySyntaxError(message, line=line, column=column)
