# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Relationship persistence and lookup."""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from sqlite3 import Connection
from typing import Any, ClassVar

from pygrafito.model import (
    Direction,
    NotFoundError,
    Relationship,
    TransactionError,
    Value,
)
from pygrafito.storage.codec import PropertyCodec


class RelationshipRepository:
    """Read and write directed typed relationships.

    Parameters
    ----------
    connection : Connection
        Open connection to the graph database.
    property_codec : PropertyCodec
        Codec used to validate and encode property values.
    """

    def __init__(
        self,
        connection: Connection,
        property_codec: PropertyCodec,
    ) -> None:
        self._connection = connection
        self._codec = property_codec

    MAXIMUM_PARAMETERS: ClassVar[int] = 32_766

    def frontier(
        self,
        frontier: Sequence[int],
        direction: Direction,
        types: frozenset[str] | None = None,
    ) -> Iterator[tuple[int, Relationship, int]]:
        """Yield one adjacency level for an ordered frontier.

        Edges are emitted per frontier node in the given order, outgoing
        before incoming, and by relationship id within each arm. In
        both-direction mode a self-loop is emitted once.

        Parameters
        ----------
        frontier : Sequence[int]
            Ordered node identifiers whose incident relationships are read.
        direction : Direction
            Direction to follow.
        types : frozenset[str] | None, optional
            Allowed relationship types, by default all types.

        Yields
        ------
        tuple[int, Relationship, int]
            The frontier node, the relationship, and the node reached when
            following ``direction`` from it.
        """
        ordered = tuple(dict.fromkeys(int(node_id) for node_id in frontier))
        if not ordered:
            return
        type_values = () if types is None else tuple(sorted(types))
        type_filter = ""
        if type_values:
            placeholders = ", ".join("?" for _ in type_values)
            type_filter = f" AND rel_type IN ({placeholders})"
        chunk_size = max(1, self.MAXIMUM_PARAMETERS - len(type_values))
        for offset in range(0, len(ordered), chunk_size):
            chunk = ordered[offset : offset + chunk_size]
            yield from self._frontier_chunk(chunk, direction, type_filter, type_values)

    def _frontier_chunk(
        self,
        chunk: Sequence[int],
        direction: Direction,
        type_filter: str,
        type_values: tuple[str, ...],
    ) -> Iterator[tuple[int, Relationship, int]]:
        """Read and order one frontier chunk.

        Parameters
        ----------
        chunk : Sequence[int]
            Frontier identifiers that fit in one statement.
        direction : Direction
            Direction to follow.
        type_filter : str
            SQL fragment restricting relationship types, possibly empty.
        type_values : tuple[str, ...]
            Values bound to the type filter.

        Yields
        ------
        tuple[int, Relationship, int]
            Ordered frontier edges for this chunk.
        """
        placeholders = ", ".join("?" for _ in chunk)
        outgoing: dict[int, list[tuple[Relationship, int]]] = {}
        incoming: dict[int, list[tuple[Relationship, int]]] = {}
        if direction in (Direction.OUTGOING, Direction.BOTH):
            rows = self._connection.execute(
                f"SELECT id, src, dst, rel_type, props FROM relationships "
                f"WHERE src IN ({placeholders}){type_filter} ORDER BY id",
                (*chunk, *type_values),
            ).fetchall()
            for relationship in self._relationships_from_rows(rows):
                outgoing.setdefault(relationship.start_id, []).append(
                    (relationship, relationship.end_id)
                )
        if direction in (Direction.INCOMING, Direction.BOTH):
            rows = self._connection.execute(
                f"SELECT id, src, dst, rel_type, props FROM relationships "
                f"WHERE dst IN ({placeholders}){type_filter} ORDER BY id",
                (*chunk, *type_values),
            ).fetchall()
            for relationship in self._relationships_from_rows(rows):
                if direction is Direction.BOTH and relationship.start_id == relationship.end_id:
                    continue
                incoming.setdefault(relationship.end_id, []).append(
                    (relationship, relationship.start_id)
                )
        for node_id in chunk:
            for relationship, target in outgoing.get(node_id, ()):
                yield node_id, relationship, target
            for relationship, target in incoming.get(node_id, ()):
                yield node_id, relationship, target

    def create(
        self,
        start_id: int,
        rel_type: str,
        end_id: int,
        properties: Mapping[str, Value] | None = None,
    ) -> Relationship:
        """Create a directed relationship between two existing nodes.

        Parameters
        ----------
        start_id : int
            Identifier of the start node.
        rel_type : str
            Non-empty relationship type.
        end_id : int
            Identifier of the end node.
        properties : Mapping[str, Value] | None, optional
            Properties to attach, by default none.

        Returns
        -------
        Relationship
            Snapshot of the created relationship.

        Raises
        ------
        NotFoundError
            If either endpoint does not exist.
        ValidationError
            If the type, a property key, or a property value is invalid.
        """
        relationship_type = self._codec.validate_identifier(rel_type, "relationship type")
        self._require_node(start_id)
        self._require_node(end_id)
        encoded = self._codec.encode_properties({} if properties is None else properties)
        cursor = self._connection.execute(
            "INSERT INTO relationships (src, dst, rel_type, props) VALUES (?, ?, ?, ?)",
            (start_id, end_id, relationship_type, encoded),
        )
        relationship_id = cursor.lastrowid
        if relationship_id is None:
            message = "SQLite did not return an id for the created relationship"
            raise TransactionError(message)
        return Relationship(
            id=relationship_id,
            rel_type=relationship_type,
            start_id=start_id,
            end_id=end_id,
            properties=self._codec.decode_properties(encoded),
        )

    def get(self, relationship_id: int) -> Relationship:
        """Read a relationship by id.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.

        Returns
        -------
        Relationship
            Snapshot of the relationship.

        Raises
        ------
        NotFoundError
            If no relationship has the given id.
        """
        row = self._connection.execute(
            "SELECT src, dst, rel_type, props FROM relationships WHERE id = ?",
            (relationship_id,),
        ).fetchone()
        if row is None:
            message = f"relationship {relationship_id} does not exist"
            raise NotFoundError(message)
        return Relationship(
            id=relationship_id,
            rel_type=str(row[2]),
            start_id=int(row[0]),
            end_id=int(row[1]),
            properties=self._codec.decode_properties(str(row[3])),
        )

    def exists(self, relationship_id: int) -> bool:
        """Report whether a relationship id is present.

        Parameters
        ----------
        relationship_id : int
            Identifier to check.

        Returns
        -------
        bool
            ``True`` when the relationship exists.
        """
        row = self._connection.execute(
            "SELECT 1 FROM relationships WHERE id = ?",
            (relationship_id,),
        ).fetchone()
        return row is not None

    def set_properties(
        self,
        relationship_id: int,
        properties: Mapping[str, Value | None],
    ) -> Relationship:
        """Set or remove relationship properties.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.
        properties : Mapping[str, Value | None]
            Properties to assign. A ``None`` value removes the property.

        Returns
        -------
        Relationship
            Snapshot of the updated relationship.

        Raises
        ------
        NotFoundError
            If the relationship does not exist.
        ValidationError
            If a key or value is invalid.
        """
        current = dict(self.get(relationship_id))
        for key, value in properties.items():
            property_key = self._codec.validate_identifier(key, "property key")
            if value is None:
                current.pop(property_key, None)
            else:
                current[property_key] = self._codec.validate_value(value)
        return self._write_properties(relationship_id, current)

    def remove_properties(
        self,
        relationship_id: int,
        keys: Iterable[str],
    ) -> Relationship:
        """Remove relationship properties.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.
        keys : Iterable[str]
            Property keys to remove. Missing keys are ignored.

        Returns
        -------
        Relationship
            Snapshot of the updated relationship.

        Raises
        ------
        NotFoundError
            If the relationship does not exist.
        ValidationError
            If a key is not a non-empty string.
        """
        current = dict(self.get(relationship_id))
        for key in keys:
            property_key = self._codec.validate_identifier(key, "property key")
            current.pop(property_key, None)
        return self._write_properties(relationship_id, current)

    def find(
        self,
        rel_type: str | None = None,
        properties: Mapping[str, Value] | None = None,
    ) -> Iterator[Relationship]:
        """Find relationships by type and exact property values.

        Parameters
        ----------
        rel_type : str | None, optional
            Relationship type every match must have, by default any type.
        properties : Mapping[str, Value] | None, optional
            Exact property values every match must have, by default none.

        Returns
        -------
        Iterator[Relationship]
            Matching relationship snapshots ordered by id.

        Raises
        ------
        ValidationError
            If the type, a key, or a value is invalid.
        """
        clauses: list[str] = []
        parameters: list[object] = []
        if rel_type is not None:
            clauses.append("rel_type = ?")
            parameters.append(self._codec.validate_identifier(rel_type, "relationship type"))
        if properties:
            for key, value in properties.items():
                path = self._codec.sql_json_path(key)
                clauses.append(f"json_type(relationships.props, {path}) = ?")
                parameters.append(self._codec.json_type(value))
                clauses.append(f"json_extract(relationships.props, {path}) = ?")
                parameters.append(self._codec.comparison_value(value))
        query = "SELECT id, src, dst, rel_type, props FROM relationships"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id"
        rows = self._connection.execute(query, parameters).fetchall()
        return self._relationships_from_rows(rows)

    def all(self) -> Iterator[Relationship]:
        """Iterate over every relationship.

        Returns
        -------
        Iterator[Relationship]
            All relationship snapshots ordered by id.
        """
        return self.find()

    def delete(self, relationship_id: int) -> None:
        """Delete a relationship.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.

        Raises
        ------
        NotFoundError
            If the relationship does not exist.
        """
        self.get(relationship_id)
        self._connection.execute(
            "DELETE FROM relationships WHERE id = ?",
            (relationship_id,),
        )

    def delete_incident(self, node_id: int) -> int:
        """Delete every relationship incident to a node.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        int
            Number of deleted relationships.
        """
        cursor = self._connection.execute(
            "DELETE FROM relationships WHERE src = ? OR dst = ?",
            (node_id, node_id),
        )
        return cursor.rowcount

    def is_connected(self, node_id: int) -> bool:
        """Report whether a node has at least one relationship.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        bool
            ``True`` when the node is an endpoint of any relationship.
        """
        row = self._connection.execute(
            "SELECT 1 FROM relationships WHERE src = ? OR dst = ? LIMIT 1",
            (node_id, node_id),
        ).fetchone()
        return row is not None

    def _require_node(self, node_id: int) -> None:
        """Ensure a node exists before creating a relationship.

        Parameters
        ----------
        node_id : int
            Identifier of the endpoint to check.

        Raises
        ------
        NotFoundError
            If the node does not exist.
        """
        row = self._connection.execute(
            "SELECT 1 FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            message = f"node {node_id} does not exist"
            raise NotFoundError(message)

    def _relationships_from_rows(
        self,
        rows: Sequence[tuple[Any, ...]],
    ) -> Iterator[Relationship]:
        """Build relationship snapshots from database rows.

        Parameters
        ----------
        rows : Sequence[tuple[Any, ...]]
            Rows containing id, endpoints, type, and encoded properties.

        Yields
        ------
        Relationship
            Snapshot for each row.
        """
        for row in rows:
            yield Relationship(
                id=int(row[0]),
                start_id=int(row[1]),
                end_id=int(row[2]),
                rel_type=str(row[3]),
                properties=self._codec.decode_properties(str(row[4])),
            )

    def _write_properties(
        self,
        relationship_id: int,
        properties: Mapping[str, Value],
    ) -> Relationship:
        """Replace the stored property object of a relationship.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.
        properties : Mapping[str, Value]
            Complete property mapping to store.

        Returns
        -------
        Relationship
            Snapshot of the updated relationship.
        """
        encoded = self._codec.encode_properties(properties)
        self._connection.execute(
            "UPDATE relationships SET props = ? WHERE id = ?",
            (encoded, relationship_id),
        )
        return self.get(relationship_id)
