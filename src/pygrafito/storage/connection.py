# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""SQLite connection management for the graph store."""

import sqlite3
from pathlib import Path
from sqlite3 import Connection

from pygrafito.model import (
    GraphClosedError,
    NotFoundError,
    ReadOnlyError,
    UnsupportedSqliteError,
    ValidationError,
)
from pygrafito.storage.schema import Schema


class Database:
    """Own one configured SQLite connection and the graph schema.

    Parameters
    ----------
    path : str | Path
        Filesystem path of the database, or ``":memory:"``.
    create : bool, optional
        Whether a missing database file may be created, by default ``True``.
    readonly : bool, optional
        Whether to open an existing file without write access, by default
        ``False``.

    Raises
    ------
    NotFoundError
        If ``create`` is false and the database file does not exist, or if a
        read-only file does not exist.
    ValidationError
        If a read-only in-memory database is requested.
    UnsupportedSqliteError
        If the SQLite runtime lacks the features the graph requires, or if a
        read-only open needs a schema write.
    """

    BUSY_TIMEOUT_MS: int = 5000
    MEMORY_PATH: str = ":memory:"

    def __init__(
        self,
        path: str | Path,
        *,
        create: bool = True,
        readonly: bool = False,
    ) -> None:
        location = str(path)
        if readonly and location == self.MEMORY_PATH:
            message = "a read-only graph must be backed by a file"
            raise ValidationError(message)
        exists = location == self.MEMORY_PATH or Path(location).exists()
        if readonly and not exists:
            message = f"database file does not exist: {location}"
            raise NotFoundError(message)
        if not create and not exists:
            message = f"database file does not exist: {location}"
            raise NotFoundError(message)
        self._location = location
        self._readonly = readonly
        self._closed = False
        self._connection = self._connect()
        self._configure()
        Schema.verify_json_support(self._connection)
        self._bootstrap()
        if self._readonly:
            self._connection.execute("PRAGMA query_only = ON")

    @property
    def location(self) -> str:
        """Return the database location used to open the connection.

        Returns
        -------
        str
            Filesystem path or ``":memory:"``.
        """
        return self._location

    @property
    def connection(self) -> Connection:
        """Return the underlying SQLite connection.

        Returns
        -------
        Connection
            The configured connection.
        """
        return self._connection

    @property
    def readonly(self) -> bool:
        """Report whether the connection was opened without write access.

        Returns
        -------
        bool
            ``True`` for a read-only handle.
        """
        return self._readonly

    def ensure_writable(self) -> None:
        """Reject a write on a read-only handle.

        Raises
        ------
        GraphClosedError
            If the database has already been closed.
        ReadOnlyError
            If the database was opened read-only.
        """
        self.ensure_open()
        if self._readonly:
            message = "graph handle is read-only"
            raise ReadOnlyError(message)

    def close(self) -> None:
        """Close the underlying connection.

        Closing an already closed database is a no-op.
        """
        if self._closed:
            return
        if self._connection.in_transaction:
            self._connection.rollback()
        self._optimize()
        self._connection.close()
        self._closed = True

    def _optimize(self) -> None:
        """Refresh planner statistics before closing a file database.

        Statistics affect plan choice only, so a failure is ignored.
        """
        if self._location == self.MEMORY_PATH:
            return
        try:
            self._connection.execute("PRAGMA optimize")
        except sqlite3.OperationalError:
            return

    def ensure_open(self) -> None:
        """Reject use of a closed database.

        Raises
        ------
        GraphClosedError
            If the database has already been closed.
        """
        if self._closed:
            message = "graph handle is closed"
            raise GraphClosedError(message)

    def _configure(self) -> None:
        """Apply the pragmas required by the storage layer."""
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(f"PRAGMA busy_timeout = {self.BUSY_TIMEOUT_MS}")
        if self._location != self.MEMORY_PATH and not self._readonly:
            self._connection.execute("PRAGMA journal_mode = WAL")

    def _connect(self) -> Connection:
        """Open the SQLite connection for the configured access mode.

        Returns
        -------
        Connection
            Read-write connection, or a read-only connection for a file.
        """
        if not self._readonly:
            return sqlite3.connect(
                self._location,
                timeout=self.BUSY_TIMEOUT_MS / 1000,
                isolation_level=None,
                check_same_thread=True,
            )
        location = Path(self._location).absolute()
        return sqlite3.connect(
            f"{location.as_uri()}?mode=ro",
            uri=True,
            timeout=self.BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
            check_same_thread=True,
        )

    def _bootstrap(self) -> None:
        """Create or verify the schema, mapping read-only schema writes.

        Raises
        ------
        UnsupportedSqliteError
            If a read-only open needs to write the schema.
        """
        try:
            Schema(self._connection).bootstrap()
        except sqlite3.OperationalError as error:
            if not self._readonly:
                raise
            message = "a read-only graph requires an existing graph database with a current schema"
            raise UnsupportedSqliteError(message) from error
