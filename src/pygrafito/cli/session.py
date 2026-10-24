# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Mutable shell state and execution routing."""

import collections.abc
import json
import string
import typing
from pathlib import Path

import pygrafito
import pygrafito.__about__
from pygrafito import Graph, QueryResult, Transaction, TransactionError, ValidationError
from pygrafito.cli.formatting import OutputMode, ResultWriter


class ParameterDecoder:
    """Decode ``NAME=JSON`` parameter assignments."""

    START: typing.ClassVar[frozenset[str]] = frozenset(string.ascii_letters + "_")
    BODY: typing.ClassVar[frozenset[str]] = frozenset(string.ascii_letters + string.digits + "_")

    @classmethod
    def decode(cls, text: str) -> tuple[str, object]:
        """Decode one parameter assignment.

        Parameters
        ----------
        text : str
            Assignment of the form ``NAME=JSON``.

        Returns
        -------
        tuple[str, object]
            Parameter name and decoded value.

        Raises
        ------
        ValidationError
            If the name is malformed, the value is not JSON, or the value uses
            a non-standard constant.
        """
        name, separator, raw = text.partition("=")
        if not separator:
            message = f"expected NAME=JSON, got {text!r}"
            raise ValidationError(message)
        cls._validate_name(name)
        try:
            value = json.loads(raw, parse_constant=cls._reject_constant)
        except ValueError as error:
            message = f"invalid JSON for parameter {name!r}: {error}"
            raise ValidationError(message) from error
        return (name, value)

    @classmethod
    def _validate_name(cls, name: str) -> None:
        """Reject a parameter name the dialect cannot reference.

        Parameters
        ----------
        name : str
            Candidate parameter name.

        Raises
        ------
        ValidationError
            If the name is empty or not an identifier.
        """
        valid = (
            bool(name)
            and name[0] in cls.START
            and all(character in cls.BODY for character in name[1:])
        )
        if not valid:
            message = f"invalid parameter name {name!r}"
            raise ValidationError(message)

    @classmethod
    def _reject_constant(cls, value: str) -> typing.Never:
        """Reject JSON constants that the value model does not accept.

        Parameters
        ----------
        value : str
            Constant spelling.

        Raises
        ------
        ValueError
            Always, for ``NaN`` and infinity spellings.
        """
        message = f"{value} is not a finite number"
        raise ValueError(message)


class Session:
    """Own the open database, transaction, parameters, and output state.

    Parameters
    ----------
    mode : OutputMode
        Result rendering mode.
    headers : bool
        Whether table and CSV output includes a header row.
    timer : bool
        Whether statement timing is reported.
    quiet : bool
        Whether interactive footers are suppressed.
    interactive : bool
        Whether the session reads from a terminal.
    readonly : bool
        Whether databases are opened read-only.
    output : typing.TextIO
        Standard output stream.
    error : typing.TextIO
        Standard error stream.
    """

    def __init__(
        self,
        *,
        mode: OutputMode,
        headers: bool,
        timer: bool,
        quiet: bool,
        interactive: bool,
        readonly: bool,
        output: typing.TextIO,
        error: typing.TextIO,
    ) -> None:
        self._mode = mode
        self._headers = headers
        self._timer = timer
        self._quiet = quiet
        self._interactive = interactive
        self._readonly = readonly
        self._output = output
        self._error = error
        self._graph: Graph | None = None
        self._transaction: Transaction | None = None
        self._location = ":memory:"
        self._file: typing.TextIO | None = None
        self._output_path: str | None = None
        self._once: typing.TextIO | None = None
        self._parameters: dict[str, object] = {}

    @property
    def mode(self) -> OutputMode:
        """Return the result rendering mode.

        Returns
        -------
        OutputMode
            Active mode.
        """
        return self._mode

    @property
    def headers(self) -> bool:
        """Return whether headers are enabled.

        Returns
        -------
        bool
            Header setting.
        """
        return self._headers

    @property
    def timer(self) -> bool:
        """Return whether timing is enabled.

        Returns
        -------
        bool
            Timing setting.
        """
        return self._timer

    @property
    def quiet(self) -> bool:
        """Return whether interactive footers are suppressed.

        Returns
        -------
        bool
            Quiet setting.
        """
        return self._quiet

    @property
    def interactive(self) -> bool:
        """Return whether the session runs interactively.

        Returns
        -------
        bool
            Interactive setting.
        """
        return self._interactive

    @property
    def readonly(self) -> bool:
        """Return whether databases are opened read-only.

        Returns
        -------
        bool
            Read-only setting.
        """
        return self._readonly

    @property
    def location(self) -> str:
        """Return the current database location.

        Returns
        -------
        str
            Filesystem path or ``":memory:"``.
        """
        return self._location

    @property
    def in_transaction(self) -> bool:
        """Return whether a transaction is active.

        Returns
        -------
        bool
            ``True`` while a transaction is open.
        """
        return self._transaction is not None

    @property
    def graph(self) -> Graph:
        """Return the open graph handle.

        Returns
        -------
        Graph
            Open graph.

        Raises
        ------
        ValidationError
            If no database is open.
        """
        if self._graph is None:
            message = "no database is open; use .open PATH"
            raise ValidationError(message)
        return self._graph

    @property
    def target(self) -> Graph | Transaction:
        """Return the object that executes statements.

        Returns
        -------
        Graph | Transaction
            Active transaction, or the graph when none is open.
        """
        if self._transaction is not None:
            return self._transaction
        return self.graph

    def set_mode(self, mode: OutputMode) -> None:
        """Change the result rendering mode.

        Parameters
        ----------
        mode : OutputMode
            New mode.
        """
        self._mode = mode

    def set_headers(self, headers: bool) -> None:
        """Change whether headers are rendered.

        Parameters
        ----------
        headers : bool
            New header setting.
        """
        self._headers = headers

    def set_timer(self, timer: bool) -> None:
        """Change whether statement timing is reported.

        Parameters
        ----------
        timer : bool
            New timing setting.
        """
        self._timer = timer

    def set_parameter(self, name: str, value: object) -> None:
        """Bind one query parameter.

        Parameters
        ----------
        name : str
            Parameter name without the leading dollar sign.
        value : object
            Parameter value.
        """
        self._parameters[name] = value

    def parameters(self) -> dict[str, object]:
        """Return a copy of the bound parameters.

        Returns
        -------
        dict[str, object]
            Parameter names and values.
        """
        return dict(self._parameters)

    def open_database(self, path: str | None) -> None:
        """Open a database, replacing any currently open one.

        The new database is opened before the old one is closed, so a failed
        open leaves the previous session state intact.

        Parameters
        ----------
        path : str | None
            Filesystem path, or ``None`` for a transient in-memory graph.
        """
        location = path if path is not None else ":memory:"
        graph = Graph.open(location, readonly=self._readonly)
        if self._graph is not None:
            self._graph.close()
        self._graph = graph
        self._location = location

    def close_database(self) -> None:
        """Close the open database, if any."""
        if self._graph is not None:
            self._graph.close()
            self._graph = None
        self._transaction = None

    def begin(self) -> None:
        """Start an explicit transaction."""
        transaction = self.graph.transaction()
        transaction.begin()
        self._transaction = transaction

    def commit(self) -> None:
        """Commit the active transaction.

        Raises
        ------
        TransactionError
            If no transaction is active.
        """
        transaction = self._require_transaction()
        transaction.commit()
        self._transaction = None

    def rollback(self) -> None:
        """Roll back the active transaction.

        Raises
        ------
        TransactionError
            If no transaction is active.
        """
        transaction = self._require_transaction()
        transaction.rollback()
        self._transaction = None

    def execute(self, text: str) -> QueryResult:
        """Execute one statement through the graph or the active transaction.

        Parameters
        ----------
        text : str
            Statement source text.

        Returns
        -------
        QueryResult
            Materialized result.
        """
        values = typing.cast(collections.abc.Mapping[str, typing.Any], self._parameters)
        return self.target.query(text, values)

    def explain(self, text: str) -> tuple[str, ...]:
        """Plan one statement without executing it.

        Parameters
        ----------
        text : str
            Statement source text.

        Returns
        -------
        tuple[str, ...]
            Plan detail lines.
        """
        values = typing.cast(collections.abc.Mapping[str, typing.Any], self._parameters)
        return self.graph.explain(text, values)

    def write_result(self, result: QueryResult) -> int:
        """Render one result to the current output target.

        Parameters
        ----------
        result : QueryResult
            Materialized result.

        Returns
        -------
        int
            Number of rows rendered.
        """
        if not result.columns:
            return 0
        stream, once = self._target_stream()
        count = ResultWriter(self._mode, headers=self._headers).write(result, stream)
        stream.flush()
        if once:
            self._release_once()
        return count

    def emit(self, text: str) -> None:
        """Write command output to the current target.

        Parameters
        ----------
        text : str
            Text to write. A trailing newline is added when missing.
        """
        stream, once = self._target_stream()
        stream.write(text if text.endswith("\n") else f"{text}\n")
        stream.flush()
        if once:
            self._release_once()

    def emit_lines(self, lines: typing.Iterable[str]) -> None:
        """Write command output lines to the current target.

        Parameters
        ----------
        lines : typing.Iterable[str]
            Lines to write.
        """
        self.emit("\n".join(lines))

    def warn(self, text: str) -> None:
        """Write a diagnostic to standard error.

        Parameters
        ----------
        text : str
            Diagnostic text.
        """
        self._error.write(text if text.endswith("\n") else f"{text}\n")
        self._error.flush()

    def report_error(self, error: BaseException) -> None:
        """Report one failure on standard error.

        Parameters
        ----------
        error : BaseException
            Failure to report.
        """
        lines = [f"error: {error}"]
        lines.extend(f"  {note}" for note in getattr(error, "__notes__", ()))
        self.warn("\n".join(lines))

    def report_footer(
        self,
        row_count: int,
        result: QueryResult,
        elapsed: float,
    ) -> None:
        """Report the interactive row count, mutation summary, and timing.

        Parameters
        ----------
        row_count : int
            Number of rows rendered.
        result : QueryResult
            Result that was rendered.
        elapsed : float
            Elapsed seconds.
        """
        if not self._interactive or self._quiet:
            return
        parts: list[str] = []
        if result.columns:
            parts.append(self._count(row_count, "row"))
        else:
            parts.extend(self._summary_parts(result))
        if self._timer:
            parts.append(f"{elapsed * 1000:.1f} ms")
        if parts:
            self.warn(", ".join(parts))

    def set_output(self, path: str | None) -> None:
        """Redirect output to a file, or back to standard output.

        Parameters
        ----------
        path : str | None
            Destination path, or ``None`` to restore standard output.
        """
        if path is None:
            self._close_file()
            self._output_path = None
            return
        stream = Path(path).open("w", encoding="utf-8", newline="")  # noqa: SIM115
        self._close_file()
        self._file = stream
        self._output_path = path

    def set_once(self, path: str) -> None:
        """Redirect the next output to a file.

        Parameters
        ----------
        path : str
            Destination path.
        """
        stream = Path(path).open("w", encoding="utf-8", newline="")  # noqa: SIM115
        self._release_once()
        self._once = stream

    def output_description(self) -> str:
        """Describe the current output target.

        Returns
        -------
        str
            ``stdout`` or the redirected path.
        """
        return "stdout" if self._output_path is None else self._output_path

    def prompt(self) -> str:
        """Return the interactive prompt for the current state.

        Returns
        -------
        str
            Prompt text.
        """
        name = ":memory:" if self._location == ":memory:" else Path(self._location).name
        marker = "*" if self.in_transaction else ""
        return f"{name}{marker}> "

    def banner(self) -> str:
        """Return the startup banner.

        Returns
        -------
        str
            One-line banner.
        """
        access = " (read-only)" if self._readonly else ""
        version = pygrafito.__about__.__version__
        return f'pygrafito {version} | {self._location}{access} | type ".help" for commands'

    def finish(self) -> None:
        """Finish the session, rolling back and closing everything open."""
        if self._transaction is not None:
            self.rollback()
            self.warn("rolled back an open transaction")
        self._release_once()
        self._close_file()
        if self._graph is not None:
            self._graph.close()
            self._graph = None

    def _require_transaction(self) -> Transaction:
        """Return the active transaction.

        Returns
        -------
        Transaction
            Active transaction.

        Raises
        ------
        TransactionError
            If no transaction is active.
        """
        if self._transaction is None:
            message = "no transaction is active"
            raise TransactionError(message)
        return self._transaction

    def _target_stream(self) -> tuple[typing.TextIO, bool]:
        """Return the stream that receives output and whether it is one-shot.

        Returns
        -------
        tuple[typing.TextIO, bool]
            Destination stream and whether it must be released after writing.
        """
        if self._once is not None:
            return (self._once, True)
        if self._file is not None:
            return (self._file, False)
        return (self._output, False)

    def _release_once(self) -> None:
        """Close and clear the one-shot output target."""
        if self._once is not None:
            self._once.close()
            self._once = None

    def _close_file(self) -> None:
        """Close and clear the redirected output file."""
        if self._file is not None:
            self._file.close()
            self._file = None

    @staticmethod
    def _count(count: int, noun: str) -> str:
        """Format a count with a singular or plural noun.

        Parameters
        ----------
        count : int
            Number of items.
        noun : str
            Singular noun.

        Returns
        -------
        str
            Formatted count.
        """
        suffix = "" if count == 1 else "s"
        return f"{count} {noun}{suffix}"

    @classmethod
    def _summary_parts(cls, result: QueryResult) -> list[str]:
        """Describe the mutations reported by a result.

        Parameters
        ----------
        result : QueryResult
            Result carrying the mutation summary.

        Returns
        -------
        list[str]
            Human-readable change counts.
        """
        summary = result.summary
        entries = (
            (summary.created_nodes, "node created"),
            (summary.created_relationships, "relationship created"),
            (summary.deleted_nodes, "node deleted"),
            (summary.deleted_relationships, "relationship deleted"),
            (summary.properties_set, "property set"),
            (summary.properties_removed, "property removed"),
            (summary.labels_added, "label added"),
            (summary.labels_removed, "label removed"),
        )
        return [cls._count(count, noun) for count, noun in entries if count]
