# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Declared property index identity, discovery, and DDL."""

import typing
from sqlite3 import Connection

from pygrafito.model import Index, IndexKind, NotFoundError
from pygrafito.storage.codec import PropertyCodec


class IndexRegistry:
    """Own the declared property indexes stored in one database.

    Parameters
    ----------
    connection : Connection
        Open connection to the graph database.
    codec : PropertyCodec
        Codec used to render quoted JSON paths.
    """

    PREFIX: typing.ClassVar[str] = "pygrafito_idx"
    TABLES: typing.ClassVar[dict[IndexKind, str]] = {
        IndexKind.NODE: "nodes",
        IndexKind.RELATIONSHIP: "relationships",
    }

    def __init__(self, connection: Connection, codec: PropertyCodec) -> None:
        self._connection = connection
        self._codec = codec

    @classmethod
    def name(cls, index: Index) -> str:
        """Return the SQLite index name for one declared index.

        The key is hex-encoded so the name is reversible and cannot contain
        SQL punctuation.

        Parameters
        ----------
        index : Index
            Declared index.

        Returns
        -------
        str
            Index name such as ``pygrafito_idx_node_6379636c6573``.
        """
        encoded = index.key.encode("utf-8").hex()
        return f"{cls.PREFIX}_{index.kind.value}_{encoded}"

    @classmethod
    def parse_name(cls, name: str) -> Index | None:
        """Recover a declared index from one SQLite index name.

        Parameters
        ----------
        name : str
            Candidate SQLite index name.

        Returns
        -------
        Index | None
            The declared index, or ``None`` when the name is not one of ours.
        """
        for kind in IndexKind:
            prefix = f"{cls.PREFIX}_{kind.value}_"
            if not name.startswith(prefix):
                continue
            try:
                key = bytes.fromhex(name[len(prefix) :]).decode("utf-8")
            except ValueError:
                return None
            if not key:
                return None
            return Index(kind, key)
        return None

    def all(self) -> tuple[Index, ...]:
        """Return every declared index in the database.

        Returns
        -------
        tuple[Index, ...]
            Declared indexes ordered by element kind and key.
        """
        declared: set[Index] = set()
        for kind, table in self.TABLES.items():
            for row in self._connection.execute(f"PRAGMA index_list({table})"):
                parsed = self.parse_name(str(row[1]))
                if parsed is not None and parsed.kind is kind:
                    declared.add(parsed)
        return tuple(sorted(declared, key=lambda index: (index.kind.value, index.key)))

    def exists(self, index: Index) -> bool:
        """Report whether one declared index exists.

        Parameters
        ----------
        index : Index
            Declared index.

        Returns
        -------
        bool
            ``True`` when the index is present.
        """
        row = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (self.name(index),),
        ).fetchone()
        return row is not None

    def ddl(self, index: Index) -> str:
        """Return the data-definition statement that creates an index.

        Parameters
        ----------
        index : Index
            Declared index.

        Returns
        -------
        str
            ``CREATE INDEX`` statement over the stored property document.
        """
        table = self.TABLES[index.kind]
        columns = self._codec.portable_index_columns(index.key)
        if columns is None:
            # SQLite builds before 3.47 cannot address a key that contains a
            # double quote or a control character. Keep the declaration
            # discoverable with an empty partial index; lookups fall back to
            # a json_each scan.
            return (
                f"CREATE INDEX IF NOT EXISTS {self.name(index)} ON {table} "
                f"(json_type(props, '$')) WHERE 0"
            )
        return f"CREATE INDEX IF NOT EXISTS {self.name(index)} ON {table} {columns}"

    def create(self, index: Index) -> None:
        """Create one declared index when it is absent.

        Parameters
        ----------
        index : Index
            Declared index.
        """
        self._connection.execute(self.ddl(index))

    def drop(self, index: Index) -> None:
        """Remove one declared index.

        Parameters
        ----------
        index : Index
            Declared index.

        Raises
        ------
        NotFoundError
            If the index is not present.
        """
        if not self.exists(index):
            message = f"index on {index.kind.value} key {index.key!r} does not exist"
            raise NotFoundError(message)
        self._connection.execute(f"DROP INDEX {self.name(index)}")
