# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for session state and execution routing."""

from pathlib import Path

import pytest

from pygrafito import Graph, QueryResult, Row, TransactionError, ValidationError
from pygrafito.cli.session import ParameterDecoder
from tests.cli.support import Harness


class TestExecutionRouting:
    """Verify statements use the active transaction or the graph."""

    def test_uncommitted_write_is_visible_then_rolled_back(self) -> None:
        harness = Harness()
        try:
            harness.session.begin()
            harness.session.execute("CREATE (n:Program {designation: 'Tron'})")
            visible = harness.session.execute("MATCH (n:Program) RETURN count(*) AS total")
            assert visible.rows[0]["total"] == 1

            harness.session.rollback()
            after = harness.session.execute("MATCH (n:Program) RETURN count(*) AS total")
            assert after.rows[0]["total"] == 0
        finally:
            harness.close()

    def test_commit_persists(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        harness = Harness(path)
        try:
            harness.session.begin()
            harness.session.execute("CREATE (n:Program {designation: 'Quorra'})")
            harness.session.commit()
        finally:
            harness.close()

        with Graph.open(path) as graph:
            assert graph.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"] == 1

    def test_commit_without_transaction(self) -> None:
        harness = Harness()
        try:
            with pytest.raises(TransactionError):
                harness.session.commit()
        finally:
            harness.close()


class TestParameters:
    """Verify parameter storage and decoding."""

    def test_decode_string_number_and_list(self) -> None:
        assert ParameterDecoder.decode('name="Quorra"') == ("name", "Quorra")
        assert ParameterDecoder.decode("cycles=37") == ("cycles", 37)
        assert ParameterDecoder.decode("ids=[1, 2]") == ("ids", [1, 2])

    def test_decode_rejects_malformed_name(self) -> None:
        with pytest.raises(ValidationError):
            ParameterDecoder.decode('1name="Quorra"')

    def test_decode_rejects_missing_value(self) -> None:
        with pytest.raises(ValidationError):
            ParameterDecoder.decode("name")

    def test_decode_rejects_non_finite_numbers(self) -> None:
        with pytest.raises(ValidationError):
            ParameterDecoder.decode("value=NaN")
        with pytest.raises(ValidationError):
            ParameterDecoder.decode("value=Infinity")

    def test_session_parameters_are_copied(self) -> None:
        harness = Harness()
        try:
            harness.session.set_parameter("name", "Tron")
            parameters = harness.session.parameters()
            parameters["name"] = "Clu"
            assert harness.session.parameters() == {"name": "Tron"}
        finally:
            harness.close()


class TestOutputState:
    """Verify redirection, prompts, and the banner."""

    def test_redirect_and_restore(self, tmp_path: Path) -> None:
        path = tmp_path / "out.txt"
        harness = Harness()
        try:
            harness.session.set_output(str(path))
            harness.session.emit("in the file")
            harness.session.set_output(None)
            harness.session.emit("on stdout")
        finally:
            harness.close()

        assert path.read_text(encoding="utf-8") == "in the file\n"
        assert harness.output.getvalue() == "on stdout\n"

    def test_once_applies_to_one_output(self, tmp_path: Path) -> None:
        path = tmp_path / "once.txt"
        harness = Harness()
        try:
            harness.session.set_once(str(path))
            harness.session.emit("first")
            harness.session.emit("second")
        finally:
            harness.close()

        assert path.read_text(encoding="utf-8") == "first\n"
        assert harness.output.getvalue() == "second\n"

    def test_failed_redirection_keeps_target(self, tmp_path: Path) -> None:
        path = tmp_path / "out.txt"
        harness = Harness()
        try:
            harness.session.set_output(str(path))
            with pytest.raises(IsADirectoryError):
                harness.session.set_output(str(tmp_path))
            harness.session.emit("still redirected")
        finally:
            harness.close()

        assert path.read_text(encoding="utf-8") == "still redirected\n"

    def test_prompt_reports_transaction(self) -> None:
        harness = Harness()
        try:
            assert harness.session.prompt() == ":memory:> "
            harness.session.begin()
            assert harness.session.prompt() == ":memory:*> "
            harness.session.rollback()
        finally:
            harness.close()

    def test_banner_reports_read_only(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            graph.add_node("Program", designation="Tron")
        harness = Harness(path, readonly=True)
        try:
            assert "read-only" in harness.session.banner()
        finally:
            harness.close()

    def test_finish_rolls_back_and_warns(self) -> None:
        harness = Harness()
        harness.session.begin()
        harness.session.execute("CREATE (n:Program {designation: 'Tron'})")
        harness.close()
        error = harness.error.getvalue()
        assert "rolled back an open transaction" in error


class TestFooters:
    """Verify interactive row counts, mutation summaries, and timing."""

    @staticmethod
    def result() -> QueryResult:
        columns = ("name",)
        return QueryResult(
            columns=columns,
            rows=(Row(columns=columns, row_values=("Quorra",)),),
        )

    def test_row_count_and_timing(self) -> None:
        harness = Harness(interactive=True)
        try:
            harness.session.set_timer(True)
            harness.session.report_footer(1, self.result(), 0.0015)
        finally:
            harness.close()
        assert "1 row, 1.5 ms" in harness.error.getvalue()

    def test_non_interactive_is_silent(self) -> None:
        harness = Harness()
        try:
            harness.session.report_footer(1, self.result(), 0.0015)
        finally:
            harness.close()
        assert harness.error.getvalue() == ""

    def test_quiet_is_silent(self) -> None:
        harness = Harness(interactive=True, quiet=True)
        try:
            harness.session.report_footer(1, self.result(), 0.0015)
        finally:
            harness.close()
        assert harness.error.getvalue() == ""

    def test_mutation_summary(self) -> None:
        harness = Harness(interactive=True)
        try:
            code, _, error = harness.run("CREATE (n:Program {designation: 'Tron'});")
            assert code == 0
            assert "1 node created" in error
        finally:
            harness.close()
