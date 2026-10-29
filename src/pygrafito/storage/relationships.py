# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Relationship persistence and lookup."""

import json
import sqlite3
import typing
from collections.abc import Iterable, Iterator, Mapping, Sequence
from sqlite3 import Connection
from typing import Any, ClassVar

from pygrafito.model import (
    Direction,
    NotFoundError,
    Relationship,
    TransactionError,
    ValidationError,
    Value,
)
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.constraints import ConstraintRegistry, ConstraintTranslator


class RelationshipRepository:
    """Read and write labeled directed and undirected relationships.

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
        self._constraints = ConstraintRegistry(connection, property_codec)
        self._translator = ConstraintTranslator(connection, property_codec, self._constraints)

    MAXIMUM_PARAMETERS: ClassVar[int] = 32_766
    LABELS_COLUMN: ClassVar[str] = (
        "(SELECT json_group_array(label) FROM (SELECT label FROM relationship_labels "
        "WHERE relationship_id = {alias}.id ORDER BY label))"
    )

    def frontier(
        self,
        frontier: Sequence[int],
        direction: Direction,
        labels: frozenset[str] | None = None,
    ) -> Iterator[tuple[int, Relationship, int]]:
        """Yield one adjacency level for an ordered frontier.

        Edges are emitted per frontier node in the given order, outgoing
        before incoming, and by relationship id within each arm. In both
        direction mode a self-loop or an undirected edge is emitted once.

        Parameters
        ----------
        frontier : Sequence[int]
            Ordered node identifiers whose incident relationships are read.
        direction : Direction
            Direction to follow.
        labels : frozenset[str] | None, optional
            Allowed relationship labels, by default all labels.

        Yields
        ------
        tuple[int, Relationship, int]
            The frontier node, the relationship, and the node reached when
            following ``direction`` from it.
        """
        ordered = tuple(dict.fromkeys(int(node_id) for node_id in frontier))
        if not ordered:
            return
        label_values = () if labels is None else tuple(sorted(labels))
        label_filter = ""
        if label_values:
            placeholders = ", ".join("?" for _ in label_values)
            label_filter = (
                " AND EXISTS (SELECT 1 FROM relationship_labels AS label_filter "
                "WHERE label_filter.relationship_id = relationships.id "
                f"AND label_filter.label IN ({placeholders}))"
            )
        chunk_size = max(1, self.MAXIMUM_PARAMETERS - len(label_values))
        for offset in range(0, len(ordered), chunk_size):
            chunk = ordered[offset : offset + chunk_size]
            yield from self._frontier_chunk(chunk, direction, label_filter, label_values)

    def _frontier_chunk(
        self,
        chunk: Sequence[int],
        direction: Direction,
        label_filter: str,
        label_values: tuple[str, ...],
    ) -> Iterator[tuple[int, Relationship, int]]:
        """Read and order one frontier chunk.

        Parameters
        ----------
        chunk : Sequence[int]
            Frontier identifiers that fit in one statement.
        direction : Direction
            Direction to follow.
        label_filter : str
            SQL fragment restricting relationship labels, possibly empty.
        label_values : tuple[str, ...]
            Values bound to the label filter.

        Yields
        ------
        tuple[int, Relationship, int]
            Ordered frontier edges for this chunk.
        """
        placeholders = ", ".join("?" for _ in chunk)
        members = frozenset(chunk)
        outgoing: dict[int, list[tuple[Relationship, int]]] = {}
        incoming: dict[int, list[tuple[Relationship, int]]] = {}
        rows: list[tuple[Any, ...]] = []
        rows.extend(
            self._connection.execute(
                f"{self._select('relationships')} WHERE src IN ({placeholders})"
                f"{label_filter} ORDER BY id",
                (*chunk, *label_values),
            ).fetchall()
        )
        rows.extend(
            self._connection.execute(
                f"{self._select('relationships')} WHERE dst IN ({placeholders})"
                f"{label_filter} ORDER BY id",
                (*chunk, *label_values),
            ).fetchall()
        )
        seen_outgoing: dict[int, set[int]] = {}
        seen_incoming: dict[int, set[int]] = {}
        for relationship in self._relationships_from_rows(rows):
            if relationship.directed:
                if relationship.start_id in members:
                    self._append(
                        outgoing,
                        seen_outgoing,
                        relationship.start_id,
                        relationship,
                        relationship.end_id,
                    )
                if relationship.end_id in members:
                    self._append(
                        incoming,
                        seen_incoming,
                        relationship.end_id,
                        relationship,
                        relationship.start_id,
                    )
                continue
            if relationship.start_id in members:
                self._append(
                    outgoing,
                    seen_outgoing,
                    relationship.start_id,
                    relationship,
                    relationship.end_id,
                )
                self._append(
                    incoming,
                    seen_incoming,
                    relationship.start_id,
                    relationship,
                    relationship.end_id,
                )
            if relationship.end_id in members:
                self._append(
                    outgoing,
                    seen_outgoing,
                    relationship.end_id,
                    relationship,
                    relationship.start_id,
                )
                self._append(
                    incoming,
                    seen_incoming,
                    relationship.end_id,
                    relationship,
                    relationship.start_id,
                )
        for node_id in chunk:
            emitted: set[int] = set()
            if direction in (Direction.OUTGOING, Direction.BOTH):
                for relationship, target in outgoing.get(node_id, ()):
                    emitted.add(relationship.id)
                    yield node_id, relationship, target
            if direction in (Direction.INCOMING, Direction.BOTH):
                for relationship, target in incoming.get(node_id, ()):
                    if direction is Direction.BOTH and relationship.id in emitted:
                        continue
                    yield node_id, relationship, target

    @staticmethod
    def _append(
        bucket: dict[int, list[tuple[Relationship, int]]],
        seen: dict[int, set[int]],
        node_id: int,
        relationship: Relationship,
        target: int,
    ) -> None:
        """Append one edge to a frontier bucket without duplicates.

        Parameters
        ----------
        bucket : dict[int, list[tuple[Relationship, int]]]
            Frontier bucket keyed by node id.
        seen : dict[int, set[int]]
            Relationship ids already present per node.
        node_id : int
            Frontier node that owns the entry.
        relationship : Relationship
            Relationship to append.
        target : int
            Node reached through the relationship.
        """
        ids = seen.setdefault(node_id, set())
        if relationship.id in ids:
            return
        ids.add(relationship.id)
        bucket.setdefault(node_id, []).append((relationship, target))

    def create(
        self,
        start_id: int,
        labels: str | Iterable[str],
        end_id: int,
        properties: Mapping[str, Value] | None = None,
        *,
        directed: bool = True,
    ) -> Relationship:
        """Create a relationship between two existing nodes.

        Parameters
        ----------
        start_id : int
            Identifier of the first endpoint.
        labels : str | Iterable[str]
            Labels to attach; a string is one label.
        end_id : int
            Identifier of the second endpoint.
        directed : bool, optional
            Whether the endpoints carry source and destination meaning, by
            default ``True``.
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
            If a label, a property key, or a property value is invalid.
        """
        validated_labels = self._validate_labels(labels)
        if not isinstance(directed, bool):
            message = "relationship directed flag must be a boolean"
            raise ValidationError(message)
        self._require_node(start_id)
        self._require_node(end_id)
        encoded = self._codec.encode_properties({} if properties is None else properties)
        validated_properties = self._codec.decode_properties(encoded)
        savepoint = "pygrafito_relationship_write"
        self._connection.execute(f"SAVEPOINT {savepoint}")
        try:
            cursor = self._connection.execute(
                "INSERT INTO relationships (src, dst, directed, props) VALUES (?, ?, ?, ?)",
                (start_id, end_id, int(directed), encoded),
            )
            relationship_id = cursor.lastrowid
            if relationship_id is None:
                message = "SQLite did not return an id for the created relationship"
                raise TransactionError(message)
            if validated_labels:
                self._connection.executemany(
                    "INSERT INTO relationship_labels (relationship_id, label) VALUES (?, ?)",
                    [(relationship_id, label) for label in validated_labels],
                )
        except sqlite3.IntegrityError as error:
            self._rollback_write(savepoint)
            violation = self._translator.translate(
                error,
                properties=validated_properties,
                rel_labels=validated_labels,
            )
            if violation is not None:
                raise violation from error
            raise
        except BaseException:
            self._rollback_write(savepoint)
            raise
        self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        return Relationship(
            id=relationship_id,
            start_id=start_id,
            end_id=end_id,
            labels=validated_labels,
            directed=directed,
            properties=validated_properties,
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
            f"{self._select('relationships')} WHERE id = ?",
            (relationship_id,),
        ).fetchone()
        if row is None:
            message = f"relationship {relationship_id} does not exist"
            raise NotFoundError(message)
        return self._relationship_from_row(row)

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

    def add_labels(
        self,
        relationship_id: int,
        labels: Iterable[str],
    ) -> Relationship:
        """Add labels to an existing relationship.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.
        labels : Iterable[str]
            Labels to add. Existing labels are left unchanged.

        Returns
        -------
        Relationship
            Snapshot of the updated relationship.

        Raises
        ------
        NotFoundError
            If the relationship does not exist.
        ValidationError
            If a label is not a non-empty string.
        """
        self.get(relationship_id)
        validated_labels = self._validate_labels(labels)
        savepoint = "pygrafito_relationship_labels"
        self._connection.execute(f"SAVEPOINT {savepoint}")
        try:
            self._connection.executemany(
                "INSERT OR IGNORE INTO relationship_labels (relationship_id, label) VALUES (?, ?)",
                [(relationship_id, label) for label in validated_labels],
            )
        except sqlite3.IntegrityError as error:
            self._rollback_write(savepoint)
            violation = self._translator.translate(
                error,
                properties=dict(self.get(relationship_id)),
                rel_labels=validated_labels,
                exclude_id=relationship_id,
            )
            if violation is not None:
                raise violation from error
            raise
        except BaseException:
            self._rollback_write(savepoint)
            raise
        self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        return self.get(relationship_id)

    def remove_labels(
        self,
        relationship_id: int,
        labels: Iterable[str],
    ) -> Relationship:
        """Remove labels from an existing relationship.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.
        labels : Iterable[str]
            Labels to remove. Missing labels are ignored.

        Returns
        -------
        Relationship
            Snapshot of the updated relationship.

        Raises
        ------
        NotFoundError
            If the relationship does not exist.
        ValidationError
            If a label is not a non-empty string.
        """
        self.get(relationship_id)
        validated_labels = self._validate_labels(labels)
        self._connection.executemany(
            "DELETE FROM relationship_labels WHERE relationship_id = ? AND label = ?",
            [(relationship_id, label) for label in validated_labels],
        )
        return self.get(relationship_id)

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
        labels: Iterable[str] = (),
        properties: Mapping[str, Value] | None = None,
        *,
        directed: bool | None = None,
    ) -> Iterator[Relationship]:
        """Find relationships by all given labels and exact property values.

        Parameters
        ----------
        labels : Iterable[str], optional
            Labels every match must carry, by default none.
        properties : Mapping[str, Value] | None, optional
            Exact property values every match must have, by default none.
        directed : bool | None, optional
            Direction filter, by default any direction.

        Returns
        -------
        Iterator[Relationship]
            Matching relationship snapshots ordered by id.

        Raises
        ------
        ValidationError
            If a label, key, or value is invalid.
        """
        validated_labels = self._validate_labels(labels)
        clauses: list[str] = []
        parameters: list[object] = []
        for label in validated_labels:
            clauses.append(
                "EXISTS (SELECT 1 FROM relationship_labels AS label_filter "
                "WHERE label_filter.relationship_id = relationships.id "
                "AND label_filter.label = ?)"
            )
            parameters.append(label)
        if directed is not None:
            if not isinstance(directed, bool):
                message = "relationship directed flag must be a boolean"
                raise ValidationError(message)
            clauses.append("directed = ?")
            parameters.append(int(directed))
        if properties:
            for key, value in properties.items():
                type_expression = self._codec.property_type_expression("relationships.props", key)
                if isinstance(value, float) and self._codec.supports_exact_text(key):
                    clauses.append(f"{type_expression} = 'real'")
                    clauses.append(
                        f"{self._codec.exact_value_expression('relationships.props', key)} = ?"
                    )
                    parameters.append(self._codec.exact_comparison_value(key, value))
                    continue
                value_expression = self._codec.property_value_expression("relationships.props", key)
                clauses.append(f"{type_expression} = ?")
                parameters.append(self._codec.json_type(value))
                clauses.append(f"{value_expression} = ?")
                parameters.append(self._codec.comparison_value(value))
        query = self._select("relationships")
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

    @classmethod
    def _select(cls, alias: str) -> str:
        """Return the projection used for relationship rows.

        Parameters
        ----------
        alias : str
            Table alias.

        Returns
        -------
        str
            SQL selecting id, endpoints, direction, labels, and properties.
        """
        labels = cls.LABELS_COLUMN.format(alias=alias)
        return (
            f"SELECT {alias}.id, {alias}.src, {alias}.dst, {alias}.directed, "
            f"{labels}, {alias}.props FROM relationships AS {alias}"
        )

    def _relationships_from_rows(
        self,
        rows: Sequence[tuple[Any, ...]],
    ) -> Iterator[Relationship]:
        """Build relationship snapshots from database rows.

        Parameters
        ----------
        rows : Sequence[tuple[Any, ...]]
            Rows containing id, endpoints, direction, labels, and properties.

        Yields
        ------
        Relationship
            Snapshot for each row.
        """
        for row in rows:
            yield self._relationship_from_row(row)

    def _relationship_from_row(self, row: tuple[Any, ...]) -> Relationship:
        """Build one relationship snapshot from a database row.

        Parameters
        ----------
        row : tuple[Any, ...]
            Row containing id, endpoints, direction, labels, and properties.

        Returns
        -------
        Relationship
            Snapshot of the relationship.
        """
        raw_labels: object = json.loads(str(row[4])) if row[4] is not None else []
        labels = typing.cast(list[str], raw_labels)
        return Relationship(
            id=int(row[0]),
            start_id=int(row[1]),
            end_id=int(row[2]),
            labels=tuple(self._codec.validate_identifier(label, "label") for label in labels),
            directed=bool(row[3]),
            properties=self._codec.decode_properties(str(row[5])),
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
        try:
            self._connection.execute(
                "UPDATE relationships SET props = ? WHERE id = ?",
                (encoded, relationship_id),
            )
        except sqlite3.IntegrityError as error:
            violation = self._translator.translate(
                error,
                properties=properties,
                rel_labels=self.get(relationship_id).labels,
                exclude_id=relationship_id,
            )
            if violation is not None:
                raise violation from error
            raise
        return self.get(relationship_id)

    def _validate_labels(
        self,
        labels: str | Iterable[str],
    ) -> tuple[str, ...]:
        """Validate and deduplicate relationship labels.

        Parameters
        ----------
        labels : str | Iterable[str]
            Candidate labels. A string is one label.

        Returns
        -------
        tuple[str, ...]
            Sorted validated labels.

        Raises
        ------
        ValidationError
            If a label is not a non-empty string.
        """
        values = (labels,) if isinstance(labels, str) else tuple(labels)
        return tuple(sorted({self._codec.validate_identifier(label, "label") for label in values}))

    def _rollback_write(self, savepoint: str) -> None:
        """Undo the current relationship write, ignoring rollback failures.

        Parameters
        ----------
        savepoint : str
            Savepoint name to roll back.
        """
        try:
            self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except sqlite3.Error:
            return
