# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Interactive loop and script execution for the graph shell."""

import time
import typing

from pygrafito import PygrafitoError
from pygrafito.cli.commands import Commands
from pygrafito.cli.reader import StatementReader
from pygrafito.cli.session import Session


class Shell:
    """Read input, run statements and commands, and report results.

    Parameters
    ----------
    session : Session
        Session that holds the database, transaction, and output state.
    input : typing.TextIO
        Stream that supplies input lines.
    error : typing.TextIO
        Stream that receives prompts and diagnostics.
    """

    CONTINUATION: str = "...> "

    def __init__(
        self,
        session: Session,
        *,
        input: typing.TextIO,
        error: typing.TextIO,
    ) -> None:
        self._session = session
        self._input = input
        self._error = error
        self._commands = Commands(session, self)

    def run(self) -> int:
        """Run the interactive loop until the user quits or input ends.

        Returns
        -------
        int
            Process exit code.
        """
        if not self._session.quiet:
            self._session.warn(self._session.banner())
        pending = ""
        while True:
            prompt = self._session.prompt() if not pending else self.CONTINUATION
            try:
                line = self._read_line(prompt)
            except KeyboardInterrupt:
                self._error.write("\n")
                self._error.flush()
                pending = ""
                continue
            if line is None:
                if pending.strip():
                    self._execute(pending)
                return 0
            if not pending:
                command = StatementReader.parse_command(line)
                if command is not None:
                    try:
                        keep_going = self._dispatch(*command)
                    except (PygrafitoError, OSError) as error:
                        self._session.report_error(error)
                        continue
                    except KeyboardInterrupt:
                        self._report_interruption()
                        continue
                    if not keep_going:
                        return 0
                    continue
            pending = f"{pending}{line}\n"
            split = StatementReader.split(pending)
            pending = split.pending
            for statement in split.statements:
                if not self._execute(statement):
                    pending = ""
                    break

    def run_script(self, text: str) -> int:
        """Execute every statement and command in a script.

        Statements and dot-commands run in order and the script stops at the
        first failure. A dot-command is recognized only at the start of a
        statement.

        Parameters
        ----------
        text : str
            Script source text.

        Returns
        -------
        int
            ``0`` when every statement succeeded, otherwise ``1``.
        """
        pending = ""
        number = 0
        for line in text.splitlines():
            if not pending:
                command = StatementReader.parse_command(line)
                if command is not None:
                    try:
                        keep_going = self._dispatch(*command)
                    except (PygrafitoError, OSError) as error:
                        self._session.report_error(error)
                        return 1
                    except KeyboardInterrupt:
                        self._report_interruption()
                        return 1
                    if not keep_going:
                        return 0
                    continue
            pending = f"{pending}{line}\n"
            split = StatementReader.split(pending)
            pending = split.pending
            for statement in split.statements:
                number += 1
                if not self._execute(statement, context=f"statement {number}"):
                    return 1
        if pending.strip():
            number += 1
            if not self._execute(pending, context=f"statement {number}"):
                return 1
        return 0

    def _read_line(self, prompt: str) -> str | None:
        """Write a prompt and read one input line.

        Parameters
        ----------
        prompt : str
            Prompt text.

        Returns
        -------
        str | None
            Line without its terminator, or ``None`` at end of input.
        """
        self._error.write(prompt)
        self._error.flush()
        line = self._input.readline()
        if line == "":
            return None
        return line.rstrip("\r\n")

    def _dispatch(self, name: str, argument: str) -> bool:
        """Run one dot-command.

        Parameters
        ----------
        name : str
            Command name without the leading dot.
        argument : str
            Command argument text.

        Returns
        -------
        bool
            ``False`` when the session should end.
        """
        return self._commands.execute(name, argument)

    def _execute(self, statement: str, *, context: str | None = None) -> bool:
        """Execute one statement and render its result.

        Parameters
        ----------
        statement : str
            Statement source text.
        context : str | None, optional
            Description of the statement's position, by default none.

        Returns
        -------
        bool
            ``True`` when the statement succeeded.
        """
        start = time.perf_counter()
        try:
            result = self._session.execute(statement)
        except (PygrafitoError, OSError) as error:
            self._report(error, context)
            return False
        except KeyboardInterrupt:
            self._report_interruption()
            return False
        elapsed = time.perf_counter() - start
        count = self._session.write_result(result)
        self._session.report_footer(count, result, elapsed)
        return True

    def _report(self, error: BaseException, context: str | None) -> None:
        """Report a statement failure.

        Parameters
        ----------
        error : BaseException
            Failure to report.
        context : str | None
            Statement position, or ``None`` in an interactive session.
        """
        if context is None:
            self._session.report_error(error)
        else:
            self._session.warn(f"error: {context}: {error}")

    def _report_interruption(self) -> None:
        """Report an interrupted statement without ending the session."""
        self._error.write("\ninterrupted\n")
        self._error.flush()
