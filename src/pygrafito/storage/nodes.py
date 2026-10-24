# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Node persistence and lookup."""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from sqlite3 import Connection
from typing import Any, ClassVar

from pygrafito.model import (
    ConnectedNodeError,
    Node,
    NotFoundError,
    TransactionError,
    Value,
)
from pygrafito.storage.codec import PropertyCodec


class NodeRepository:
    """Read and write nodes, labels, and node properties.

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

    def create(
        self,
        labels: Iterable[str] = (),
        properties: Mapping[str, Value] | None = None,
    ) -> Node:
        """Create a node with labels and properties.

        Parameters
        ----------
        labels : Iterable[str], optional
            Labels to attach, by default none.
        properties : Mapping[str, Value] | None, optional
            Properties to attach, by default none.

        Returns
        -------
        Node
            Snapshot of the created node.

        Raises
        ------
        ValidationError
            If a label, property key, or property value is invalid.
        """
        validated_labels = self._validate_labels(labels)
        encoded = self._codec.encode_properties({} if properties is None else properties)
        cursor = self._connection.execute("INSERT INTO nodes (props) VALUES (?)", (encoded,))
        node_id = cursor.lastrowid
        if node_id is None:
            message = "SQLite did not return an id for the created node"
            raise TransactionError(message)
        if validated_labels:
            self._connection.executemany(
                "INSERT INTO node_labels (node_id, label) VALUES (?, ?)",
                [(node_id, label) for label in sorted(validated_labels)],
            )
        return Node(
            id=node_id,
            labels=validated_labels,
            properties=self._codec.decode_properties(encoded),
        )

    def get(self, node_id: int) -> Node:
        """Read a node by id.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        Node
            Snapshot of the node.

        Raises
        ------
        NotFoundError
            If no node has the given id.
        """
        row = self._connection.execute(
            "SELECT props FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            message = f"node {node_id} does not exist"
            raise NotFoundError(message)
        return self._node_from_payload(node_id, str(row[0]), self._labels(node_id))

    def exists(self, node_id: int) -> bool:
        """Report whether a node id is present.

        Parameters
        ----------
        node_id : int
            Identifier to check.

        Returns
        -------
        bool
            ``True`` when the node exists.
        """
        row = self._connection.execute(
            "SELECT 1 FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        return row is not None

    def get_many(self, node_ids: Iterable[int]) -> dict[int, Node]:
        """Read several nodes and their labels in one batch.

        Parameters
        ----------
        node_ids : Iterable[int]
            Identifiers to read. Duplicates are collapsed and missing ids are
            omitted from the result.

        Returns
        -------
        dict[int, Node]
            Node snapshots keyed by id.
        """
        unique_ids = tuple(dict.fromkeys(int(node_id) for node_id in node_ids))
        if not unique_ids:
            return {}
        rows: list[tuple[Any, ...]] = []
        for offset in range(0, len(unique_ids), self.MAXIMUM_PARAMETERS):
            chunk = unique_ids[offset : offset + self.MAXIMUM_PARAMETERS]
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                self._connection.execute(
                    f"SELECT id, props FROM nodes WHERE id IN ({placeholders})",
                    list(chunk),
                ).fetchall()
            )
        labels_by_node = self._labels_for([int(row[0]) for row in rows])
        return {
            int(row[0]): self._node_from_payload(
                int(row[0]),
                str(row[1]),
                labels_by_node.get(int(row[0]), frozenset()),
            )
            for row in rows
        }

    def add_labels(
        self,
        node_id: int,
        labels: Iterable[str],
    ) -> Node:
        """Add labels to an existing node.

        Parameters
        ----------
        node_id : int
            Identifier of the node.
        labels : Iterable[str]
            Labels to add. Existing labels are left unchanged.

        Returns
        -------
        Node
            Snapshot of the updated node.

        Raises
        ------
        NotFoundError
            If the node does not exist.
        ValidationError
            If a label is not a non-empty string.
        """
        self.get(node_id)
        validated_labels = self._validate_labels(labels)
        self._connection.executemany(
            "INSERT OR IGNORE INTO node_labels (node_id, label) VALUES (?, ?)",
            [(node_id, label) for label in sorted(validated_labels)],
        )
        return self.get(node_id)

    def remove_labels(
        self,
        node_id: int,
        labels: Iterable[str],
    ) -> Node:
        """Remove labels from an existing node.

        Parameters
        ----------
        node_id : int
            Identifier of the node.
        labels : Iterable[str]
            Labels to remove. Missing labels are ignored.

        Returns
        -------
        Node
            Snapshot of the updated node.

        Raises
        ------
        NotFoundError
            If the node does not exist.
        ValidationError
            If a label is not a non-empty string.
        """
        self.get(node_id)
        validated_labels = self._validate_labels(labels)
        self._connection.executemany(
            "DELETE FROM node_labels WHERE node_id = ? AND label = ?",
            [(node_id, label) for label in sorted(validated_labels)],
        )
        return self.get(node_id)

    def set_properties(
        self,
        node_id: int,
        properties: Mapping[str, Value | None],
    ) -> Node:
        """Set or remove node properties.

        Parameters
        ----------
        node_id : int
            Identifier of the node.
        properties : Mapping[str, Value | None]
            Properties to assign. A ``None`` value removes the property.

        Returns
        -------
        Node
            Snapshot of the updated node.

        Raises
        ------
        NotFoundError
            If the node does not exist.
        ValidationError
            If a key or value is invalid.
        """
        current = dict(self.get(node_id))
        for key, value in properties.items():
            property_key = self._codec.validate_identifier(key, "property key")
            if value is None:
                current.pop(property_key, None)
            else:
                current[property_key] = self._codec.validate_value(value)
        return self._write_properties(node_id, current)

    def remove_properties(
        self,
        node_id: int,
        keys: Iterable[str],
    ) -> Node:
        """Remove node properties.

        Parameters
        ----------
        node_id : int
            Identifier of the node.
        keys : Iterable[str]
            Property keys to remove. Missing keys are ignored.

        Returns
        -------
        Node
            Snapshot of the updated node.

        Raises
        ------
        NotFoundError
            If the node does not exist.
        ValidationError
            If a key is not a non-empty string.
        """
        current = dict(self.get(node_id))
        for key in keys:
            property_key = self._codec.validate_identifier(key, "property key")
            current.pop(property_key, None)
        return self._write_properties(node_id, current)

    def find(
        self,
        labels: Iterable[str] = (),
        properties: Mapping[str, Value] | None = None,
    ) -> Iterator[Node]:
        """Find nodes by all given labels and exact property values.

        Parameters
        ----------
        labels : Iterable[str], optional
            Labels every matching node must carry, by default none.
        properties : Mapping[str, Value] | None, optional
            Exact property values every matching node must have, by default none.

        Returns
        -------
        Iterator[Node]
            Matching node snapshots ordered by id.

        Raises
        ------
        ValidationError
            If a label, key, or value is invalid.
        """
        validated_labels = sorted(self._validate_labels(labels))
        clauses: list[str] = []
        parameters: list[object] = []
        for label in validated_labels:
            clauses.append(
                "EXISTS (SELECT 1 FROM node_labels label_filter "
                "WHERE label_filter.node_id = nodes.id AND label_filter.label = ?)"
            )
            parameters.append(label)
        if properties:
            for key, value in properties.items():
                path = self._codec.sql_json_path(key)
                clauses.append(f"json_type(nodes.props, {path}) = ?")
                parameters.append(self._codec.json_type(value))
                clauses.append(f"json_extract(nodes.props, {path}) = ?")
                parameters.append(self._codec.comparison_value(value))
        query = "SELECT nodes.id, nodes.props FROM nodes"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY nodes.id"
        rows = self._connection.execute(query, parameters).fetchall()
        node_ids = [int(row[0]) for row in rows]
        labels_by_node = self._labels_for(node_ids)
        return self._nodes_from_rows(rows, labels_by_node)

    def all(self) -> Iterator[Node]:
        """Iterate over every node.

        Returns
        -------
        Iterator[Node]
            All node snapshots ordered by id.
        """
        return self.find()

    def delete(self, node_id: int, *, detach: bool = False) -> None:
        """Delete a node.

        Parameters
        ----------
        node_id : int
            Identifier of the node.
        detach : bool, optional
            Whether to remove incident relationships first, by default ``False``.

        Raises
        ------
        NotFoundError
            If the node does not exist.
        ConnectedNodeError
            If the node has relationships and ``detach`` is false.
        """
        self.get(node_id)
        if self.is_connected(node_id):
            if not detach:
                message = f"node {node_id} still has relationships; delete with detach=True"
                raise ConnectedNodeError(message)
            self._connection.execute(
                "DELETE FROM relationships WHERE src = ? OR dst = ?",
                (node_id, node_id),
            )
        self._connection.execute("DELETE FROM nodes WHERE id = ?", (node_id,))

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

    def _labels(self, node_id: int) -> frozenset[str]:
        """Read the labels attached to a node.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        frozenset[str]
            Labels attached to the node.
        """
        rows = self._connection.execute(
            "SELECT label FROM node_labels WHERE node_id = ? ORDER BY label",
            (node_id,),
        ).fetchall()
        return frozenset(str(row[0]) for row in rows)

    def _labels_for(
        self,
        node_ids: Sequence[int],
    ) -> dict[int, frozenset[str]]:
        """Read labels for several nodes at once.

        Parameters
        ----------
        node_ids : Sequence[int]
            Identifiers whose labels are needed.

        Returns
        -------
        dict[int, frozenset[str]]
            Labels keyed by node id.
        """
        if not node_ids:
            return {}
        placeholders = ", ".join("?" for _ in node_ids)
        rows = self._connection.execute(
            f"SELECT node_id, label FROM node_labels WHERE node_id IN ({placeholders})",
            list(node_ids),
        ).fetchall()
        labels: dict[int, set[str]] = {node_id: set() for node_id in node_ids}
        for node_id, label in rows:
            labels[int(node_id)].add(str(label))
        return {node_id: frozenset(values) for node_id, values in labels.items()}

    def _nodes_from_rows(
        self,
        rows: Sequence[tuple[Any, ...]],
        labels_by_node: Mapping[int, frozenset[str]],
    ) -> Iterator[Node]:
        """Build node snapshots from database rows.

        Parameters
        ----------
        rows : Sequence[tuple[Any, ...]]
            Rows containing an id and encoded properties.
        labels_by_node : Mapping[int, frozenset[str]]
            Labels keyed by node id.

        Yields
        ------
        Node
            Snapshot for each row.
        """
        for row in rows:
            node_id = int(row[0])
            yield self._node_from_payload(
                node_id,
                str(row[1]),
                labels_by_node.get(node_id, frozenset()),
            )

    def _node_from_payload(
        self,
        node_id: int,
        payload: str,
        labels: frozenset[str],
    ) -> Node:
        """Build one node snapshot from its stored payload.

        Parameters
        ----------
        node_id : int
            Identifier of the node.
        payload : str
            Encoded property text.
        labels : frozenset[str]
            Labels attached to the node.

        Returns
        -------
        Node
            Snapshot of the node.
        """
        return Node(
            id=node_id,
            labels=labels,
            properties=self._codec.decode_properties(payload),
        )

    def _write_properties(
        self,
        node_id: int,
        properties: Mapping[str, Value],
    ) -> Node:
        """Replace the stored property object of a node.

        Parameters
        ----------
        node_id : int
            Identifier of the node.
        properties : Mapping[str, Value]
            Complete property mapping to store.

        Returns
        -------
        Node
            Snapshot of the updated node.
        """
        encoded = self._codec.encode_properties(properties)
        self._connection.execute(
            "UPDATE nodes SET props = ? WHERE id = ?",
            (encoded, node_id),
        )
        return self._node_from_payload(node_id, encoded, self._labels(node_id))

    def _validate_labels(
        self,
        labels: Iterable[str],
    ) -> frozenset[str]:
        """Validate and deduplicate labels.

        Parameters
        ----------
        labels : Iterable[str]
            Candidate labels.

        Returns
        -------
        frozenset[str]
            Validated labels.

        Raises
        ------
        ValidationError
            If a label is not a non-empty string.
        """
        return frozenset(self._codec.validate_identifier(label, "label") for label in labels)
