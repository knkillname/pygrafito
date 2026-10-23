# Proposal

## Why

`pygrafito` can store, read, and traverse a property graph, but every question must be expressed
through Python loops or the three fixed traversal methods. There is no way to express a pattern,
a filter, a projection, and a bounded result in one request. That ceiling blocks the project's
next step: a familiar pattern-matching graph query dialect that is to this library what a
practical SQL dialect is to an embedded SQL engine.

The dialect is the eventual product surface. This change establishes its read-only core rather
than adding a parallel Python query builder that would later compete with the language.

## What Changes

- Add a read-only query language with a documented core profile: `MATCH`, `WHERE`, `RETURN`,
  `DISTINCT`, `ORDER BY`, `SKIP`, and `LIMIT`.
- Support one path pattern with multiple segments, node labels, relationship types, direction,
  property maps, and node, relationship, and path variables.
- Support `$name` parameters, boolean and comparison operators, `IN`, `IS NULL` / `IS NOT NULL`,
  string predicates, arithmetic, a small scalar function set, and aggregates (`count`, `collect`,
  `sum`, `avg`, `min`, `max`).
- Add `Graph.query()`, `Graph.prepare()`, `PreparedQuery`, `QueryResult`, and a query error
  hierarchy with source positions.
- Compile fixed-length patterns to indexed SQL joins and predicates. Do not reuse the whole-graph
  adjacency snapshot used by convenience traversal.
- Add indexed endpoint reads for the query executor without exposing a new public adjacency API.
- Define and document the dialect's semantic contract: numeric equality with booleans distinct,
  query-only nulls, ordering, string comparison, path shape, empty aggregates, result column
  naming, and pagination validation.
- Publish a language reference and executable README examples; add a dialect conformance suite.
- Keep the existing object API, traversal methods, schema, and transaction rules intact.
- Out of scope for this change: variable-length patterns, write clauses, property indexes,
  `OPTIONAL MATCH`, `WITH`, `UNWIND`, subqueries, `MERGE`, a CLI, and import/export.

## Capabilities

### New Capabilities

- `graph-query-language`: the dialect's read-only surface and semantics, including parsing,
  pattern matching, filtering, projection, ordering, pagination, parameters, aggregates, result
  values, error reporting, and execution consistency.

### Modified Capabilities

None. The existing `property-graph` and `graph-traversal` requirements remain valid. The query
language builds on them and does not change their behavior.

## Impact

- Affected code: a new query subpackage inside `engine` (lexer, parser, AST, semantic checks,
  plan, compiler, executor, result rows), additions to the graph facade and package exports, new
  query error types, and test and documentation updates.
- Public API: new `Graph.query`, `Graph.prepare`, `Transaction.query`, `PreparedQuery`,
  `QueryResult`, and query error classes. Existing APIs remain source-compatible; there are no
  breaking changes.
- Dependencies: none added. The lexer, parser, compiler, and executor are standard-library
  Python. SQLite remains the storage and SQL execution backend.
- Data and compatibility: no schema change, no schema version bump, and no migration. Existing
  databases open unchanged.
- Documentation: `README.md` gains a language section whose examples are executed by the test
  suite; `CHANGELOG.md` records the new capability under `[Unreleased]`.
- Deliberate deferrals: variable-length paths, write statements, indexes and planner work,
  aggregation pipelines, and tooling are separate changes.
