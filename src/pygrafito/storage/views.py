# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Read-only SQL views and their publication version."""

import contextlib
import sqlite3
from sqlite3 import Connection

from pygrafito.model import LockTimeoutError, UnsupportedSqliteError


class Views:
    """Create, upgrade, and version the public interop views.

    Parameters
    ----------
    connection : Connection
        Open connection to the graph database.
    """

    VERSION: int = 2
    FORMAT: str = "pygrafito"
    NODES: str = "graph_nodes"
    NODE_LABELS: str = "graph_node_labels"
    RELATIONSHIPS: str = "graph_relationships"
    META: str = "graph_meta"
    RESERVED: frozenset[str] = frozenset({NODES, NODE_LABELS, RELATIONSHIPS, META})

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def check_names(self) -> None:
        """Reject a reserved name that is not an identifiable graph view.

        Raises
        ------
        UnsupportedSqliteError
            If a reserved name is a table, or a reserved view exists without
            the ``graph_meta`` marker.
        """
        objects = self._objects()
        for name, kind in objects.items():
            if kind == "table":
                message = f"cannot publish interop views: {name} is a table"
                raise UnsupportedSqliteError(message)
        if self.META not in objects and objects:
            names = ", ".join(sorted(objects))
            message = f"cannot publish interop views: {names} exist without {self.META}"
            raise UnsupportedSqliteError(message)

    def ensure(self, *, readonly: bool = False) -> None:
        """Publish missing or outdated views on a write-capable connection.

        Parameters
        ----------
        readonly : bool, optional
            Whether the connection cannot take a write lock, by default
            ``False``. A read-only connection is never modified.

        Raises
        ------
        UnsupportedSqliteError
            If a reserved name is occupied or ``graph_meta`` is malformed.
        LockTimeoutError
            If the publication write lock cannot be obtained.
        """
        if readonly:
            return
        self.check_names()
        if not self._needs_update():
            return
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower():
                message = "could not publish interop views before the lock wait exhausted"
                raise LockTimeoutError(message) from error
            raise
        try:
            self.check_names()
            if self._needs_update():
                self._recreate()
            self._connection.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                self._connection.execute("ROLLBACK")
            raise

    def version(self) -> int | None:
        """Return the published view version.

        Returns
        -------
        int | None
            Published version, or ``None`` when the views or the version record
            are absent or malformed.
        """
        try:
            row = self._connection.execute(
                f"SELECT value FROM {self.META} WHERE key = 'view_version'"
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        try:
            return int(str(row[0]))
        except ValueError:
            return None

    def _objects(self) -> dict[str, str]:
        """Return the reserved names that exist as tables or views.

        Returns
        -------
        dict[str, str]
            Object name mapped to its ``sqlite_master`` type.
        """
        placeholders = ", ".join("?" for _ in self.RESERVED)
        rows = self._connection.execute(
            f"SELECT name, type FROM sqlite_master "
            f"WHERE type IN ('table', 'view') AND name IN ({placeholders})",
            sorted(self.RESERVED),
        ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def _needs_update(self) -> bool:
        """Report whether the views must be created or replaced.

        Returns
        -------
        bool
            ``True`` when the views are missing, older, or incomplete.

        Raises
        ------
        UnsupportedSqliteError
            If ``graph_meta`` exists but does not carry a valid version.
        """
        objects = self._objects()
        if self.META not in objects:
            return True
        version = self.version()
        if version is None:
            message = f"{self.META} does not carry a valid view_version"
            raise UnsupportedSqliteError(message)
        if version > self.VERSION:
            return False
        if version < self.VERSION:
            return True
        return any(name not in objects for name in self.RESERVED)

    def _recreate(self) -> None:
        """Replace every reserved view with the current definitions."""
        for name in sorted(self.RESERVED):
            self._connection.execute(f"DROP VIEW IF EXISTS {name}")
        for statement in self._definitions():
            self._connection.execute(statement)

    @classmethod
    def _definitions(cls) -> tuple[str, ...]:
        """Return the current view definitions.

        Returns
        -------
        tuple[str, ...]
            One ``CREATE VIEW`` statement per public view.
        """
        return (
            f"""
            CREATE VIEW {cls.NODES} AS
            SELECT n.id AS id,
                   CAST((SELECT json_group_array(label)
                           FROM (SELECT label FROM node_labels
                                  WHERE node_id = n.id ORDER BY label)) AS TEXT) AS labels,
                   n.props AS properties
              FROM nodes AS n
            """,
            f"""
            CREATE VIEW {cls.NODE_LABELS} AS
            SELECT node_id AS node_id, label AS label
              FROM node_labels
            """,
            f"""
            CREATE VIEW {cls.RELATIONSHIPS} AS
            SELECT r.id AS id,
                   r.src AS start_id,
                   r.dst AS end_id,
                   CAST((SELECT json_group_array(label)
                           FROM (SELECT label FROM relationship_labels
                                  WHERE relationship_id = r.id ORDER BY label)) AS TEXT) AS labels,
                   r.directed AS directed,
                   r.props AS properties
              FROM relationships AS r
            """,
            f"""
            CREATE VIEW {cls.META} AS
            SELECT CAST('format' AS TEXT) AS key, CAST('{cls.FORMAT}' AS TEXT) AS value
            UNION ALL
            SELECT CAST('view_version' AS TEXT), CAST('{cls.VERSION}' AS TEXT)
            """,
        )


__all__ = ["Views"]
