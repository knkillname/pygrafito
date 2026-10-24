# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Public graph facade."""

import os
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path as FilePath
from types import TracebackType
from typing import Self

from pygrafito.engine.query.executor import QueryExecutor
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.plan import PlanBuilder
from pygrafito.engine.query.prepared import PreparedQuery
from pygrafito.engine.query.results import QueryResult
from pygrafito.engine.query.semantic import SemanticAnalyzer
from pygrafito.engine.query.values import QueryValue
from pygrafito.engine.transaction import Transaction
from pygrafito.engine.traversal import (
    DatabaseNeighborhood,
    ReachabilityEvaluator,
    ShortestPathEvaluator,
    TrailEnumerator,
    TraversalCapture,
    TraversalSupport,
)
from pygrafito.model import (
    Direction,
    Index,
    IndexKind,
    Node,
    Path,
    Relationship,
    TransactionError,
    TraversalStep,
    ValidationError,
    Value,
)
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.indexes import IndexRegistry
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository


class Graph:
    """An embedded property graph backed by one SQLite connection.

    Parameters
    ----------
    database : Database
        Open database wrapper owned by this graph.
    """

    def __init__(self, database: Database) -> None:
        self._database = database
        self._codec = PropertyCodec()
        self._nodes = NodeRepository(
            database.connection,
            self._codec,
        )
        self._relationships = RelationshipRepository(
            database.connection,
            self._codec,
        )
        self._indexes = IndexRegistry(database.connection, self._codec)
        self._query = QueryExecutor(
            database.connection,
            self._nodes,
            self._relationships,
            self._codec,
            database,
        )

    @classmethod
    def open(
        cls,
        path: str | FilePath,
        *,
        create: bool = True,
        readonly: bool = False,
    ) -> Self:
        """Open or create a graph database.

        Parameters
        ----------
        path : str | FilePath
            Filesystem path of the database, or ``":memory:"``.
        create : bool, optional
            Whether a missing file may be created, by default ``True``.
        readonly : bool, optional
            Whether to open an existing file without write access, by default
            ``False``. A read-only open never creates a file and is not
            available for an in-memory database.

        Returns
        -------
        Self
            An open graph handle.

        Raises
        ------
        NotFoundError
            If the file does not exist and may not be created.
        ValidationError
            If a read-only in-memory graph is requested.
        UnsupportedSqliteError
            If the SQLite runtime lacks required features, or a read-only open
            needs to write the schema.
        """
        return cls(Database(path, create=create, readonly=readonly))

    def close(self) -> None:
        """Close the graph handle. Closing twice is a no-op."""
        self._database.close()

    def __enter__(self) -> Self:
        """Return the open graph for a context block.

        Returns
        -------
        Self
            This graph.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Close the graph when leaving a context block.

        Parameters
        ----------
        exc_type : type[BaseException] | None
            Exception type raised inside the block, if any.
        _exc_value : BaseException | None
            Exception instance raised inside the block, if any.
        _traceback : TracebackType | None
            Traceback raised inside the block, if any.
        """
        self.close()

    def transaction(self) -> Transaction:
        """Create one explicit write transaction.

        Returns
        -------
        Transaction
            Transaction that is not active until entered or begun.

        Raises
        ------
        ReadOnlyError
            If the graph handle was opened read-only.
        """
        self._database.ensure_writable()
        return Transaction(
            self._database.connection,
            self._nodes,
            self._relationships,
            query_executor=self._query,
        )

    def query(
        self,
        text: str,
        parameters: Mapping[str, QueryValue] | None = None,
    ) -> QueryResult:
        """Parse and execute one statement.

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
        self._database.ensure_open()
        if self._database.connection.in_transaction:
            message = "a graph transaction is active; use Transaction.query"
            raise TransactionError(message)
        return self.prepare(text).execute(parameters)

    def prepare(self, text: str) -> PreparedQuery:
        """Parse and validate a query for repeated execution.

        Parameters
        ----------
        text : str
            Query source text.

        Returns
        -------
        PreparedQuery
            Prepared statement whose columns are available before execution.
        """
        self._database.ensure_open()
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        return PreparedQuery(
            self._query,
            text,
            PlanBuilder.build(analysis),
        )

    def explain(
        self,
        text: str,
        parameters: Mapping[str, QueryValue] | None = None,
    ) -> tuple[str, ...]:
        """Return the planned access path for one statement without running it.

        Parameters
        ----------
        text : str
            Query source text.
        parameters : Mapping[str, QueryValue] | None, optional
            Query parameter values, by default none.

        Returns
        -------
        tuple[str, ...]
            One detail line per plan row, in plan order. A statement without a
            ``MATCH`` clause returns an empty tuple.

        Raises
        ------
        QuerySyntaxError
            If the statement does not parse.
        QuerySemanticError
            If the statement is invalid or references a missing parameter.
        """
        self._database.ensure_open()
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        plan = PlanBuilder.build(analysis)
        return self._query.explain(plan, parameters or {})

    def create_node_index(self, key: str) -> Index:
        """Declare a property index over nodes.

        Parameters
        ----------
        key : str
            Property key whose values are indexed.

        Returns
        -------
        Index
            The declared index.

        Raises
        ------
        ValidationError
            If the key is not a non-empty string.
        TransactionError
            If an explicit transaction is active on this graph.
        """
        return self._create_index(Index(IndexKind.NODE, key))

    def create_relationship_index(self, key: str) -> Index:
        """Declare a property index over relationships.

        Parameters
        ----------
        key : str
            Property key whose values are indexed.

        Returns
        -------
        Index
            The declared index.

        Raises
        ------
        ValidationError
            If the key is not a non-empty string.
        TransactionError
            If an explicit transaction is active on this graph.
        """
        return self._create_index(Index(IndexKind.RELATIONSHIP, key))

    def drop_index(self, index: Index) -> None:
        """Remove one declared index.

        Parameters
        ----------
        index : Index
            Index returned by ``indexes`` or constructed by the caller.

        Raises
        ------
        NotFoundError
            If the index is not declared.
        TransactionError
            If an explicit transaction is active on this graph.
        """
        self._require_index_access()
        self._indexes.drop(index)
        self._refresh_planner_statistics()

    def indexes(self) -> tuple[Index, ...]:
        """Return the declared indexes.

        Returns
        -------
        tuple[Index, ...]
            Declared indexes ordered by element kind and key.
        """
        self._database.ensure_open()
        return self._indexes.all()

    def backup_to(self, path: str | FilePath) -> FilePath:
        """Write a consistent copy of the open database.

        The copy is written to a temporary sibling of the destination and
        atomically moved into place, so an interrupted copy never leaves a
        partial database at the destination.

        Parameters
        ----------
        path : str | FilePath
            Destination path that must not already exist.

        Returns
        -------
        FilePath
            The written destination path.

        Raises
        ------
        ValidationError
            If the destination already exists or cannot be written.
        TransactionError
            If an explicit transaction is active on this graph.
        """
        self._database.ensure_open()
        if self._database.connection.in_transaction:
            message = "a graph transaction is active; finish it before a backup"
            raise TransactionError(message)
        destination = FilePath(path)
        if destination.exists():
            message = f"backup destination already exists: {destination}"
            raise ValidationError(message)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        try:
            target = sqlite3.connect(str(temporary), isolation_level=None)
            try:
                self._database.connection.backup(target)
            finally:
                target.close()
            temporary.replace(destination)
        except (OSError, sqlite3.Error) as error:
            temporary.unlink(missing_ok=True)
            message = f"could not write backup: {destination}"
            raise ValidationError(message) from error
        return destination

    def check_integrity(self) -> tuple[str, ...]:
        """Report structural integrity problems of the open database.

        Returns
        -------
        tuple[str, ...]
            One line per reported problem, or an empty tuple when the store is
            healthy.
        """
        self._database.ensure_open()
        problems: list[str] = []
        for row in self._database.connection.execute("PRAGMA integrity_check"):
            value = str(row[0])
            if value != "ok":
                problems.append(f"integrity: {value}")
        for row in self._database.connection.execute("PRAGMA foreign_key_check"):
            problems.append(
                f"foreign key: table={row[0]} rowid={row[1]} parent={row[2]} fkid={row[3]}"
            )
        return tuple(problems)

    def _create_index(self, index: Index) -> Index:
        """Create one declared index after the access checks.

        Parameters
        ----------
        index : Index
            Index to create.

        Returns
        -------
        Index
            The declared index.
        """
        self._require_index_access()
        self._indexes.create(index)
        self._refresh_planner_statistics()
        return index

    def _refresh_planner_statistics(self) -> None:
        """Refresh planning statistics, ignoring failures.

        Statistics affect plan choice only, so a refresh failure must not fail
        the index operation that triggered it.
        """
        try:
            self._database.connection.execute("ANALYZE")
        except sqlite3.OperationalError:
            return

    def _require_index_access(self) -> None:
        """Reject index changes while a transaction is active.

        Raises
        ------
        ReadOnlyError
            If the graph handle was opened read-only.
        TransactionError
            If an explicit transaction is active on this graph.
        """
        self._database.ensure_writable()
        if self._database.connection.in_transaction:
            message = "a graph transaction is active; declare indexes outside it"
            raise TransactionError(message)

    def add_node(
        self,
        *labels: str,
        **properties: Value,
    ) -> Node:
        """Create a node in its own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.add_node(*labels, **properties)

    def add_relationship(
        self,
        start: Node | int,
        rel_type: str,
        end: Node | int,
        **properties: Value,
    ) -> Relationship:
        """Create a relationship in its own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.add_relationship(start, rel_type, end, **properties)

    def set_properties(
        self,
        element: Node | Relationship,
        **properties: Value | None,
    ) -> Node | Relationship:
        """Set or remove properties in their own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.set_properties(element, **properties)

    def remove_properties(
        self,
        element: Node | Relationship,
        *keys: str,
    ) -> Node | Relationship:
        """Remove properties in their own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.remove_properties(element, *keys)

    def add_labels(
        self,
        node: Node | int,
        *labels: str,
    ) -> Node:
        """Add labels in their own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.add_labels(node, *labels)

    def remove_labels(
        self,
        node: Node | int,
        *labels: str,
    ) -> Node:
        """Remove labels in their own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.remove_labels(node, *labels)

    def delete(
        self,
        element: Node | Relationship,
        *,
        detach: bool = False,
    ) -> None:
        """Delete an element in its own transaction.

        Parameters
        ----------
        element : Node | Relationship
            Element to delete.
        detach : bool, optional
            Whether to remove incident relationships before deleting a node,
            by default ``False``.
        """
        self._database.ensure_open()
        with self.transaction() as active:
            active.delete(element, detach=detach)

    def node(self, node_id: int) -> Node:
        """Read a node.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        Node
            Snapshot of the node.
        """
        self._database.ensure_open()
        return self._nodes.get(node_id)

    def relationship(self, relationship_id: int) -> Relationship:
        """Read a relationship.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.

        Returns
        -------
        Relationship
            Snapshot of the relationship.
        """
        self._database.ensure_open()
        return self._relationships.get(relationship_id)

    def find_nodes(
        self,
        *labels: str,
        **properties: Value,
    ) -> Iterator[Node]:
        """Find nodes by labels and exact property values.

        Parameters
        ----------
        *labels : str
            Labels every match must carry.
        **properties : Value
            Exact property values every match must have.

        Returns
        -------
        Iterator[Node]
            Matching node snapshots ordered by id.
        """
        self._database.ensure_open()
        return self._nodes.find(labels, properties)

    def find_relationships(
        self,
        rel_type: str | None = None,
        **properties: Value,
    ) -> Iterator[Relationship]:
        """Find relationships by type and exact property values.

        Parameters
        ----------
        rel_type : str | None, optional
            Relationship type every match must have, by default any type.
        **properties : Value
            Exact property values every match must have.

        Returns
        -------
        Iterator[Relationship]
            Matching relationship snapshots ordered by id.
        """
        self._database.ensure_open()
        return self._relationships.find(rel_type, properties)

    def traverse(
        self,
        start: Node | int,
        *,
        max_depth: int,
        direction: Direction = Direction.OUTGOING,
        types: Iterable[str] | None = None,
    ) -> Iterator[TraversalStep]:
        """Yield distinct reachable nodes at their shortest depth.

        The start node is never yielded. The traversal runs against a snapshot
        taken when this method is called, so later writes do not change the
        results.

        Parameters
        ----------
        start : Node | int
            Start node or its id.
        max_depth : int
            Maximum number of relationships to follow.
        direction : Direction, optional
            Direction to follow, by default outgoing.
        types : Iterable[str] | None, optional
            Allowed relationship types, by default all types.

        Returns
        -------
        Iterator[TraversalStep]
            Each reached node once with its shortest depth.
        """
        self._database.ensure_open()
        snapshot = TraversalCapture(self._nodes, self._relationships).region(
            start,
            max_depth,
            direction,
            types,
        )
        evaluator = ReachabilityEvaluator(
            snapshot,
            start,
            max_depth,
            direction,
            types,
        )
        return iter(evaluator)

    def shortest_path(
        self,
        start: Node | int,
        end: Node | int,
        *,
        direction: Direction = Direction.OUTGOING,
        types: Iterable[str] | None = None,
        max_depth: int | None = None,
    ) -> Path | None:
        """Find one path with the fewest relationships.

        A node has a zero-length path to itself.

        Parameters
        ----------
        start : Node | int
            Start node or its id.
        end : Node | int
            End node or its id.
        direction : Direction, optional
            Direction in which paths advance, by default outgoing.
        types : Iterable[str] | None, optional
            Allowed relationship types, by default all types.
        max_depth : int | None, optional
            Maximum path length, by default unbounded.

        Returns
        -------
        Path | None
            A shortest path, or ``None`` when none exists.
        """
        self._database.ensure_open()
        source = DatabaseNeighborhood(self._nodes, self._relationships)
        evaluator = ShortestPathEvaluator(
            source,
            start,
            end,
            direction,
            types,
            max_depth,
        )
        return evaluator.evaluate()

    def paths(
        self,
        start: Node | int,
        end: Node | int,
        *,
        max_depth: int,
        min_depth: int = 1,
        direction: Direction = Direction.OUTGOING,
        types: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> Iterator[Path]:
        """Enumerate relationship-unique trails between two nodes.

        Nodes may repeat, but a relationship may not be used twice in one
        path. Enumeration is lazy and bounded by ``max_depth``.

        Parameters
        ----------
        start : Node | int
            Start node or its id.
        end : Node | int
            End node or its id.
        max_depth : int
            Inclusive maximum number of relationships.
        min_depth : int, optional
            Inclusive minimum number of relationships, by default 1.
        direction : Direction, optional
            Direction in which paths advance, by default outgoing.
        types : Iterable[str] | None, optional
            Allowed relationship types, by default all types.
        limit : int | None, optional
            Maximum number of paths to produce, by default unlimited.

        Returns
        -------
        Iterator[Path]
            Trails within the depth range.
        """
        self._database.ensure_open()
        end_id = TraversalSupport.node_id(end)
        snapshot = TraversalCapture(self._nodes, self._relationships).region(
            start,
            max_depth,
            direction,
            types,
            include=(end_id,),
        )
        evaluator = TrailEnumerator(
            snapshot,
            start,
            end,
            min_depth,
            max_depth,
            direction,
            types,
            limit,
        )
        return iter(evaluator)
