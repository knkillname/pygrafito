# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for process wiring, arguments, exit codes, and streams."""

import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from pygrafito import Graph
from pygrafito.cli.app import App


class Runner:
    """Run the shell as a subprocess."""

    @staticmethod
    def run(
        *arguments: str,
        input_text: str | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Invoke ``python -m pygrafito``.

        Parameters
        ----------
        *arguments : str
            Command-line arguments.
        input_text : str | None, optional
            Standard input, by default none.
        cwd : Path | None, optional
            Working directory, by default the current one.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Completed process with captured streams.
        """
        return subprocess.run(
            [sys.executable, "-m", "pygrafito", *arguments],
            capture_output=True,
            text=True,
            input=input_text,
            cwd=cwd,
            check=False,
        )


class TestArguments:
    """Verify parsed options and their effects."""

    def test_command_runs(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = App.main(
            [
                ":memory:",
                "-c",
                "CREATE (n:Program {designation: 'Tron'}) RETURN n.designation AS name;",
            ]
        )
        captured = capsys.readouterr()
        assert code == 0
        assert "Tron" in captured.out

    def test_no_database_is_transient(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = App.main(["-c", "CREATE (n:Program {designation: 'Tron'});"])
        assert code == 0
        assert capsys.readouterr().out == ""

    def test_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as stopped:
            App.main(["--help"])
        assert stopped.value.code == 0
        assert "usage: pygrafito" in capsys.readouterr().out

    def test_unknown_option_exits_two(self) -> None:
        with pytest.raises(SystemExit) as stopped:
            App.main(["--bogus"])
        assert stopped.value.code == 2

    def test_command_and_file_are_exclusive(self, tmp_path: Path) -> None:
        script = tmp_path / "script.cypher"
        script.write_text("MATCH (n) RETURN n;", encoding="utf-8")
        with pytest.raises(SystemExit) as stopped:
            App.main(["-c", "MATCH (n) RETURN n;", "-f", str(script)])
        assert stopped.value.code == 2

    def test_format_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = App.main(
            [
                "--format",
                "json",
                "-c",
                "CREATE (n:Program {designation: 'Quorra'}) RETURN n.designation AS name;",
                ":memory:",
            ]
        )
        assert code == 0
        assert '"name": "Quorra"' in capsys.readouterr().out

    def test_parameter_binding(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = App.main(
            [
                "--param",
                'name="Quorra"',
                "--param",
                "cycles=37",
                "-c",
                "CREATE (n:Program {designation: $name, cycles: $cycles}) "
                "RETURN n.designation AS name;",
                ":memory:",
            ]
        )
        assert code == 0
        assert "Quorra" in capsys.readouterr().out

    def test_parameters_apply_to_every_statement(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = App.main(
            [
                "--param",
                'name="Quorra"',
                "-c",
                "CREATE (n:Program {designation: $name}); CREATE (m:Program {designation: $name});",
                ":memory:",
            ]
        )
        assert code == 0
        assert capsys.readouterr().err == ""

    def test_malformed_parameter_exits_two(self) -> None:
        with pytest.raises(SystemExit) as stopped:
            App.main(["--param", "name", "-c", "MATCH (n) RETURN n;", ":memory:"])
        assert stopped.value.code == 2

    def test_readonly_without_database_exits_two(self) -> None:
        with pytest.raises(SystemExit) as stopped:
            App.main(["--readonly", "-c", "MATCH (n) RETURN n;"])
        assert stopped.value.code == 2


class TestFailures:
    """Verify runtime failures and their exit codes."""

    def test_query_error_exits_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = App.main([":memory:", "-c", "MATCH (n) RETURN missing;"])
        captured = capsys.readouterr()
        assert code == 1
        assert "error:" in captured.err
        assert captured.out == ""

    def test_unreadable_script_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = App.main(["-f", str(tmp_path / "missing.cypher"), ":memory:"])
        captured = capsys.readouterr()
        assert code == 1
        assert "error:" in captured.err

    def test_readonly_missing_file_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = App.main(
            [
                "--readonly",
                "-c",
                "MATCH (n) RETURN n;",
                str(tmp_path / "missing.db"),
            ]
        )
        captured = capsys.readouterr()
        assert code == 1
        assert "does not exist" in captured.err
        assert not (tmp_path / "missing.db").exists()


class TestSubprocess:
    """Verify the module entry point and piped input."""

    def test_module_help(self) -> None:
        completed = Runner.run("--help")
        assert completed.returncode == 0
        assert "usage: pygrafito" in completed.stdout

    def test_piped_script(self, tmp_path: Path) -> None:
        database = tmp_path / "grid.db"
        completed = Runner.run(
            str(database),
            input_text=(
                "CREATE (n:Program {designation: 'Tron'});\n"
                "MATCH (n:Program) RETURN n.designation AS name;\n"
                ".schema\n"
                ".quit\n"
            ),
        )
        assert completed.returncode == 0, completed.stderr
        assert "Tron" in completed.stdout
        assert "Labels" in completed.stdout
        assert "pygrafito" not in completed.stdout
        assert completed.stderr == ""
        with Graph.open(database) as graph:
            assert graph.query("MATCH (n:Program) RETURN count(*) AS t").rows[0]["t"] == 1

    def test_script_file(self, tmp_path: Path) -> None:
        database = tmp_path / "grid.db"
        script = tmp_path / "seed.cypher"
        script.write_text(
            "CREATE (n:Program {designation: 'Quorra'});\n"
            "MATCH (n:Program) RETURN n.designation AS name;\n",
            encoding="utf-8",
        )
        completed = Runner.run(str(database), "-f", str(script))
        assert completed.returncode == 0, completed.stderr
        assert "Quorra" in completed.stdout

    def test_script_failure_stops(self, tmp_path: Path) -> None:
        database = tmp_path / "grid.db"
        completed = Runner.run(
            str(database),
            input_text=("MATCH (n) RETURN missing;\nCREATE (n:Program {designation: 'Clu'});\n"),
        )
        assert completed.returncode == 1
        assert "statement 1" in completed.stderr
        with Graph.open(database) as graph:
            assert graph.query("MATCH (n) RETURN count(*) AS t").rows[0]["t"] == 0

    def test_json_output_is_clean(self, tmp_path: Path) -> None:
        completed = Runner.run(
            ":memory:",
            "--format",
            "json",
            "-c",
            "CREATE (n:Program {designation: 'Tron'}) RETURN n.designation AS name;",
        )
        assert completed.returncode == 0
        assert completed.stdout.startswith("[")
        assert completed.stderr == ""

    def test_console_script_is_declared(self) -> None:
        scripts = entry_points(group="console_scripts")
        matching = [script for script in scripts if script.name == "pygrafito"]
        assert matching
        assert matching[0].value == "pygrafito.cli.app:App.main"

    def test_console_script_matches_the_module(self) -> None:
        script = Path(sys.executable).with_name("pygrafito")
        assert script.exists()
        completed = subprocess.run(
            [str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0
        assert completed.stdout == Runner.run("--help").stdout
