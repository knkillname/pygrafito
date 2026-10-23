# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Explicit write transactions."""

import contextlib
from collections.abc import Iterator
from sqlite3 import Connection, Error
from types import TracebackType
from typing import Self

from pygrafito.model import (
    Node,
    Relationship,
    TransactionError,
    ValidationError,
    Value,
)
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository


class Transaction:
    """Group graph writes in one ``BEGIN IMMEDIATE`` transaction.

    Parameters
    ----------
    connection : Connection
        Connection shared with the repositories.
    node_repository : NodeRepository
        Repository used for node writes.
    relationship_repository : RelationshipRepository
        Repository used for relationship writes.
    """

    def __init__(
        self,
        connection: Connection,
        node_repository: NodeRepository,
        relationship_repository: RelationshipRepository,
    ) -> None:
        self._connection = connection
        self._node_repository = node_repository
        self._relationship_repository = relationship_repository
        self._active = False
        self._finished = False

    def __enter__(self) -> Self:
        """Start the transaction.

        Returns
        -------
        Self
            The active transaction.

        Raises
        ------
        TransactionError
            If the transaction is already active, was already used, or SQLite
            cannot start a transaction.
        """
        if self._finished:
            message = "transaction has already been used"
            raise TransactionError(message)
        if self._active:
            message = "transaction is already active"
            raise TransactionError(message)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except Error as error:
            message = "could not start a graph transaction"
            raise TransactionError(message) from error
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Commit on success or roll back on failure.

        Parameters
        ----------
        exc_type : type[BaseException] | None
            Exception type raised inside the context, if any.
        _exc_value : BaseException | None
            Exception instance raised inside the context, if any.
        _traceback : TracebackType | None
            Traceback raised inside the context, if any.

        Raises
        ------
        TransactionError
            If the transaction is not active or SQLite cannot finish it.
        """
        if not self._active:
            message = "transaction is not active"
            raise TransactionError(message)
        try:
            if exc_type is None:
                self._connection.execute("COMMIT")
            else:
                self._connection.execute("ROLLBACK")
        except Error as error:
            if self._connection.in_transaction:
                with contextlib.suppress(Error):
                    self._connection.execute("ROLLBACK")
            message = "could not finish a graph transaction"
            raise TransactionError(message) from error
        finally:
            self._active = False
            self._finished = True

    def add_node(
        self,
        *labels: str,
        **properties: Value,
    ) -> Node:
        """Create a node inside the transaction.

        Parameters
        ----------
        *labels : str
            Labels to attach.
        **properties : Value
            Properties to attach.

        Returns
        -------
        Node
            Snapshot of the created node.
        """
        self._require_active()
        return self._node_repository.create(labels, properties)

    def add_relationship(
        self,
        start: Node | int,
        rel_type: str,
        end: Node | int,
        **properties: Value,
    ) -> Relationship:
        """Create a relationship inside the transaction.

        Parameters
        ----------
        start : Node | int
            Start node or its id.
        rel_type : str
            Non-empty relationship type.
        end : Node | int
            End node or its id.
        **properties : Value
            Properties to attach.

        Returns
        -------
        Relationship
            Snapshot of the created relationship.
        """
        self._require_active()
        return self._relationship_repository.create(
            self._node_id(start),
            rel_type,
            self._node_id(end),
            properties,
        )

    def set_properties(
        self,
        element: Node | Relationship,
        **properties: Value | None,
    ) -> Node | Relationship:
        """Set or remove properties on a node or relationship.

        Parameters
        ----------
        element : Node | Relationship
            Element to update.
        **properties : Value | None
            Properties to assign. ``None`` removes a property.

        Returns
        -------
        Node | Relationship
            Snapshot of the updated element.
        """
        self._require_active()
        if isinstance(element, Node):
            return self._node_repository.set_properties(element.id, properties)
        if isinstance(element, Relationship):
            return self._relationship_repository.set_properties(element.id, properties)
        message = "element must be a Node or Relationship snapshot"
        raise ValidationError(message)

    def remove_properties(
        self,
        element: Node | Relationship,
        *keys: str,
    ) -> Node | Relationship:
        """Remove properties from a node or relationship.

        Parameters
        ----------
        element : Node | Relationship
            Element to update.
        *keys : str
            Property keys to remove.

        Returns
        -------
        Node | Relationship
            Snapshot of the updated element.
        """
        self._require_active()
        if isinstance(element, Node):
            return self._node_repository.remove_properties(element.id, keys)
        if isinstance(element, Relationship):
            return self._relationship_repository.remove_properties(element.id, keys)
        message = "element must be a Node or Relationship snapshot"
        raise ValidationError(message)

    def add_labels(
        self,
        node: Node | int,
        *labels: str,
    ) -> Node:
        """Add labels to a node inside the transaction.

        Parameters
        ----------
        node : Node | int
            Node or its id.
        *labels : str
            Labels to add.

        Returns
        -------
        Node
            Snapshot of the updated node.
        """
        self._require_active()
        return self._node_repository.add_labels(self._node_id(node), labels)

    def remove_labels(
        self,
        node: Node | int,
        *labels: str,
    ) -> Node:
        """Remove labels from a node inside the transaction.

        Parameters
        ----------
        node : Node | int
            Node or its id.
        *labels : str
            Labels to remove.

        Returns
        -------
        Node
            Snapshot of the updated node.
        """
        self._require_active()
        return self._node_repository.remove_labels(self._node_id(node), labels)

    def delete(
        self,
        element: Node | Relationship,
        *,
        detach: bool = False,
    ) -> None:
        """Delete a node or relationship inside the transaction.

        Parameters
        ----------
        element : Node | Relationship
            Element to delete.
        detach : bool, optional
            Whether to remove incident relationships before deleting a node,
            by default ``False``.

        Raises
        ------
        ValidationError
            If the element is not a node or relationship snapshot.
        """
        self._require_active()
        if isinstance(element, Relationship):
            self._relationship_repository.delete(element.id)
            return
        if isinstance(element, Node):
            self._node_repository.delete(element.id, detach=detach)
            return
        message = "element must be a Node or Relationship snapshot"
        raise ValidationError(message)

    def node(self, node_id: int) -> Node:
        """Read a node inside the transaction.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        Node
            Snapshot of the node.
        """
        self._require_active()
        return self._node_repository.get(node_id)

    def relationship(self, relationship_id: int) -> Relationship:
        """Read a relationship inside the transaction.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.

        Returns
        -------
        Relationship
            Snapshot of the relationship.
        """
        self._require_active()
        return self._relationship_repository.get(relationship_id)

    def find_nodes(
        self,
        *labels: str,
        **properties: Value,
    ) -> Iterator[Node]:
        """Find nodes inside the transaction.

        Parameters
        ----------
        *labels : str
            Labels every match must carry.
        **properties : Value
            Exact property values every match must have.

        Returns
        -------
        Iterator[Node]
            Matching node snapshots.
        """
        self._require_active()
        return self._node_repository.find(labels, properties)

    def find_relationships(
        self,
        rel_type: str | None = None,
        **properties: Value,
    ) -> Iterator[Relationship]:
        """Find relationships inside the transaction.

        Parameters
        ----------
        rel_type : str | None, optional
            Relationship type every match must have, by default any type.
        **properties : Value
            Exact property values every match must have.

        Returns
        -------
        Iterator[Relationship]
            Matching relationship snapshots.
        """
        self._require_active()
        return self._relationship_repository.find(rel_type, properties)

    def _require_active(self) -> None:
        """Reject operations outside an active transaction.

        Raises
        ------
        TransactionError
            If the transaction has not been started or has already finished.
        """
        if not self._active:
            message = "transaction is not active"
            raise TransactionError(message)

    @staticmethod
    def _node_id(node: Node | int) -> int:
        """Extract a node id from a snapshot or integer.

        Parameters
        ----------
        node : Node | int
            Node snapshot or id.

        Returns
        -------
        int
            Identifier of the node.

        Raises
        ------
        ValidationError
            If the argument is not a node snapshot or integer id.
        """
        if isinstance(node, Node):
            return node.id
        if isinstance(node, int) and not isinstance(node, bool):
            return node
        message = "node must be a Node snapshot or integer id"
        raise ValidationError(message)
