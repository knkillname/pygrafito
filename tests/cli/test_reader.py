# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for statement boundaries and dot-command parsing."""

from pygrafito.cli.reader import StatementReader


class TestStatementSplit:
    """Verify semicolon boundaries outside literals and comments."""

    def test_one_terminated_statement(self) -> None:
        split = StatementReader.split("MATCH (n) RETURN n;")
        assert split.statements == ("MATCH (n) RETURN n",)
        assert split.pending == ""

    def test_several_statements_on_one_line(self) -> None:
        split = StatementReader.split("CREATE (n:Program); CREATE (m:Program);")
        assert split.statements == ("CREATE (n:Program)", " CREATE (m:Program)")
        assert split.pending == ""

    def test_statement_spans_lines(self) -> None:
        split = StatementReader.split("MATCH (n:Program)\nRETURN n\n")
        assert split.statements == ()
        assert split.pending == "MATCH (n:Program)\nRETURN n\n"
        split = StatementReader.split(split.pending + ";")
        assert split.statements == ("MATCH (n:Program)\nRETURN n\n",)

    def test_pending_after_terminator(self) -> None:
        split = StatementReader.split("CREATE (n:Program); MATCH (n)")
        assert split.statements == ("CREATE (n:Program)",)
        assert split.pending == " MATCH (n)"

    def test_whitespace_and_comment_pending_is_empty(self) -> None:
        assert StatementReader.split("  \n").pending == ""
        assert StatementReader.split("// nothing\n").pending == ""
        assert StatementReader.split("/* nothing */\n").pending == ""

    def test_empty_statements_are_skipped(self) -> None:
        split = StatementReader.split(";; ;")
        assert split.statements == ()
        assert split.pending == ""

    def test_comment_only_statement_is_skipped(self) -> None:
        split = StatementReader.split("/* setup */;")
        assert split.statements == ()

    def test_semicolon_in_single_quoted_string(self) -> None:
        split = StatementReader.split("CREATE (n:Program {designation: 'Tron;Rinzler'});")
        assert split.statements == ("CREATE (n:Program {designation: 'Tron;Rinzler'})",)
        assert split.pending == ""

    def test_semicolon_in_double_quoted_string(self) -> None:
        split = StatementReader.split('CREATE (n:Program {designation: "a;b"});')
        assert len(split.statements) == 1

    def test_escaped_quote_in_string(self) -> None:
        split = StatementReader.split("CREATE (n:Program {designation: 'Tron\\'s'});")
        assert len(split.statements) == 1
        assert split.pending == ""

    def test_semicolon_in_quoted_identifier(self) -> None:
        split = StatementReader.split("CREATE (n:Program {`a;b`: 1});")
        assert len(split.statements) == 1

    def test_doubled_backtick_in_identifier(self) -> None:
        split = StatementReader.split("CREATE (n:Program {`a``b;c`: 1});")
        assert len(split.statements) == 1

    def test_semicolon_in_line_comment(self) -> None:
        split = StatementReader.split("// a; b\nCREATE (n:Program);")
        assert split.statements == ("// a; b\nCREATE (n:Program)",)

    def test_semicolon_in_block_comment(self) -> None:
        split = StatementReader.split("/* a; b */ CREATE (n:Program);")
        assert split.statements == ("/* a; b */ CREATE (n:Program)",)

    def test_unterminated_string_stays_pending(self) -> None:
        split = StatementReader.split("CREATE (n:Program {designation: 'Tron);")
        assert split.statements == ()
        assert split.pending == "CREATE (n:Program {designation: 'Tron);"

    def test_unterminated_block_comment_swallows_terminator(self) -> None:
        split = StatementReader.split("CREATE (n:Program) /* note")
        assert split.statements == ()
        assert split.pending == "CREATE (n:Program) /* note"


class TestCommandParsing:
    """Verify dot-command recognition and argument splitting."""

    def test_bare_command(self) -> None:
        assert StatementReader.parse_command(".help") == ("help", "")

    def test_command_with_argument(self) -> None:
        assert StatementReader.parse_command(".mode table") == ("mode", "table")

    def test_command_with_extra_spaces(self) -> None:
        assert StatementReader.parse_command("   .node   42  ") == ("node", "42")

    def test_command_argument_keeps_inner_spaces(self) -> None:
        assert StatementReader.parse_command(".explain MATCH (n) RETURN n") == (
            "explain",
            "MATCH (n) RETURN n",
        )

    def test_dot_alone_is_an_empty_name(self) -> None:
        assert StatementReader.parse_command(".") == ("", "")

    def test_statement_is_not_a_command(self) -> None:
        assert StatementReader.parse_command("MATCH (n) RETURN n;") is None

    def test_leading_whitespace_still_a_command(self) -> None:
        assert StatementReader.parse_command("\t.mode csv") == ("mode", "csv")

    def test_dot_inside_a_line_is_not_a_command(self) -> None:
        assert StatementReader.parse_command("MATCH (n) .mode csv") is None
