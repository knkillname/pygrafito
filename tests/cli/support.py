# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Shared harness and fixtures for shell tests."""

import io
import typing
from pathlib import Path

from pygrafito import Graph
from pygrafito.cli.formatting import OutputMode
from pygrafito.cli.session import Session
from pygrafito.cli.shell import Shell


class Harness:
    """Drive a session and shell with in-memory streams.

    Parameters
    ----------
    path : Path | None, optional
        Database path, by default an in-memory graph.
    mode : OutputMode, optional
        Output mode, by default ``TABLE``.
    headers : bool, optional
        Whether headers are enabled, by default ``True``.
    interactive : bool, optional
        Whether the session is interactive, by default ``False``.
    readonly : bool, optional
        Whether the database is opened read-only, by default ``False``.
    quiet : bool, optional
        Whether footers are suppressed, by default ``False``.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        mode: OutputMode = OutputMode.TABLE,
        headers: bool = True,
        interactive: bool = False,
        readonly: bool = False,
        quiet: bool = False,
    ) -> None:
        self.output = io.StringIO()
        self.error = io.StringIO()
        self.session = Session(
            mode=mode,
            headers=headers,
            timer=False,
            quiet=quiet,
            interactive=interactive,
            readonly=readonly,
            output=self.output,
            error=self.error,
        )
        self.session.open_database(str(path) if path is not None else None)
        self.shell = Shell(self.session, input=io.StringIO(), error=self.error)

    def run(self, script: str) -> tuple[int, str, str]:
        """Run a script and return its code and captured streams.

        Parameters
        ----------
        script : str
            Script source.

        Returns
        -------
        tuple[int, str, str]
            Exit code, standard output, and standard error.
        """
        code = self.shell.run_script(script)
        return (code, self.output.getvalue(), self.error.getvalue())

    def run_interactive(self, text: str) -> tuple[int, str, str]:
        """Run the interactive loop over the given input.

        Parameters
        ----------
        text : str
            Input lines.

        Returns
        -------
        tuple[int, str, str]
            Exit code, standard output, and standard error.
        """
        self.shell = Shell(
            self.session,
            input=io.StringIO(text),
            error=self.error,
        )
        code = self.shell.run()
        return (code, self.output.getvalue(), self.error.getvalue())

    def reset(self) -> None:
        """Clear captured streams."""
        self.output.seek(0)
        self.output.truncate()
        self.error.seek(0)
        self.error.truncate()

    def close(self) -> None:
        """Finish the session and close the database."""
        self.session.finish()


class Fixtures:
    """Build the themed graph used by shell tests."""

    @staticmethod
    def seed(path: Path) -> None:
        """Create the standard test graph.

        Parameters
        ----------
        path : Path
            Database path.
        """
        with Graph.open(path) as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node("Program", "ISO", designation="Quorra", cycles=37)
            tron = graph.add_node("Program", designation="Tron", cycles=40)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
            graph.add_relationship(quorra, "ALLIES_WITH", tron, since_cycle=2021)
            graph.add_relationship(tron, "GUARDS", tron)

    @staticmethod
    def open(path: Path) -> typing.Iterator[Graph]:
        """Open a graph for assertions.

        Parameters
        ----------
        path : Path
            Database path.

        Yields
        ------
        Graph
            Open graph handle.
        """
        with Graph.open(path) as graph:
            yield graph
