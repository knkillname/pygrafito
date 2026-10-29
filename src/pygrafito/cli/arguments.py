# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Split shell dot-command arguments with platform-aware path rules."""

import os
import shlex
import typing


class CommandArguments:
    r"""Split dot-command argument text into values.

    POSIX hosts keep the existing shell-like parsing, including backslash
    escapes. Windows hosts treat backslashes as ordinary path characters so a
    native path such as ``C:\grid\snapshot.jsonl`` survives unchanged.
    """

    WINDOWS: typing.ClassVar[bool] = os.name == "nt"
    QUOTES: typing.ClassVar[frozenset[str]] = frozenset({'"', "'"})
    QUOTED_PAIR_LENGTH: typing.ClassVar[int] = 2

    @classmethod
    def split(cls, text: str, *, windows: bool | None = None) -> list[str]:
        """Split one argument string into parts.

        Parameters
        ----------
        text : str
            Raw argument text after a dot-command name.
        windows : bool | None, optional
            Whether to use Windows path rules, by default the host platform.

        Returns
        -------
        list[str]
            Parsed argument parts without their surrounding quotes.

        Raises
        ------
        ValueError
            If a quote is not closed.
        """
        use_windows = cls.WINDOWS if windows is None else windows
        if not use_windows:
            return shlex.split(text)
        return cls._split_windows(text)

    @classmethod
    def path(cls, text: str) -> str:
        """Return one path argument while preserving native separators.

        A single pair of matching quotes is removed. Unquoted spaces and
        backslashes stay part of the path, so an existing POSIX invocation is
        unchanged and a Windows path does not lose its separators.

        Parameters
        ----------
        text : str
            Raw argument text after a dot-command name.

        Returns
        -------
        str
            The path value, or an empty string when the argument is empty.

        Raises
        ------
        ValueError
            If the argument opens a quote that it does not close.
        """
        stripped = text.strip()
        if not stripped:
            return ""
        first = stripped[0]
        if first in cls.QUOTES:
            if len(stripped) < cls.QUOTED_PAIR_LENGTH or stripped[-1] != first:
                raise ValueError("No closing quotation")
            return stripped[1:-1]
        return stripped

    @classmethod
    def _split_windows(cls, text: str) -> list[str]:
        """Split one argument string with Windows path rules.

        Whitespace separates arguments outside quotes. Backslashes are always
        literal. A doubled quote inside a quoted segment produces one literal
        quote, matching the usual command-line convention.

        Parameters
        ----------
        text : str
            Raw argument text after a dot-command name.

        Returns
        -------
        list[str]
            Parsed argument parts.

        Raises
        ------
        ValueError
            If a quote is not closed.
        """
        parts: list[str] = []
        current: list[str] = []
        started = False
        quote: str | None = None
        index = 0
        while index < len(text):
            char = text[index]
            if quote is None:
                if char.isspace():
                    if started:
                        parts.append("".join(current))
                        current = []
                        started = False
                elif char in cls.QUOTES:
                    quote = char
                    started = True
                else:
                    current.append(char)
                    started = True
            elif char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    current.append(quote)
                    index += 1
                else:
                    quote = None
            else:
                current.append(char)
            index += 1
        if quote is not None:
            raise ValueError("No closing quotation")
        if started:
            parts.append("".join(current))
        return parts
