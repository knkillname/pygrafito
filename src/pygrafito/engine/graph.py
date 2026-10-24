# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Public graph facade."""

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
    AdjacencySnapshot,
    ReachabilityEvaluator,
    ShortestPathEvaluator,
    TrailEnumerator,
)
from pygrafito.model import (
    Direction,
    Node,
    Path,
    Relationship,
    TransactionError,
    TraversalStep,
    Value,
)
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
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
    ) -> Self:
        """Open or create a graph database.

        Parameters
        ----------
        path : str | FilePath
            Filesystem path of the database, or ``":memory:"``.
        create : bool, optional
            Whether a missing file may be created, by default ``True``.

        Returns
        -------
        Self
            An open graph handle.

        Raises
        ------
        NotFoundError
            If ``create`` is false and the file does not exist.
        UnsupportedSqliteError
            If the SQLite runtime lacks required features.
        """
        return cls(Database(path, create=create))

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
            Transaction that is not active until entered.
        """
        self._database.ensure_open()
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
        snapshot = self._snapshot()
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
        snapshot = self._snapshot()
        evaluator = ShortestPathEvaluator(
            snapshot,
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
        snapshot = self._snapshot()
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

    def _snapshot(self) -> AdjacencySnapshot:
        """Materialize the graph state for one traversal.

        Returns
        -------
        AdjacencySnapshot
            Snapshot fixed at call time.
        """
        return AdjacencySnapshot.capture(
            self._nodes,
            self._relationships,
        )
