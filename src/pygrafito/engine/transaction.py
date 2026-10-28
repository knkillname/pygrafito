# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Explicit write transactions."""

import contextlib
from collections.abc import Iterable, Iterator, Mapping
from sqlite3 import Connection, Error, OperationalError
from types import TracebackType
from typing import Self

from pygrafito.engine.query.executor import QueryExecutor
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.plan import PlanBuilder
from pygrafito.engine.query.results import QueryResult
from pygrafito.engine.query.semantic import SemanticAnalyzer
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import (
    LockTimeoutError,
    Node,
    Relationship,
    TransactionError,
    ValidationError,
    Value,
)
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
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
    query_executor : QueryExecutor | None, optional
        Executor used by :meth:`query`, by default a new executor on the same
        repositories.
    database : Database | None, optional
        Database wrapper that checks handle affinity, by default ``None`` for
        transactions built directly on a connection.
    """

    def __init__(
        self,
        connection: Connection,
        node_repository: NodeRepository,
        relationship_repository: RelationshipRepository,
        query_executor: QueryExecutor | None = None,
        *,
        database: Database | None = None,
    ) -> None:
        self._connection = connection
        self._node_repository = node_repository
        self._relationship_repository = relationship_repository
        self._database = database
        self._query = (
            QueryExecutor(
                connection,
                node_repository,
                relationship_repository,
                PropertyCodec(),
            )
            if query_executor is None
            else query_executor
        )
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
        return self.begin()

    def begin(self) -> Self:
        """Start the transaction explicitly.

        Returns
        -------
        Self
            The active transaction.

        Raises
        ------
        TransactionError
            If the transaction is already active, was already used, or SQLite
            cannot start a transaction.
        LockTimeoutError
            If the write-lock wait exhausts the busy timeout.
        """
        self._ensure_affinity()
        if self._finished:
            message = "transaction has already been used"
            raise TransactionError(message)
        if self._active:
            message = "transaction is already active"
            raise TransactionError(message)
        if self._connection.in_transaction:
            message = "a graph transaction is already active; use the active transaction"
            raise TransactionError(message)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except OperationalError as error:
            if "locked" in str(error).lower():
                message = "could not start a graph transaction before the lock wait exhausted"
                raise LockTimeoutError(message) from error
            message = "could not start a graph transaction"
            raise TransactionError(message) from error
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
        if exc_type is None:
            self.commit()
        else:
            self.rollback()

    def commit(self) -> None:
        """Commit the transaction and mark it finished.

        Raises
        ------
        TransactionError
            If the transaction is not active or SQLite cannot commit it.
        """
        self._require_active()
        self._finish("COMMIT")

    def rollback(self) -> None:
        """Roll the transaction back and mark it finished.

        Raises
        ------
        TransactionError
            If the transaction is not active or SQLite cannot roll it back.
        """
        self._require_active()
        self._finish("ROLLBACK")

    def _finish(self, statement: str) -> None:
        """Execute a finishing statement and reset the transaction state.

        Parameters
        ----------
        statement : str
            ``COMMIT`` or ``ROLLBACK``.

        Raises
        ------
        TransactionError
            If SQLite cannot finish the transaction.
        """
        try:
            self._connection.execute(statement)
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
        labels: str | Iterable[str],
        end: Node | int,
        *,
        directed: bool = True,
        **properties: Value,
    ) -> Relationship:
        """Create a relationship inside the transaction.

        Parameters
        ----------
        start : Node | int
            First endpoint node or its id.
        labels : str | Iterable[str]
            Labels to attach; a string is one label.
        end : Node | int
            Second endpoint node or its id.
        directed : bool, optional
            Whether the endpoints carry source and destination meaning, by
            default ``True``.
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
            labels,
            self._node_id(end),
            directed=directed,
            properties=properties,
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
        element: Node | Relationship | int,
        *labels: str,
    ) -> Node | Relationship:
        """Add labels to an element inside the transaction.

        Parameters
        ----------
        element : Node | Relationship | int
            Node or relationship snapshot, or a node id.
        *labels : str
            Labels to add.

        Returns
        -------
        Node | Relationship
            Snapshot of the updated element.
        """
        self._require_active()
        target = self._label_target(element)
        if isinstance(target, Node):
            return self._node_repository.add_labels(target.id, labels)
        return self._relationship_repository.add_labels(target.id, labels)

    def remove_labels(
        self,
        element: Node | Relationship | int,
        *labels: str,
    ) -> Node | Relationship:
        """Remove labels from an element inside the transaction.

        Parameters
        ----------
        element : Node | Relationship | int
            Node or relationship snapshot, or a node id.
        *labels : str
            Labels to remove.

        Returns
        -------
        Node | Relationship
            Snapshot of the updated element.
        """
        self._require_active()
        target = self._label_target(element)
        if isinstance(target, Node):
            return self._node_repository.remove_labels(target.id, labels)
        return self._relationship_repository.remove_labels(target.id, labels)

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
        *labels: str,
        directed: bool | None = None,
        **properties: Value,
    ) -> Iterator[Relationship]:
        """Find relationships inside the transaction.

        Parameters
        ----------
        *labels : str
            Labels every match must carry.
        directed : bool | None, optional
            Direction filter, by default any direction.
        **properties : Value
            Exact property values every match must have.

        Returns
        -------
        Iterator[Relationship]
            Matching relationship snapshots.
        """
        self._require_active()
        return self._relationship_repository.find(labels, properties, directed=directed)

    def query(
        self,
        text: str,
        parameters: Mapping[str, QueryValue] | None = None,
    ) -> QueryResult:
        """Execute one statement inside the active transaction.

        The statement uses the transaction's connection, so it observes the
        transaction's uncommitted writes and does not start or finish a
        transaction of its own. A write statement runs inside a savepoint, so a
        failure undoes only that statement.

        Parameters
        ----------
        text : str
            Query source text.
        parameters : Mapping[str, QueryValue] | None, optional
            Query parameter values, by default none.

        Returns
        -------
        QueryResult
            Materialized query result.
        """
        self._require_active()
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        values: Mapping[str, QueryValue] = {} if parameters is None else parameters
        return self._query.execute_active(PlanBuilder.build(analysis), values)

    def _require_active(self) -> None:
        """Reject operations outside an active transaction.

        Raises
        ------
        HandleAffinityError
            If the transaction is used from a thread that does not own its
            graph handle.
        TransactionError
            If the transaction has not been started or has already finished.
        """
        self._ensure_affinity()
        if not self._active:
            message = "transaction is not active"
            raise TransactionError(message)

    def _ensure_affinity(self) -> None:
        """Reject use from a thread that does not own the graph handle.

        Raises
        ------
        HandleAffinityError
            If the owning database belongs to another thread.
        """
        if self._database is not None:
            self._database.ensure_affinity()

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

    def _label_target(self, element: Node | Relationship | int) -> Node | Relationship:
        """Resolve the element targeted by a label write.

        A bare integer addresses a node, preserving the original node-only
        signature. Pass a :class:`Relationship` snapshot to target an edge.

        Parameters
        ----------
        element : Node | Relationship | int
            Element snapshot or node id.

        Returns
        -------
        Node | Relationship
            Snapshot of the targeted element.

        Raises
        ------
        ValidationError
            If the argument is not a node, relationship, or integer id.
        """
        if isinstance(element, (Node, Relationship)):
            return element
        if isinstance(element, int) and not isinstance(element, bool):
            return self._node_repository.get(element)
        message = "element must be a Node, Relationship, or integer node id"
        raise ValidationError(message)
