# Proposal

## Why

`pygrafito` can store a graph, but it cannot easily receive one. Loading a dataset means a
Python loop of `add_node` and `add_relationship` calls, and every "create if missing" is a
read-modify-write sequence in application code. The query dialect rejects `UNWIND` and
`MERGE`, the two clauses bulk-loading queries are written in, so a query ported from a
server-based graph database usually fails at the load step. This change closes the on-ramp:
rows in, upserts without duplicate work. It is the first of three changes; it precedes
`add-embedding-contract` and `add-data-interop`.

## What Changes

- Add `UNWIND <list expression> AS <variable>` as a row-expanding clause. It expands a list
  parameter, list literal, or other list-valued expression into one row per element and may
  feed `CREATE`, `MERGE`, or `RETURN`. An empty list or a null value produces no rows; a
  non-list value raises a query error.
- Add `MERGE <path pattern>` with match-or-create semantics over the whole pattern, including
  relationship patterns.
- Add `ON CREATE SET` and `ON MATCH SET` clauses attached to a `MERGE`, evaluated per merged
  row. Ordinary `SET` and `REMOVE` remain available after the `MERGE` stage.
- Fix `MERGE` cardinality: zero matches creates the pattern and binds the new elements; one
  match binds the existing elements; several matches produce several result rows and create
  nothing. `MERGE` never raises a duplicate-match error on its own.
- Reject a null property value in a `MERGE` pattern with a query error. Properties are
  removed with `SET`/`REMOVE`, never merged with null.
- Add `Graph.import_rows(statement, rows, *, batch_size=...)` and
  `Graph.import_file(path, statement, *, format=None, batch_size=...)`. The rows bind as the
  `$rows` parameter and the statement performs the mapping; there is no separate mapping DSL.
  JSONL preserves value types. CSV cells are strings and the statement converts them with
  `toInteger`, `toFloat`, or `toString`.
- Add `.import PATH --statement TEXT [--format csv|jsonl] [--batch N] [--atomic]` to the
  command-line shell. Files are read incrementally, never loaded whole.
- Commit each batch independently by default. `--atomic` wraps the whole file in one
  transaction. A failure reports the file, the row number, and the query error; earlier
  batches stay committed unless `--atomic` is set.
- Out of scope: a declarative column-mapping DSL, CSV type inference, `LOAD CSV`, procedures,
  and `MERGE` over more than one path pattern.

## Capabilities

### New Capabilities

- `graph-import`: row-oriented import from CSV and JSONL, statement-driven mapping, batching,
  transaction boundaries, and row-level error reporting.

### Modified Capabilities

- `graph-query-language`: adds `UNWIND`, `MERGE`, `ON CREATE SET`, and `ON MATCH SET`, plus the
  matching cardinality, null, list-expression, and write-summary rules.
- `graph-shell`: adds the `.import` dot-command, its options, output, and failure reporting.

## Impact

- Affected code: lexer, parser, AST, semantic analyzer, compiler, executor, mutation, and plan
  modules for the new clauses; a new import module for file reading and batching; CLI command
  and session modules; documentation, README examples, and `CHANGELOG.md`.
- Public API: `Graph.import_rows`, `Graph.import_file`, an import summary type, and the
  `.import` shell command. No existing signature changes.
- Storage: none. No schema change, no migration, and no change to `PRAGMA user_version`.
- Dependencies: none. CSV and JSONL use the standard-library `csv` and `json` modules.
- Tests: TRON-themed fixtures for import; `MERGE` cardinality, conditional updates, batching,
  atomicity, and row-level errors; README examples.
