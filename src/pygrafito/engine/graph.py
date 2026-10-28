# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Public graph facade."""

import contextlib
import os
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path as FilePath
from types import TracebackType
from typing import Self

from pygrafito.engine.importing import ImportRunner
from pygrafito.engine.interop import InteropSummary, SnapshotExporter, SnapshotRestorer
from pygrafito.engine.query.executor import QueryExecutor
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.plan import PlanBuilder
from pygrafito.engine.query.prepared import PreparedQuery
from pygrafito.engine.query.results import ImportSummary, QueryResult
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
    Constraint,
    Direction,
    ElementKind,
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
from pygrafito.storage.constraints import ConstraintRegistry
from pygrafito.storage.indexes import IndexRegistry
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository
from pygrafito.storage.views import Views


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
        self._constraints = ConstraintRegistry(database.connection, self._codec)
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
        busy_timeout: int | None = None,
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
        busy_timeout : int | None, optional
            Milliseconds a lock wait may take before it fails, by default
            5000 milliseconds.

        Returns
        -------
        Self
            An open graph handle.

        Raises
        ------
        NotFoundError
            If the file does not exist and may not be created.
        ValidationError
            If a read-only in-memory graph is requested or the busy timeout is
            invalid.
        UnsupportedSqliteError
            If the SQLite runtime lacks required features, the file belongs to
            another application, or a read-only open needs to write the schema.
        LockTimeoutError
            If opening waits for a lock longer than the busy timeout.
        """
        return cls(
            Database(
                path,
                create=create,
                readonly=readonly,
                busy_timeout=busy_timeout,
            )
        )

    @property
    def journal_mode(self) -> str:
        """Return the journal mode this handle obtained.

        Returns
        -------
        str
            Lower-case journal mode such as ``wal`` or ``memory``.
        """
        self._database.ensure_open()
        return self._database.journal_mode

    @property
    def view_version(self) -> int:
        """Return the published interop view version.

        Returns
        -------
        int
            Published view version, or zero when the views are absent.
        """
        self._database.ensure_open()
        version = Views(self._database.connection).version()
        return 0 if version is None else version

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
            database=self._database,
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

    def import_rows(
        self,
        statement: str,
        rows: Iterable[Mapping[str, object]],
        *,
        batch_size: int = 1000,
        atomic: bool = False,
    ) -> ImportSummary:
        """Import in-memory row mappings with one write statement.

        Parameters
        ----------
        statement : str
            Write statement that references ``$rows``.
        rows : Iterable[Mapping[str, object]]
            Row mappings to import.
        batch_size : int, optional
            Rows per statement execution, by default 1000.
        atomic : bool, optional
            Whether the whole import commits in one transaction, by default
            ``False``.

        Returns
        -------
        ImportSummary
            Rows, batches, and aggregate mutation counts.

        Raises
        ------
        ReadOnlyError
            If the graph is read-only.
        GraphClosedError
            If the graph handle is closed.
        ValidationError
            If the statement or a row is invalid.
        """
        self._database.ensure_open()
        self._database.ensure_writable()
        return ImportRunner(self).import_rows(
            statement,
            rows,
            batch_size=batch_size,
            atomic=atomic,
        )

    def import_file(
        self,
        path: str | FilePath,
        statement: str,
        *,
        format: str | None = None,
        batch_size: int = 1000,
        atomic: bool = False,
    ) -> ImportSummary:
        """Import a CSV or JSONL file with one write statement.

        Parameters
        ----------
        path : str | FilePath
            File to import.
        statement : str
            Write statement that references ``$rows``.
        format : str | None, optional
            Explicit ``csv`` or ``jsonl`` format, by default inferred from the
            file suffix.
        batch_size : int, optional
            Rows per statement execution, by default 1000.
        atomic : bool, optional
            Whether the whole import commits in one transaction, by default
            ``False``.

        Returns
        -------
        ImportSummary
            Rows, batches, and aggregate mutation counts.

        Raises
        ------
        ReadOnlyError
            If the graph is read-only.
        GraphClosedError
            If the graph handle is closed.
        ValidationError
            If the format, statement, or a row is invalid.
        """
        self._database.ensure_open()
        self._database.ensure_writable()
        return ImportRunner(self).import_file(
            FilePath(path),
            statement,
            format=format,
            batch_size=batch_size,
            atomic=atomic,
        )

    def export_jsonl(
        self,
        path: str | FilePath,
        *,
        overwrite: bool = False,
    ) -> InteropSummary:
        """Write one consistent snapshot of the graph as JSONL.

        The snapshot is written to a sibling temporary file and atomically
        moved into place, so an interrupted export never leaves a partial file
        at the destination.

        Parameters
        ----------
        path : str | FilePath
            Destination path.
        overwrite : bool, optional
            Whether an existing destination may be replaced, by default
            ``False``.

        Returns
        -------
        InteropSummary
            Number of nodes and relationships written.

        Raises
        ------
        GraphClosedError
            If the graph handle is closed.
        TransactionError
            If an explicit transaction is active.
        ValidationError
            If the destination exists and overwrite is false, names the open
            database or one of its sidecars, or cannot be written.
        """
        self._database.ensure_open()
        if not isinstance(overwrite, bool):
            message = "overwrite must be a boolean"
            raise ValidationError(message)
        if self._database.connection.in_transaction:
            message = "a graph transaction is active; finish it before an export"
            raise TransactionError(message)
        destination = FilePath(path)
        self._require_export_destination(destination)
        if destination.exists() and not overwrite:
            message = f"export destination already exists: {destination}"
            raise ValidationError(message)
        with self._read_snapshot():
            return SnapshotExporter(
                self._database.connection,
                self._codec,
            ).export(destination)

    def restore_jsonl(
        self,
        path: str | FilePath,
        *,
        replace: bool = False,
    ) -> InteropSummary:
        """Restore one JSONL snapshot in a single transaction.

        By default the target must be empty. With ``replace`` enabled, the
        current relationships and nodes are deleted and the snapshot is loaded
        in the same transaction, so a failure restores the original graph.

        Parameters
        ----------
        path : str | FilePath
            Snapshot file to read.
        replace : bool, optional
            Whether a non-empty target may be replaced, by default ``False``.

        Returns
        -------
        InteropSummary
            Number of nodes and relationships restored.

        Raises
        ------
        GraphClosedError
            If the graph handle is closed.
        ReadOnlyError
            If the graph handle was opened read-only.
        TransactionError
            If an explicit transaction is active.
        ValidationError
            If the target is non-empty, the snapshot is invalid, or its counts
            do not match.
        """
        self._database.ensure_open()
        self._database.ensure_writable()
        if not isinstance(replace, bool):
            message = "replace must be a boolean"
            raise ValidationError(message)
        if self._database.connection.in_transaction:
            message = "a graph transaction is active; finish it before a restore"
            raise TransactionError(message)
        return SnapshotRestorer(
            self,
            self._database.connection,
            self._codec,
            FilePath(path),
        ).restore(replace=replace)

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

    def create_node_uniqueness_constraint(self, label: str, key: str) -> Constraint:
        """Declare that nodes with one label hold distinct values for one key.

        Parameters
        ----------
        label : str
            Label whose nodes the constraint covers.
        key : str
            Property key whose values must stay distinct.

        Returns
        -------
        Constraint
            The declared constraint.

        Raises
        ------
        ValidationError
            If the label or key is not a non-empty identifier.
        ReadOnlyError
            If the graph handle was opened read-only.
        TransactionError
            If an explicit transaction is active on this graph.
        ConstraintViolationError
            If nodes that already carry the label duplicate a value.
        """
        return self._create_constraint(Constraint(ElementKind.NODE, label, key))

    def create_relationship_uniqueness_constraint(
        self,
        label: str,
        key: str,
    ) -> Constraint:
        """Declare that relationships carrying one label hold distinct values.

        Parameters
        ----------
        label : str
            Relationship label whose relationships the constraint covers.
        key : str
            Property key whose values must stay distinct.

        Returns
        -------
        Constraint
            The declared constraint.

        Raises
        ------
        ValidationError
            If the label or key is not a non-empty identifier.
        ReadOnlyError
            If the graph handle was opened read-only.
        TransactionError
            If an explicit transaction is active on this graph.
        ConstraintViolationError
            If relationships carrying the label already duplicate a value.
        """
        return self._create_constraint(Constraint(ElementKind.RELATIONSHIP, label, key))

    def constraints(self) -> tuple[Constraint, ...]:
        """Return the declared uniqueness constraints.

        Returns
        -------
        tuple[Constraint, ...]
            Declared constraints ordered by element kind, scope, and key.
        """
        self._database.ensure_open()
        return self._constraints.all()

    def drop_constraint(self, constraint: Constraint) -> None:
        """Remove one declared uniqueness constraint.

        Parameters
        ----------
        constraint : Constraint
            Constraint returned by ``constraints`` or constructed by the caller.

        Raises
        ------
        NotFoundError
            If the constraint is not declared.
        ReadOnlyError
            If the graph handle was opened read-only.
        TransactionError
            If an explicit transaction is active on this graph.
        """
        self._require_constraint_access()
        self._constraints.drop(constraint)
        self._refresh_planner_statistics()

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

    def _require_export_destination(self, destination: FilePath) -> None:
        """Reject a destination that would replace the live database.

        Parameters
        ----------
        destination : FilePath
            Requested export path.

        Raises
        ------
        ValidationError
            If the destination names the open database or a journal sidecar.
        """
        location = self._database.location
        if location == Database.MEMORY_PATH:
            return
        database = FilePath(location).resolve()
        target = destination.resolve()
        reserved = {database}
        reserved.update(
            FilePath(f"{database}{suffix}").resolve() for suffix in ("-wal", "-shm", "-journal")
        )
        if target in reserved:
            message = f"export destination is the open database: {destination}"
            raise ValidationError(message)

    @contextlib.contextmanager
    def _read_snapshot(self) -> Iterator[None]:
        """Run a public read against one committed state.

        A deferred transaction is started unless the caller already opened an
        explicit transaction, in which case its writes stay visible. The
        transaction closes before this context exits, so no transaction
        outlives a returned iterator.

        Yields
        ------
        None
            Control while the snapshot is active.

        Raises
        ------
        TransactionError
            If SQLite cannot start or finish the read transaction.
        """
        self._database.ensure_open()
        connection = self._database.connection
        if connection.in_transaction:
            yield
            return
        try:
            connection.execute("BEGIN")
        except sqlite3.Error as error:
            message = "could not start a graph read"
            raise TransactionError(message) from error
        try:
            yield
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise
        try:
            connection.execute("COMMIT")
        except sqlite3.Error as error:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            message = "could not finish a graph read"
            raise TransactionError(message) from error

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

    def _create_constraint(self, constraint: Constraint) -> Constraint:
        """Declare one constraint after the access checks.

        Parameters
        ----------
        constraint : Constraint
            Constraint to declare.

        Returns
        -------
        Constraint
            The declared constraint.
        """
        self._require_constraint_access()
        self._constraints.create(constraint)
        self._refresh_planner_statistics()
        return constraint

    def _require_constraint_access(self) -> None:
        """Reject constraint changes while a transaction is active.

        Raises
        ------
        ReadOnlyError
            If the graph handle was opened read-only.
        TransactionError
            If an explicit transaction is active on this graph.
        """
        self._database.ensure_writable()
        if self._database.connection.in_transaction:
            message = "a graph transaction is active; change constraints outside it"
            raise TransactionError(message)

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
        labels: str | Iterable[str],
        end: Node | int,
        *,
        directed: bool = True,
        **properties: Value,
    ) -> Relationship:
        """Create a relationship in its own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.add_relationship(
                start,
                labels,
                end,
                directed=directed,
                **properties,
            )

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
        element: Node | Relationship | int,
        *labels: str,
    ) -> Node | Relationship:
        """Add labels in their own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.add_labels(element, *labels)

    def remove_labels(
        self,
        element: Node | Relationship | int,
        *labels: str,
    ) -> Node | Relationship:
        """Remove labels in their own transaction.

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
        self._database.ensure_open()
        with self.transaction() as active:
            return active.remove_labels(element, *labels)

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
        with self._read_snapshot():
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
        with self._read_snapshot():
            return self._nodes.find(labels, properties)

    def find_relationships(
        self,
        *labels: str,
        directed: bool | None = None,
        **properties: Value,
    ) -> Iterator[Relationship]:
        """Find relationships by labels and exact property values.

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
            Matching relationship snapshots ordered by id.
        """
        self._database.ensure_open()
        with self._read_snapshot():
            return self._relationships.find(labels, properties, directed=directed)

    def traverse(
        self,
        start: Node | int,
        *,
        max_depth: int,
        direction: Direction = Direction.OUTGOING,
        labels: Iterable[str] | None = None,
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
        labels : Iterable[str] | None, optional
            Allowed relationship labels, by default all labels.

        Returns
        -------
        Iterator[TraversalStep]
            Each reached node once with its shortest depth.
        """
        self._database.ensure_open()
        with self._read_snapshot():
            snapshot = TraversalCapture(self._nodes, self._relationships).region(
                start,
                max_depth,
                direction,
                labels,
            )
        evaluator = ReachabilityEvaluator(
            snapshot,
            start,
            max_depth,
            direction,
            labels,
        )
        return iter(evaluator)

    def shortest_path(
        self,
        start: Node | int,
        end: Node | int,
        *,
        direction: Direction = Direction.OUTGOING,
        labels: Iterable[str] | None = None,
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
        labels : Iterable[str] | None, optional
            Allowed relationship labels, by default all labels.
        max_depth : int | None, optional
            Maximum path length, by default unbounded.

        Returns
        -------
        Path | None
            A shortest path, or ``None`` when none exists.
        """
        self._database.ensure_open()
        with self._read_snapshot():
            source = DatabaseNeighborhood(self._nodes, self._relationships)
            evaluator = ShortestPathEvaluator(
                source,
                start,
                end,
                direction,
                labels,
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
        labels: Iterable[str] | None = None,
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
        labels : Iterable[str] | None, optional
            Allowed relationship labels, by default all labels.
        limit : int | None, optional
            Maximum number of paths to produce, by default unlimited.

        Returns
        -------
        Iterator[Path]
            Trails within the depth range.
        """
        self._database.ensure_open()
        end_id = TraversalSupport.node_id(end)
        with self._read_snapshot():
            snapshot = TraversalCapture(self._nodes, self._relationships).region(
                start,
                max_depth,
                direction,
                labels,
                include=(end_id,),
            )
        evaluator = TrailEnumerator(
            snapshot,
            start,
            end,
            min_depth,
            max_depth,
            direction,
            labels,
            limit,
        )
        return iter(evaluator)
