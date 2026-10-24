# Proposal

## Why

`pygrafito` has one query surface and it cannot write. Every mutation must be expressed through the
imperative object API, so the dialect can ask questions about a graph but never build or maintain
one. That is the largest remaining gap against the goal of a lightweight embedded graph database:
the language is the product surface, and today it is a read-only view.

This change closes the asymmetry. A statement may match, mutate, and return in one call, with the
same atomicity and validation rules the object API already guarantees.

## What Changes

- Support write clauses: `CREATE` for nodes and relationships, `SET` and `REMOVE` for properties
  and labels, and `DELETE` / `DETACH DELETE` for elements.
- Change the statement shape from "one `MATCH` + required `RETURN`" to an ordered clause sequence,
  where `MATCH` and `RETURN` are each optional but the sequence is never empty.
- Make `Graph.query`, `Transaction.query`, and `PreparedQuery.execute` execute read and write
  statements. Remove the read-only rejection; a statement is classified as a write when it
  contains any write clause.
- Give a standalone write statement its own `BEGIN IMMEDIATE` transaction, so each call is atomic.
  `Transaction.query` runs a write statement inside the active transaction and opens nothing.
- Define mutation cardinality explicitly: write clauses operate on match rows, and an entity
  referenced by several rows is mutated or deleted once per statement.
- Make `RETURN` optional after a write. When it is omitted, the result has no columns and carries a
  mutation summary with created, deleted, and property/label update counts.
- Map storage failures from writes onto the query error hierarchy, so callers see `QueryError`
  subclasses rather than `NotFoundError` or `ConnectedNodeError`.
- Keep the existing object API, traversal methods, schema, and transaction rules intact. No schema
  change and no migration.

Deliberate deferrals: `MERGE`, `ON CREATE SET` / `ON MATCH SET`, variable-length patterns,
`OPTIONAL MATCH`, `WITH`, `UNWIND`, subqueries, multiple patterns and multiple `MATCH` clauses,
property indexes, streaming results, and import/export.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-query-language`: the statement contract becomes read-write. The read-only execution
  requirement is replaced by statement execution; the core dialect profile gains a clause sequence
  with optional `MATCH` and `RETURN`; additions cover `CREATE`, `SET`, `REMOVE`, `DELETE`,
  mutation cardinality, write results, write errors, and write atomicity; prepared queries,
  transaction integration, the result model, and the consistent-snapshot requirement are adjusted
  for statements that mutate.

## Impact

- Affected code: the query front-end and executor (`tokens`, `ast`, `parser`, `semantic`, `plan`,
  `compiler`, `executor`, `prepared`), the `Graph` and `Transaction` entry points, and the package
  exports if the result model gains a summary type.
- Public API: `Graph.query` and `Transaction.query` accept write statements; `PreparedQuery`
  supports prepared writes; `QueryResult` exposes a mutation summary. No existing call signature
  changes, and no API is removed, so the change is source-compatible.
- Behavior: statements that previously raised a read-only query error now execute. This is an
  intentional contract change, documented in `docs/query-language.md` and the README.
- Dependencies: none. Everything remains standard-library Python over SQLite.
- Data and compatibility: no schema change, no schema version bump, and no migration. Existing
  databases open unchanged, and the new clauses reuse the existing storage rules for strict
  property values, deletion protection, and transactions.
- Documentation: `README.md` gains write examples that the snippet test executes,
  `docs/query-language.md` records the clause grammar and mutation semantics, and `CHANGELOG.md`
  gains an entry under `[Unreleased]`.
- Unchanged capabilities: `property-graph` and `graph-traversal` requirements remain valid. The new
  clauses call the same storage operations and introduce no new storage rule.
