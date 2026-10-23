# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Database schema bootstrap and compatibility checks."""

import sqlite3
from sqlite3 import Connection, OperationalError

from pygrafito.model import UnsupportedSqliteError


class Schema:
    """Own the database schema and SQLite feature checks.

    Parameters
    ----------
    connection : Connection
        Open connection to the graph database.
    """

    VERSION: int = 1
    MINIMUM_SQLITE_VERSION: tuple[int, int, int] = (3, 38, 0)

    _STATEMENTS: tuple[str, ...] = (
        """
        CREATE TABLE IF NOT EXISTS nodes (
            id    INTEGER PRIMARY KEY,
            props TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(props))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS node_labels (
            node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            label   TEXT NOT NULL,
            PRIMARY KEY (node_id, label)
        ) WITHOUT ROWID
        """,
        "CREATE INDEX IF NOT EXISTS node_labels_by_label ON node_labels (label, node_id)",
        """
        CREATE TABLE IF NOT EXISTS relationships (
            id       INTEGER PRIMARY KEY,
            src      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE RESTRICT,
            dst      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE RESTRICT,
            rel_type TEXT NOT NULL,
            props    TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(props))
        )
        """,
        "CREATE INDEX IF NOT EXISTS rel_by_src ON relationships (src, rel_type, dst)",
        "CREATE INDEX IF NOT EXISTS rel_by_dst ON relationships (dst, rel_type, src)",
    )

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def bootstrap(self) -> None:
        """Create the schema when missing and record the schema version.

        The operation is idempotent: existing tables and indexes are left
        untouched, and an already-current ``user_version`` is not rewritten.

        Raises
        ------
        UnsupportedSqliteError
            If the database declares a newer schema version than this library
            can operate.
        """
        current = self.version()
        if current > self.VERSION:
            message = (
                f"database schema version {current} is newer than the supported "
                f"version {self.VERSION}"
            )
            raise UnsupportedSqliteError(message)
        for statement in self._STATEMENTS:
            self._connection.execute(statement)
        if current != self.VERSION:
            self._connection.execute(f"PRAGMA user_version = {self.VERSION}")

    def version(self) -> int:
        """Read the schema version stored in ``PRAGMA user_version``.

        Returns
        -------
        int
            Current schema version, or zero when never initialized.

        Raises
        ------
        UnsupportedSqliteError
            If SQLite reports a non-integer version.
        """
        row = self._connection.execute("PRAGMA user_version").fetchone()
        if row is None:
            return 0
        value: object = row[0]
        if not isinstance(value, int):
            message = "SQLite reported a non-integer user_version"
            raise UnsupportedSqliteError(message)
        return value

    @classmethod
    def verify_json_support(
        cls,
        connection: Connection,
        runtime_version: tuple[int, int, int] | None = None,
    ) -> None:
        """Verify that the runtime provides the required JSON1 functions.

        Parameters
        ----------
        connection : Connection
            Open connection whose runtime is checked.
        runtime_version : tuple[int, int, int] | None, optional
            SQLite version to validate, by default the runtime's version.

        Raises
        ------
        UnsupportedSqliteError
            If SQLite is older than the required version, lacks JSON
            functions, or reports unexpected JSON type metadata.
        """
        version = sqlite3.sqlite_version_info if runtime_version is None else runtime_version
        if version < cls.MINIMUM_SQLITE_VERSION:
            required = ".".join(str(part) for part in cls.MINIMUM_SQLITE_VERSION)
            message = f"SQLite {required} or newer is required; found {'.'.join(map(str, version))}"
            raise UnsupportedSqliteError(message)
        try:
            row = connection.execute(
                """SELECT json_valid('{"a":1}'), json_type('{"a":1}', '$.a')"""
            ).fetchone()
        except OperationalError as error:
            message = "the SQLite runtime does not provide the JSON1 functions"
            raise UnsupportedSqliteError(message) from error
        if row is None or row[0] != 1 or row[1] != "integer":
            message = "the SQLite runtime reported unexpected JSON function results"
            raise UnsupportedSqliteError(message)
