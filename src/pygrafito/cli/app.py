# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Process entry point for the graph shell."""

import argparse
import sys
import typing
from pathlib import Path

from pygrafito import PygrafitoError, ValidationError
from pygrafito.cli.formatting import OutputMode
from pygrafito.cli.session import ParameterDecoder, Session
from pygrafito.cli.shell import Shell


class App:
    """Wire arguments, streams, and a session into one process run."""

    DESCRIPTION: typing.ClassVar[str] = (
        "Interactive and scripted shell for an embedded property graph."
    )

    @staticmethod
    def main(argv: typing.Sequence[str] | None = None) -> int:
        """Run the shell.

        Parameters
        ----------
        argv : typing.Sequence[str] | None, optional
            Argument list, by default the process arguments.

        Returns
        -------
        int
            Process exit code.
        """
        parser = App._parser()
        arguments = parser.parse_args(argv)
        if arguments.readonly and arguments.database is None:
            parser.error("--readonly requires a database path")
        parameters: dict[str, object] = {}
        for item in typing.cast(list[str], arguments.param):
            try:
                name, value = ParameterDecoder.decode(item)
            except ValidationError as error:
                parser.error(str(error))
            parameters[name] = value
        interactive = arguments.command is None and arguments.file is None and sys.stdin.isatty()
        session = Session(
            mode=OutputMode.from_name(arguments.format),
            headers=True,
            timer=False,
            quiet=arguments.quiet,
            interactive=interactive,
            readonly=arguments.readonly,
            output=sys.stdout,
            error=sys.stderr,
        )
        for name, value in parameters.items():
            session.set_parameter(name, value)
        try:
            session.open_database(arguments.database)
        except (PygrafitoError, OSError) as error:
            session.report_error(error)
            return 1
        shell = Shell(session, input=sys.stdin, error=sys.stderr)
        try:
            return App._run(shell, session, arguments)
        except KeyboardInterrupt:
            session.warn("interrupted")
            return 130
        finally:
            session.finish()

    @classmethod
    def _run(
        cls,
        shell: Shell,
        session: Session,
        arguments: argparse.Namespace,
    ) -> int:
        """Select the input mode and run it.

        Parameters
        ----------
        shell : Shell
            Shell bound to the session.
        session : Session
            Session under test.
        arguments : argparse.Namespace
            Parsed arguments.

        Returns
        -------
        int
            Process exit code.
        """
        if arguments.command is not None:
            return shell.run_script(arguments.command)
        if arguments.file is not None:
            return cls._run_file(shell, session, arguments.file)
        if not session.interactive:
            return shell.run_script(sys.stdin.read())
        return shell.run()

    @classmethod
    def _run_file(cls, shell: Shell, session: Session, path: str) -> int:
        """Run a script file.

        Parameters
        ----------
        shell : Shell
            Shell bound to the session.
        session : Session
            Session under test.
        path : str
            Script path.

        Returns
        -------
        int
            Process exit code.
        """
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as error:
            session.report_error(error)
            return 1
        return shell.run_script(text)

    @classmethod
    def _parser(cls) -> argparse.ArgumentParser:
        """Build the argument parser.

        Returns
        -------
        argparse.ArgumentParser
            Configured parser.
        """
        parser = argparse.ArgumentParser(prog="pygrafito", description=cls.DESCRIPTION)
        parser.add_argument(
            "database",
            nargs="?",
            help="database file; omit for a transient in-memory graph",
        )
        source = parser.add_mutually_exclusive_group()
        source.add_argument(
            "-c",
            "--command",
            metavar="TEXT",
            help="run statements and exit",
        )
        source.add_argument(
            "-f",
            "--file",
            metavar="PATH",
            help="run a script file and exit",
        )
        parser.add_argument(
            "--format",
            choices=[mode.value for mode in OutputMode],
            default=OutputMode.TABLE.value,
            help="result rendering mode (default: table)",
        )
        parser.add_argument(
            "--param",
            action="append",
            default=[],
            metavar="NAME=JSON",
            help="bind a query parameter; repeatable",
        )
        parser.add_argument(
            "--readonly",
            action="store_true",
            help="open the database without write access",
        )
        parser.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            help="suppress the banner and interactive footers",
        )
        return parser
