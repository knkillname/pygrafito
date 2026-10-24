# API reference

This reference documents the public Python surface exported by `pygrafito`. Names not listed here
are internal, even if they are importable from a submodule.

The documentation is generated from the package docstrings, so signatures, defaults, return
values, and raised exceptions match the installed version. The version shown in the sidebar is the
version used to build this site.

## How to read this reference

- Use [`Graph.open`](graph.md#lifecycle) to create a graph. Do not construct `Graph`,
  `Transaction`, or `PreparedQuery` directly; their constructors take internal collaborators.
- Model objects (`Node`, `Relationship`, `Path`, and the summary types) are immutable snapshots.
  They are safe to keep after a read, but they do not update when the graph changes.
- Errors inherit from `PygrafitoError`. Catch the narrowest type your caller can handle; see
  [Errors](errors.md).
- Property values are `bool`, signed 64-bit `int`, finite `float`, `str`, or a homogeneous list of
  those scalars. Query values also include `None`, mappings, and graph objects. Neither `Value` nor
  `QueryValue` is exported; they describe accepted shapes in method signatures.

## Core

| Name | Page | Purpose |
| --- | --- | --- |
| `Graph` | [Graph and transactions](graph.md) | Open a graph and run reads, writes, queries, traversal, indexes, constraints, import/export, and maintenance. |
| `Transaction` | [Graph and transactions](graph.md#transactions) | Group writes in one explicit `BEGIN IMMEDIATE` transaction. |

## Data model

| Name | Page | Purpose |
| --- | --- | --- |
| `Node` | [Data model](model.md#node) | Immutable node snapshot with an id, labels, and properties. |
| `Relationship` | [Data model](model.md#relationship) | Immutable directed relationship with an id, type, endpoints, and properties. |
| `Path` | [Data model](model.md#path) | Immutable sequence of nodes and relationships. |
| `TraversalStep` | [Data model](model.md#traversalstep) | A reached node together with its shortest depth. |
| `Direction` | [Data model](model.md#direction) | Outgoing, incoming, or both. |
| `ElementKind` | [Data model](model.md#elementkind) | Node or relationship. |
| `IndexKind` | [Data model](model.md#indexkind) | Alias of `ElementKind`. |
| `Index` | [Administration](admin.md#index) | Declared property index. |
| `Constraint` | [Administration](admin.md#constraint) | Declared uniqueness constraint. |

## Queries and results

| Name | Page | Purpose |
| --- | --- | --- |
| `PreparedQuery` | [Queries and results](query.md#preparedquery) | Parsed, planned statement that can run repeatedly. |
| `QueryResult` | [Queries and results](query.md#queryresult) | Materialized columns, rows, and mutation summary. |
| `Row` | [Queries and results](query.md#row) | Immutable result row with lookup by column name. |
| `MutationSummary` | [Queries and results](query.md#mutationsummary) | Counts of changes applied by one statement. |
| `ImportSummary` | [Queries and results](query.md#importsummary) | Rows, batches, and aggregate mutations from one import. |
| `InteropSummary` | [Administration](admin.md#interopsummary) | Node and relationship counts from export or restore. |

## Errors

| Name | Page | Purpose |
| --- | --- | --- |
| `PygrafitoError` | [Errors](errors.md#pygrafitoerror) | Base class for every library error. |
| `GraphClosedError` | [Errors](errors.md#graphclosederror) | The handle was already closed. |
| `ValidationError` | [Errors](errors.md#validationerror) | A value, identifier, or request is invalid. |
| `NotFoundError` | [Errors](errors.md#notfounderror) | A requested element, index, or constraint does not exist. |
| `ConnectedNodeError` | [Errors](errors.md#connectednodeerror) | A node with relationships cannot be deleted without `detach=True`. |
| `TransactionError` | [Errors](errors.md#transactionerror) | A transaction cannot start, commit, or be reused. |
| `ReadOnlyError` | [Errors](errors.md#readonlyerror) | A write was requested on a read-only handle. |
| `UnsupportedSqliteError` | [Errors](errors.md#unsupportedsqliteerror) | SQLite or the file cannot provide a required feature. |
| `HandleAffinityError` | [Errors](errors.md#handleaffinityerror) | A handle was used from a thread that does not own it. |
| `LockTimeoutError` | [Errors](errors.md#locktimeouterror) | A write-lock wait exhausted the busy timeout. |
| `ConstraintViolationError` | [Errors](errors.md#constraintviolationerror) | A write would duplicate a constrained value. |
| `QueryError` | [Errors](errors.md#queryerror) | Base class for query-language failures. |
| `QuerySyntaxError` | [Errors](errors.md#querysyntaxerror) | The statement cannot be lexed or parsed. |
| `QuerySemanticError` | [Errors](errors.md#querysemanticerror) | The statement violates a static dialect rule. |
| `QueryExecutionError` | [Errors](errors.md#queryexecutionerror) | The statement fails while evaluating. |

## Go deeper

- [Five-minute quickstart](../getting-started/quickstart.md) for the first graph.
- [Query your graph](../guides/querying.md) for the statement workflow.
- [Embedding contract](../reference/embedding-contract.md) for lifecycle and concurrency guarantees.
