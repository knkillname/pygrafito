# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the interactive loop, scripts, and failure handling."""

import io
import typing
from pathlib import Path

from pygrafito import Graph, QueryResult
from pygrafito.cli.formatting import OutputMode
from pygrafito.cli.session import Session
from pygrafito.cli.shell import Shell
from tests.cli.support import Fixtures, Harness


class _InterruptingInput(io.StringIO):
    """Input stream that interrupts once before returning its text."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._pending_interrupt = True

    @typing.override
    def readline(self, size: int = -1) -> str:
        if self._pending_interrupt:
            self._pending_interrupt = False
            raise KeyboardInterrupt
        return super().readline(size)


class _InterruptingSession(Session):
    """Session whose statement execution is interrupted."""

    @typing.override
    def execute(self, text: str) -> QueryResult:
        raise KeyboardInterrupt


class TestInteractive:
    """Verify prompts, banner, continuation, and quitting."""

    def test_multiline_statement_and_quit(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        harness = Harness(path, interactive=True)
        try:
            code, output, error = harness.run_interactive(
                "MATCH (n:Program)\nRETURN count(*) AS total;\n.quit\n"
            )
        finally:
            harness.close()

        assert code == 0
        assert "| total |" in output
        assert "pygrafito" in error
        assert "...> " in error
        assert "1 row" in error

    def test_bare_quit(self) -> None:
        harness = Harness(interactive=True)
        try:
            code, _, _ = harness.run_interactive(".quit\n")
        finally:
            harness.close()
        assert code == 0

    def test_end_of_input_exits_zero(self) -> None:
        harness = Harness(interactive=True)
        try:
            code, output, _ = harness.run_interactive("")
        finally:
            harness.close()
        assert code == 0
        assert output == ""

    def test_quiet_hides_the_banner(self) -> None:
        harness = Harness(interactive=True, quiet=True)
        try:
            _, _, error = harness.run_interactive(".quit\n")
        finally:
            harness.close()
        assert "pygrafito" not in error

    def test_pending_statement_at_end_of_script(self) -> None:
        harness = Harness()
        try:
            code, _, _ = harness.run("CREATE (n:Program {designation: 'Tron'})")
            total = harness.session.execute("MATCH (n:Program) RETURN count(*) AS total").rows[0][
                "total"
            ]
        finally:
            harness.close()
        assert code == 0
        assert total == 1

    def test_end_of_input_flushes_pending_statement(self) -> None:
        harness = Harness(interactive=True)
        try:
            code, output, _ = harness.run_interactive("CREATE (n:Program)")
            total = harness.session.execute("MATCH (n:Program) RETURN count(*) AS total").rows[0][
                "total"
            ]
            in_transaction = harness.session.in_transaction
        finally:
            harness.close()

        assert code == 0
        assert in_transaction is False
        assert output == ""
        assert total == 1

    def test_interrupt_at_prompt_clears_the_buffer(self) -> None:
        harness = Harness(interactive=True)
        harness.shell = Shell(
            harness.session,
            input=_InterruptingInput("MATCH (n)\n.quit\n"),
            error=harness.error,
        )
        try:
            code = harness.shell.run()
        finally:
            harness.close()
        assert code == 0

    def test_dot_line_inside_statement_is_text(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        harness = Harness(path, interactive=True)
        try:
            _, output, error = harness.run_interactive("MATCH (n:Program)\n.mode csv;\n.quit\n")
        finally:
            harness.close()

        assert "error:" in error
        assert "|" not in output

    def test_interrupt_during_statement_keeps_session_usable(self) -> None:
        output = io.StringIO()
        error = io.StringIO()
        session = _InterruptingSession(
            mode=OutputMode.TABLE,
            headers=True,
            timer=False,
            quiet=False,
            interactive=True,
            readonly=False,
            output=output,
            error=error,
        )
        session.open_database(None)
        shell = Shell(session, input=io.StringIO("MATCH (n) RETURN n;\n.quit\n"), error=error)
        try:
            code = shell.run()
            assert session.in_transaction is False
        finally:
            session.finish()

        assert code == 0
        assert "interrupted" in error.getvalue()

    def test_script_interrupt_returns_failure(self) -> None:
        output = io.StringIO()
        error = io.StringIO()
        session = _InterruptingSession(
            mode=OutputMode.TABLE,
            headers=True,
            timer=False,
            quiet=False,
            interactive=False,
            readonly=False,
            output=output,
            error=error,
        )
        session.open_database(None)
        shell = Shell(session, input=io.StringIO(), error=error)
        try:
            code = shell.run_script("MATCH (n) RETURN n;")
        finally:
            session.finish()

        assert code == 1
        assert "interrupted" in error.getvalue()


class TestScripts:
    """Verify fail-fast execution, statement positions, and silence."""

    def test_success(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        harness = Harness(path)
        try:
            code, output, error = harness.run(
                "CREATE (n:Program {designation: 'Tron'});\n"
                "MATCH (n:Program) RETURN n.designation AS name;\n"
            )
        finally:
            harness.close()

        assert code == 0
        assert "Tron" in output
        assert error == ""

    def test_failure_stops_the_script(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        harness = Harness(path)
        try:
            code, _, error = harness.run(
                "CREATE (n:Program {designation: 'Tron'});\n"
                "MATCH (n) RETURN missing;\n"
                "CREATE (m:Program {designation: 'Clu'});\n"
            )
        finally:
            harness.close()

        assert code == 1
        assert "error: statement 2:" in error
        with Graph.open(path) as graph:
            names = sorted(node["designation"] for node in graph.find_nodes("Program"))
        assert names == ["Tron"]

    def test_syntax_error_reports_position(self) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run("MATCH (n RETURN n;")
        finally:
            harness.close()

        assert code == 1
        assert "statement 1" in error
        assert "line 1, column" in error

    def test_unreadable_script(self, tmp_path: Path) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run(".read /missing/script.cypher\n")
        finally:
            harness.close()

        assert code == 1
        assert "error:" in error

    def test_read_inside_transaction(self, tmp_path: Path) -> None:
        script = tmp_path / "seed.cypher"
        script.write_text("CREATE (n:Program {designation: 'Rinzler'});\n", encoding="utf-8")
        harness = Harness()
        try:
            code, _, error = harness.run(f".begin\n.read {script}\n.rollback\n")
            total = harness.session.execute("MATCH (n:Program) RETURN count(*) AS total").rows[0][
                "total"
            ]
        finally:
            harness.close()

        assert code == 0
        assert error == ""
        assert total == 0

    def test_output_redirection_in_script(self, tmp_path: Path) -> None:
        destination = tmp_path / "result.txt"
        harness = Harness()
        try:
            code, _, _ = harness.run(
                f".mode json\n.output {destination}\n"
                "CREATE (n:Program {designation: 'Tron'});\n"
                "MATCH (n:Program) RETURN n.designation AS name;\n"
                ".output off\n"
            )
        finally:
            harness.close()

        assert code == 0
        assert '"name": "Tron"' in destination.read_text(encoding="utf-8")
