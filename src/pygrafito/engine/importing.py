# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Row-oriented import from CSV, JSONL, and in-memory mappings."""

import collections.abc
import csv
import dataclasses
import json
import typing
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

from pygrafito.engine.query.prepared import PreparedQuery
from pygrafito.engine.query.results import ImportSummary, MutationSummary
from pygrafito.engine.query.values import QueryValue
from pygrafito.engine.transaction import Transaction
from pygrafito.model import PygrafitoError, ValidationError


class _ProbeStopError(Exception):
    """Internal marker that rolls back a failure probe."""


class GraphHandle(typing.Protocol):
    """Minimal graph surface used by the import runner."""

    def prepare(self, text: str) -> PreparedQuery:
        """Parse, analyse, and plan one statement.

        Parameters
        ----------
        text : str
            Statement source text.

        Returns
        -------
        PreparedQuery
            Reusable prepared statement.
        """
        ...

    def transaction(self) -> Transaction:
        """Start an explicit transaction.

        Returns
        -------
        Transaction
            Transaction handle.
        """
        ...


class CsvReader:
    """Read a CSV file as row mappings.

    Parameters
    ----------
    path : Path
        File to read.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def rows(self) -> Iterator[tuple[int, Mapping[str, object]]]:
        """Yield one mapping per non-blank CSV record.

        Yields
        ------
        tuple[int, Mapping[str, object]]
            One-based record number and its header-keyed values.

        Raises
        ------
        ValidationError
            If the header is missing or duplicated, or a record width differs.
        """
        with self._path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None or not header:
                message = f"{self._path}: CSV input requires a header row"
                raise ValidationError(message)
            if any(not name for name in header):
                message = f"{self._path}: CSV header names must not be empty"
                raise ValidationError(message)
            if len(set(header)) != len(header):
                message = f"{self._path}: CSV header names must be unique"
                raise ValidationError(message)
            for number, record in enumerate(reader, start=1):
                if not record:
                    continue
                if len(record) != len(header):
                    message = (
                        f"{self._path}: CSV row {number} has {len(record)} fields; "
                        f"expected {len(header)}"
                    )
                    raise ValidationError(message)
                yield number, dict(zip(header, record, strict=True))


class JsonLinesReader:
    """Read a JSONL file as row mappings.

    Parameters
    ----------
    path : Path
        File to read.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def rows(self) -> Iterator[tuple[int, Mapping[str, object]]]:
        """Yield one mapping per non-blank JSON object line.

        Yields
        ------
        tuple[int, Mapping[str, object]]
            One-based line number and its decoded object.

        Raises
        ------
        ValidationError
            If a line is invalid JSON, not an object, or contains a non-finite
            number.
        """
        with self._path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line, parse_constant=self._reject_constant)
                except (json.JSONDecodeError, ValueError) as error:
                    message = f"{self._path}: JSONL line {number}: {error}"
                    raise ValidationError(message) from error
                if not isinstance(value, dict):
                    message = f"{self._path}: JSONL line {number} must be a JSON object"
                    raise ValidationError(message)
                yield number, typing.cast(Mapping[str, object], value)

    @staticmethod
    def _reject_constant(value: str) -> typing.Never:
        """Reject a non-finite JSON constant.

        Parameters
        ----------
        value : str
            Constant spelling.

        Raises
        ------
        ValueError
            Always, for ``NaN`` and infinity spellings.
        """
        message = f"{value} is not a finite JSON number"
        raise ValueError(message)


class ImportRunner:
    """Validate, batch, and execute one statement-driven import.

    Parameters
    ----------
    graph : GraphHandle
        Graph used to prepare and run the import statement.
    """

    DEFAULT_BATCH_SIZE: int = 1000

    def __init__(self, graph: GraphHandle) -> None:
        self._graph = graph

    def import_rows(
        self,
        statement: str,
        rows: Iterable[Mapping[str, object]],
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        atomic: bool = False,
    ) -> ImportSummary:
        """Import in-memory row mappings.

        Parameters
        ----------
        statement : str
            Write statement that references ``$rows``.
        rows : Iterable[Mapping[str, object]]
            Row mappings to import.
        batch_size : int, optional
            Rows per statement execution, by default 1000.
        atomic : bool, optional
            Whether the whole import commits in one transaction, by default
            ``False``.

        Returns
        -------
        ImportSummary
            Rows, batches, and aggregate mutation counts.
        """
        numbered = (
            (number, typing.cast(Mapping[str, object], row))
            for number, row in enumerate(rows, start=1)
        )
        return self._run(statement, numbered, "<rows>", batch_size=batch_size, atomic=atomic)

    def import_file(
        self,
        path: Path,
        statement: str,
        *,
        format: str | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        atomic: bool = False,
    ) -> ImportSummary:
        """Import a CSV or JSONL file.

        Parameters
        ----------
        path : Path
            File to import.
        statement : str
            Write statement that references ``$rows``.
        format : str | None, optional
            Explicit ``csv`` or ``jsonl`` format, by default inferred from the
            file suffix.
        batch_size : int, optional
            Rows per statement execution, by default 1000.
        atomic : bool, optional
            Whether the whole import commits in one transaction, by default
            ``False``.

        Returns
        -------
        ImportSummary
            Rows, batches, and aggregate mutation counts.
        """
        selected = self.select_format(path, format)
        reader: CsvReader | JsonLinesReader = (
            CsvReader(path) if selected == "csv" else JsonLinesReader(path)
        )
        return self._run(
            statement,
            reader.rows(),
            str(path),
            batch_size=batch_size,
            atomic=atomic,
        )

    @classmethod
    def select_format(cls, path: Path, format: str | None) -> str:
        """Return the format selected by the argument or the file suffix.

        Parameters
        ----------
        path : Path
            File to import.
        format : str | None
            Explicit format, or ``None`` to infer it.

        Returns
        -------
        str
            ``csv`` or ``jsonl``.

        Raises
        ------
        ValidationError
            If the explicit format or the suffix is not supported.
        """
        if format is not None:
            selected = format.lower()
            if selected not in {"csv", "jsonl"}:
                message = f"unsupported import format {format!r}; use 'csv' or 'jsonl'"
                raise ValidationError(message)
            return selected
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return "csv"
        if suffix in {".jsonl", ".ndjson"}:
            return "jsonl"
        message = (
            f"cannot determine the import format of {path.name!r}; "
            "use format='csv' or format='jsonl'"
        )
        raise ValidationError(message)

    def _run(
        self,
        statement: str,
        rows: Iterable[tuple[int, Mapping[str, object]]],
        source: str,
        *,
        batch_size: int,
        atomic: bool,
    ) -> ImportSummary:
        """Validate, batch, and execute an import.

        Parameters
        ----------
        statement : str
            Write statement that references ``$rows``.
        rows : Iterable[tuple[int, Mapping[str, object]]]
            Numbered row mappings.
        source : str
            Source label used in failure notes.
        batch_size : int
            Rows per statement execution.
        atomic : bool
            Whether the whole import commits in one transaction.

        Returns
        -------
        ImportSummary
            Rows, batches, and aggregate mutation counts.
        """
        prepared = self._prepare(statement)
        batch_size = self._batch_size(batch_size)
        if atomic:
            return self._run_atomic(statement, rows, source, batch_size)
        return self._run_batches(prepared, statement, rows, source, batch_size)

    def _prepare(self, statement: str) -> PreparedQuery:
        """Prepare and validate the import statement.

        Parameters
        ----------
        statement : str
            Write statement that references ``$rows``.

        Returns
        -------
        PreparedQuery
            Validated prepared statement.

        Raises
        ------
        ValidationError
            If the statement does not write or does not reference ``$rows``.
        """
        prepared = self._graph.prepare(statement)
        if not prepared.is_write:
            message = "the import statement must contain a write clause"
            raise ValidationError(message)
        if "rows" not in prepared.parameters:
            message = "the import statement must reference $rows"
            raise ValidationError(message)
        return prepared

    @classmethod
    def _batch_size(cls, batch_size: int) -> int:
        """Validate a batch size.

        Parameters
        ----------
        batch_size : int
            Requested rows per batch.

        Returns
        -------
        int
            The validated batch size.

        Raises
        ------
        ValidationError
            If the size is not a positive integer.
        """
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            message = "batch_size must be a positive integer"
            raise ValidationError(message)
        return batch_size

    def _run_batches(
        self,
        prepared: PreparedQuery,
        statement: str,
        rows: Iterable[tuple[int, Mapping[str, object]]],
        source: str,
        batch_size: int,
    ) -> ImportSummary:
        """Execute each batch in its own transaction.

        Parameters
        ----------
        prepared : PreparedQuery
            Prepared import statement.
        statement : str
            Statement source used by failure probes.
        rows : Iterable[tuple[int, Mapping[str, object]]]
            Numbered row mappings.
        source : str
            Source label used in failure notes.
        batch_size : int
            Rows per batch.

        Returns
        -------
        ImportSummary
            Rows, batches, and aggregate mutation counts.
        """
        summary = ImportSummary()
        total = 0
        for batches, (start, batch) in enumerate(
            self._batches(rows, source, batch_size),
            start=1,
        ):
            try:
                result = prepared.execute({"rows": typing.cast(list[QueryValue], batch)})
            except PygrafitoError as error:
                self._annotate(error, statement, source, start, batches, batch)
                raise
            total += len(batch)
            summary = self._accumulate(summary, result.summary, total, batches)
        return summary

    def _run_atomic(
        self,
        statement: str,
        rows: Iterable[tuple[int, Mapping[str, object]]],
        source: str,
        batch_size: int,
    ) -> ImportSummary:
        """Execute every batch in one transaction.

        Parameters
        ----------
        statement : str
            Statement source executed inside the transaction.
        rows : Iterable[tuple[int, Mapping[str, object]]]
            Numbered row mappings.
        source : str
            Source label used in failure notes.
        batch_size : int
            Rows per batch.

        Returns
        -------
        ImportSummary
            Rows, batches, and aggregate mutation counts.
        """
        summary = ImportSummary()
        total = 0
        batches = 0
        start = 1
        batch: list[Mapping[str, object]] = []
        transaction = self._graph.transaction().begin()
        try:
            for batch_start, batch in self._batches(rows, source, batch_size):
                start = batch_start
                result = transaction.query(
                    statement,
                    {"rows": typing.cast(list[QueryValue], batch)},
                )
                total += len(batch)
                batches += 1
                summary = self._accumulate(summary, result.summary, total, batches)
            transaction.commit()
        except PygrafitoError as error:
            transaction.rollback()
            if not isinstance(error, ValidationError):
                self._annotate(error, statement, source, start, batches + 1, batch)
            raise
        return summary

    def _batches(
        self,
        rows: Iterable[tuple[int, Mapping[str, object]]],
        source: str,
        batch_size: int,
    ) -> Iterator[tuple[int, list[Mapping[str, object]]]]:
        """Group numbered rows into validated batches.

        Parameters
        ----------
        rows : Iterable[tuple[int, Mapping[str, object]]]
            Numbered row mappings.
        source : str
            Source label used in validation messages.
        batch_size : int
            Rows per batch.

        Yields
        ------
        tuple[int, list[Mapping[str, object]]]
            First row number and the batch rows.
        """
        batch: list[Mapping[str, object]] = []
        start = 1
        for number, row in rows:
            self._validate_row(row, source, number)
            if not batch:
                start = number
            batch.append(row)
            if len(batch) == batch_size:
                yield start, batch
                batch = []
        if batch:
            yield start, batch

    @classmethod
    def _validate_row(
        cls,
        row: Mapping[str, object],
        source: str,
        number: int,
    ) -> None:
        """Require one row to be a string-keyed mapping.

        Parameters
        ----------
        row : Mapping[str, object]
            Candidate row.
        source : str
            Source label used in the message.
        number : int
            One-based row number.

        Raises
        ------
        ValidationError
            If the row is not a mapping or a key is not a string.
        """
        if not isinstance(row, collections.abc.Mapping):
            message = f"{source} row {number} must be a mapping"
            raise ValidationError(message)
        if any(not isinstance(key, str) for key in row):
            message = f"{source} row {number} keys must be strings"
            raise ValidationError(message)

    def _annotate(
        self,
        error: PygrafitoError,
        statement: str,
        source: str,
        start: int,
        batch_number: int,
        batch: list[Mapping[str, object]],
    ) -> None:
        """Attach import context to a query failure.

        Parameters
        ----------
        error : PygrafitoError
            Failure raised by the import statement.
        statement : str
            Statement executed for the batch.
        source : str
            Source label.
        start : int
            First row number of the failing batch.
        batch_number : int
            One-based batch number.
        batch : list[Mapping[str, object]]
            Rows of the failing batch.
        """
        row = self._locate_row(statement, start, batch)
        error.add_note(f"while importing {source} row {row} (batch {batch_number})")

    def _locate_row(
        self,
        statement: str,
        start: int,
        batch: list[Mapping[str, object]],
    ) -> int:
        """Find the row that fails when the batch is replayed.

        Parameters
        ----------
        statement : str
            Statement executed for the batch.
        start : int
            First row number of the batch.
        batch : list[Mapping[str, object]]
            Rows of the failing batch.

        Returns
        -------
        int
            One-based row number of the first failing row, or the batch start
            when no single row reproduces the failure.
        """
        found = start
        try:
            with self._graph.transaction() as transaction:
                for offset, row in enumerate(batch):
                    try:
                        transaction.query(
                            statement,
                            {"rows": typing.cast(list[QueryValue], [row])},
                        )
                    except PygrafitoError:
                        found = start + offset
                        raise _ProbeStopError from None
                raise _ProbeStopError
        except _ProbeStopError:
            return found

    @staticmethod
    def _accumulate(
        summary: ImportSummary,
        mutations: MutationSummary,
        rows: int,
        batches: int,
    ) -> ImportSummary:
        """Add one batch's counts to an import summary.

        Parameters
        ----------
        summary : ImportSummary
            Summary so far.
        mutations : MutationSummary
            Counts of the latest batch.
        rows : int
            Rows read so far.
        batches : int
            Batches executed so far.

        Returns
        -------
        ImportSummary
            Updated summary.
        """
        previous = summary.mutations
        combined = MutationSummary(
            created_nodes=previous.created_nodes + mutations.created_nodes,
            created_relationships=previous.created_relationships + mutations.created_relationships,
            deleted_nodes=previous.deleted_nodes + mutations.deleted_nodes,
            deleted_relationships=previous.deleted_relationships + mutations.deleted_relationships,
            properties_set=previous.properties_set + mutations.properties_set,
            properties_removed=previous.properties_removed + mutations.properties_removed,
            labels_added=previous.labels_added + mutations.labels_added,
            labels_removed=previous.labels_removed + mutations.labels_removed,
        )
        return dataclasses.replace(summary, rows=rows, batches=batches, mutations=combined)


__all__ = [
    "CsvReader",
    "GraphHandle",
    "ImportRunner",
    "JsonLinesReader",
]
