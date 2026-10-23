# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""SQLite connection management for the graph store."""

import sqlite3
from pathlib import Path
from sqlite3 import Connection

from pygrafito.model import NotFoundError
from pygrafito.storage.schema import Schema


class Database:
    """Own one configured SQLite connection and the graph schema.

    Parameters
    ----------
    path : str | Path
        Filesystem path of the database, or ``":memory:"``.
    create : bool, optional
        Whether a missing database file may be created, by default ``True``.

    Raises
    ------
    NotFoundError
        If ``create`` is false and the database file does not exist.
    UnsupportedSqliteError
        If the SQLite runtime lacks the features the graph requires.
    """

    BUSY_TIMEOUT_MS: int = 5000
    MEMORY_PATH: str = ":memory:"

    def __init__(self, path: str | Path, *, create: bool = True) -> None:
        location = str(path)
        if not create and location != self.MEMORY_PATH and not Path(location).exists():
            message = f"database file does not exist: {location}"
            raise NotFoundError(message)
        self._location = location
        self._closed = False
        self._connection = sqlite3.connect(
            location,
            timeout=self.BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
            check_same_thread=True,
        )
        self._configure()
        Schema.verify_json_support(self._connection)
        Schema(self._connection).bootstrap()

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

    def close(self) -> None:
        """Close the underlying connection.

        Closing an already closed database is a no-op.
        """
        if self._closed:
            return
        if self._connection.in_transaction:
            self._connection.rollback()
        self._connection.close()
        self._closed = True

    def _configure(self) -> None:
        """Apply the pragmas required by the storage layer."""
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(f"PRAGMA busy_timeout = {self.BUSY_TIMEOUT_MS}")
        if self._location != self.MEMORY_PATH:
            self._connection.execute("PRAGMA journal_mode = WAL")
