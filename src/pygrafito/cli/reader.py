# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Statement boundaries and dot-command detection for the graph shell."""

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class Split:
    """Complete statements and the text that is not yet terminated.

    Parameters
    ----------
    statements : tuple[str, ...]
        Complete statements, in source order, without their terminators.
    pending : str
        Text after the last terminator that still needs input.
    """

    statements: tuple[str, ...]
    pending: str


class StatementReader:
    """Split shell input on semicolons outside literals and comments.

    The reader only finds statement boundaries; it does not validate syntax.
    It recognizes single- and double-quoted strings with backslash escapes,
    backtick identifiers with doubled backticks, ``//`` line comments, and
    ``/* ... */`` block comments, so a semicolon in any of those regions is
    ordinary text.
    """

    QUOTES: frozenset[str] = frozenset({"'", '"'})
    BACKTICK: str = "`"

    @classmethod
    def split(cls, text: str) -> Split:
        """Split input into complete statements and a pending remainder.

        Parameters
        ----------
        text : str
            Accumulated shell input.

        Returns
        -------
        Split
            Complete statements and the unterminated remainder. A remainder
            that contains only whitespace or comments is empty.
        """
        statements: list[str] = []
        start = 0
        has_code = False
        index = 0
        length = len(text)
        while index < length:
            character = text[index]
            pair = text[index : index + 2]
            if pair == "//":
                newline = text.find("\n", index)
                index = length if newline == -1 else newline
                continue
            if pair == "/*":
                end = text.find("*/", index + 2)
                index = length if end == -1 else end + 2
                continue
            if character in cls.QUOTES:
                has_code = True
                index = cls._string_end(text, index, character)
                continue
            if character == cls.BACKTICK:
                has_code = True
                index = cls._backtick_end(text, index)
                continue
            if character == ";":
                if has_code:
                    statements.append(text[start:index])
                start = index + 1
                has_code = False
                index += 1
                continue
            if not character.isspace():
                has_code = True
            index += 1
        remainder = text[start:] if has_code else ""
        return Split(tuple(statements), remainder)

    @classmethod
    def parse_command(cls, line: str) -> tuple[str, str] | None:
        """Parse a dot-command line.

        Parameters
        ----------
        line : str
            One input line, with or without a trailing newline.

        Returns
        -------
        tuple[str, str] | None
            Command name without the leading dot and its argument, or ``None``
            when the line is not a dot-command.
        """
        stripped = line.strip()
        if not stripped.startswith("."):
            return None
        parts = stripped[1:].split(maxsplit=1)
        if not parts:
            return ("", "")
        name = parts[0]
        argument = parts[1].strip() if len(parts) > 1 else ""
        return (name, argument)

    @classmethod
    def _string_end(cls, text: str, index: int, quote: str) -> int:
        """Find the first index after a string literal.

        Parameters
        ----------
        text : str
            Source text.
        index : int
            Index of the opening quote.
        quote : str
            Quote character that opened the literal.

        Returns
        -------
        int
            Index after the closing quote, or the end of the text when the
            literal is unterminated.
        """
        index += 1
        while index < len(text):
            character = text[index]
            if character == "\\":
                index += 2
                continue
            if character == quote:
                return index + 1
            index += 1
        return len(text)

    @classmethod
    def _backtick_end(cls, text: str, index: int) -> int:
        """Find the first index after a backtick-quoted identifier.

        Parameters
        ----------
        text : str
            Source text.
        index : int
            Index of the opening backtick.

        Returns
        -------
        int
            Index after the closing backtick, or the end of the text when the
            identifier is unterminated.
        """
        index += 1
        while index < len(text):
            if text[index] == cls.BACKTICK:
                if index + 1 < len(text) and text[index + 1] == cls.BACKTICK:
                    index += 2
                    continue
                return index + 1
            index += 1
        return len(text)
