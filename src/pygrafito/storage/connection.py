# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""SQLite connection management for the graph store."""

import sqlite3
import threading
import time
from pathlib import Path
from sqlite3 import Connection

from pygrafito.model import (
    GraphClosedError,
    HandleAffinityError,
    LockTimeoutError,
    NotFoundError,
    ReadOnlyError,
    UnsupportedSqliteError,
    ValidationError,
)
from pygrafito.storage.schema import Schema
from pygrafito.storage.views import Views


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
    busy_timeout : int | None, optional
        Milliseconds a lock wait may take before it fails, by default
        :attr:`BUSY_TIMEOUT_MS`.

    Raises
    ------
    NotFoundError
        If ``create`` is false and the database file does not exist, or if a
        read-only file does not exist.
    ValidationError
        If a read-only in-memory database is requested or the busy timeout is
        invalid.
    UnsupportedSqliteError
        If the SQLite runtime lacks the features the graph requires, or if a
        read-only open needs a schema write.
    LockTimeoutError
        If opening the database exhausts the busy timeout while waiting for a
        lock.
    """

    BUSY_TIMEOUT_MS: int = 5000
    MEMORY_PATH: str = ":memory:"
    JOURNAL_MODE_BACKOFF_SECONDS: tuple[float, ...] = (0.01, 0.02, 0.04, 0.08)

    def __init__(
        self,
        path: str | Path,
        *,
        create: bool = True,
        readonly: bool = False,
        busy_timeout: int | None = None,
    ) -> None:
        self._busy_timeout = self._validated_timeout(busy_timeout)
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
        self._owner_thread = threading.get_ident()
        self._journal_mode = "unknown"
        self._connection = self._connect()
        try:
            Schema.verify_json_support(self._connection)
            self._configure()
            if not self._readonly:
                Views(self._connection).check_names()
            self._bootstrap()
            Views(self._connection).ensure(readonly=self._readonly)
            if self._readonly:
                self._connection.execute("PRAGMA query_only = ON")
        except BaseException:
            self._connection.close()
            raise

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

    @property
    def journal_mode(self) -> str:
        """Return the journal mode the database obtained.

        Returns
        -------
        str
            Lower-case journal mode such as ``wal`` or ``memory``.
        """
        return self._journal_mode

    @property
    def busy_timeout(self) -> int:
        """Return the configured lock wait in milliseconds.

        Returns
        -------
        int
            Busy timeout in milliseconds.
        """
        return self._busy_timeout

    def ensure_writable(self) -> None:
        """Reject a write on a read-only handle.

        Raises
        ------
        GraphClosedError
            If the database has already been closed.
        HandleAffinityError
            If the current thread does not own the database handle.
        ReadOnlyError
            If the database was opened read-only.
        """
        self.ensure_open()
        if self._readonly:
            message = "graph handle is read-only"
            raise ReadOnlyError(message)

    def ensure_open(self) -> None:
        """Reject use of a closed or foreign-thread database.

        Raises
        ------
        GraphClosedError
            If the database has already been closed.
        HandleAffinityError
            If the current thread does not own the database handle.
        """
        if self._closed:
            message = "graph handle is closed"
            raise GraphClosedError(message)
        self.ensure_affinity()

    def ensure_affinity(self) -> None:
        """Reject use of a handle from a thread that does not own it.

        Raises
        ------
        HandleAffinityError
            If the current thread does not own the database handle.
        """
        if threading.get_ident() != self._owner_thread:
            message = "graph handle belongs to the thread that opened it"
            raise HandleAffinityError(message)

    def close(self) -> None:
        """Close the underlying connection.

        Closing an already closed database is a no-op.

        Raises
        ------
        HandleAffinityError
            If the current thread does not own the database handle.
        """
        if self._closed:
            return
        self.ensure_affinity()
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

    def _configure(self) -> None:
        """Apply the pragmas required by the storage layer.

        The journal-mode switch is retried because the busy handler does not
        cover ``PRAGMA journal_mode``.
        """
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout}")
        schema = Schema(self._connection)
        schema.refuse_foreign_database()
        schema.ensure_supported(readonly=self._readonly)
        self._configure_journal_mode()

    def _configure_journal_mode(self) -> None:
        """Prefer write-ahead logging and record the mode in effect.

        Raises
        ------
        LockTimeoutError
            If the switch still reports a lock after every retry.
        """
        if self._location != self.MEMORY_PATH and not self._readonly:
            self._enable_write_ahead_logging()
            return
        self._journal_mode = self._read_journal_mode()

    def _enable_write_ahead_logging(self) -> None:
        """Switch a file database to write-ahead logging with a bounded retry.

        Raises
        ------
        LockTimeoutError
            If the switch still reports a lock after every retry.
        """
        attempts = len(self.JOURNAL_MODE_BACKOFF_SECONDS) + 1
        for attempt in range(attempts):
            try:
                self._connection.execute("PRAGMA journal_mode = WAL").fetchone()
            except sqlite3.OperationalError as error:
                if attempt + 1 >= attempts or not self._is_lock_error(error):
                    if self._is_lock_error(error):
                        message = "could not switch the database to write-ahead logging"
                        raise LockTimeoutError(message) from error
                    raise
                time.sleep(self.JOURNAL_MODE_BACKOFF_SECONDS[attempt])
                continue
            self._journal_mode = self._read_journal_mode()
            return

    def _read_journal_mode(self) -> str:
        """Read back the journal mode the connection obtained.

        Returns
        -------
        str
            Lower-case journal mode.
        """
        row = self._connection.execute("PRAGMA journal_mode").fetchone()
        if row is None:
            return "unknown"
        return str(row[0]).lower()

    def _connect(self) -> Connection:
        """Open the SQLite connection for the configured access mode.

        Returns
        -------
        Connection
            Read-write connection, or a read-only connection for a file.
        """
        timeout = self._busy_timeout / 1000
        if not self._readonly:
            return sqlite3.connect(
                self._location,
                timeout=timeout,
                isolation_level=None,
                check_same_thread=True,
            )
        location = Path(self._location).absolute()
        return sqlite3.connect(
            f"{location.as_uri()}?mode=ro",
            uri=True,
            timeout=timeout,
            isolation_level=None,
            check_same_thread=True,
        )

    def _bootstrap(self) -> None:
        """Create or verify the schema, mapping read-only schema writes.

        Raises
        ------
        UnsupportedSqliteError
            If a read-only open needs to write the schema.
        LockTimeoutError
            If the bootstrap write lock cannot be obtained.
        """
        try:
            Schema(self._connection).bootstrap(readonly=self._readonly)
        except sqlite3.OperationalError as error:
            if self._readonly:
                message = (
                    "a read-only graph requires an existing graph database with a current schema"
                )
                raise UnsupportedSqliteError(message) from error
            if self._is_lock_error(error):
                message = "could not initialize the graph schema before the lock wait exhausted"
                raise LockTimeoutError(message) from error
            raise

    @classmethod
    def _validated_timeout(cls, busy_timeout: int | None) -> int:
        """Validate a configured busy timeout.

        Parameters
        ----------
        busy_timeout : int | None
            Requested timeout in milliseconds, or ``None`` for the default.

        Returns
        -------
        int
            Timeout in milliseconds.

        Raises
        ------
        ValidationError
            If the timeout is not a non-negative integer.
        """
        if busy_timeout is None:
            return cls.BUSY_TIMEOUT_MS
        if isinstance(busy_timeout, bool) or not isinstance(busy_timeout, int) or busy_timeout < 0:
            message = "busy_timeout must be a non-negative integer"
            raise ValidationError(message)
        return busy_timeout

    @staticmethod
    def _is_lock_error(error: sqlite3.OperationalError) -> bool:
        """Report whether an operational error is a lock wait.

        Parameters
        ----------
        error : sqlite3.OperationalError
            Failure reported by SQLite.

        Returns
        -------
        bool
            ``True`` for a ``database is locked`` failure.
        """
        return "locked" in str(error).lower()
