# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for platform-aware dot-command argument parsing."""

import pytest

from pygrafito.cli.arguments import CommandArguments


class TestWindowsSplitting:
    """Verify native Windows paths survive dot-command parsing."""

    def test_unquoted_drive_path_is_one_value(self) -> None:
        parts = CommandArguments.split(r"C:\grid\snapshot.jsonl", windows=True)
        assert parts == [r"C:\grid\snapshot.jsonl"]

    def test_quoted_path_with_spaces_is_one_value(self) -> None:
        parts = CommandArguments.split(r'"C:\Grid Files\backup.db"', windows=True)
        assert parts == [r"C:\Grid Files\backup.db"]

    def test_import_keeps_the_statement_quoted(self) -> None:
        text = (
            r'"C:\Grid Files\programs.csv" --statement '
            r'"UNWIND $rows AS row CREATE (n:Program {name: row.name})"'
        )
        parts = CommandArguments.split(text, windows=True)
        assert parts == [
            r"C:\Grid Files\programs.csv",
            "--statement",
            "UNWIND $rows AS row CREATE (n:Program {name: row.name})",
        ]

    def test_export_options_are_split(self) -> None:
        parts = CommandArguments.split(r"C:\grid\snapshot.jsonl --overwrite", windows=True)
        assert parts == [r"C:\grid\snapshot.jsonl", "--overwrite"]

    def test_doubled_quote_is_literal(self) -> None:
        parts = CommandArguments.split('"a""b"', windows=True)
        assert parts == ['a"b']

    def test_unclosed_quote_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="closing quotation"):
            CommandArguments.split(r'"C:\Grid Files', windows=True)


class TestPosixSplitting:
    """Verify the existing POSIX parsing is unchanged."""

    def test_backslashes_remain_escapes(self) -> None:
        parts = CommandArguments.split(r"C:\grid\snapshot.jsonl", windows=False)
        assert parts == ["C:gridsnapshot.jsonl"]

    def test_quoted_path_with_spaces(self) -> None:
        parts = CommandArguments.split("'grid files/backup.db'", windows=False)
        assert parts == ["grid files/backup.db"]

    def test_statement_keeps_single_quoted_literals(self) -> None:
        text = "programs.csv --statement \"UNWIND $rows AS row CREATE (n {name: 'Tron'})\""
        parts = CommandArguments.split(text, windows=False)
        assert parts == [
            "programs.csv",
            "--statement",
            "UNWIND $rows AS row CREATE (n {name: 'Tron'})",
        ]


class TestSinglePath:
    """Verify single path arguments keep native separators and spaces."""

    def test_plain_path_is_unchanged(self) -> None:
        assert CommandArguments.path(r"C:\grid\snapshot.jsonl") == (r"C:\grid\snapshot.jsonl")

    def test_unquoted_spaces_stay_in_the_path(self) -> None:
        assert CommandArguments.path("/tmp/Grid Files/backup.db") == ("/tmp/Grid Files/backup.db")

    def test_quoted_path_loses_only_the_quotes(self) -> None:
        assert CommandArguments.path(r'"C:\Grid Files\backup.db"') == (r"C:\Grid Files\backup.db")

    def test_single_quoted_path_loses_only_the_quotes(self) -> None:
        assert CommandArguments.path("'Grid Files/backup.db'") == "Grid Files/backup.db"

    def test_empty_argument_is_empty(self) -> None:
        assert CommandArguments.path("  ") == ""

    def test_unclosed_quote_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="closing quotation"):
            CommandArguments.path('"C:\\Grid Files')
