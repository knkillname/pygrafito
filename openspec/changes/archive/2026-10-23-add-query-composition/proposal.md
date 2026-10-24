# Proposal

## Why

The dialect can express exactly one fixed-length pattern and one projection. Real
application queries compose: a two-hop lookup, a left join that keeps unmatched rows, an
aggregation whose result feeds a filter, a join between independent patterns. Today every
one of those is rejected before execution, so callers decompose the query into several
calls and Python loops. That defeats the point of shipping a query language and leaves the
embedded database less useful than the object API it is meant to complement.

This change makes the dialect composable. It is the step between "the engine can answer a
pattern" and "a caller can write the query the application actually needs" without
introducing an optimizer, a planner rewrite, or a storage change.

## What Changes

- **Variable-length relationships.** `-[r:ALLIES_WITH*1..3]->` follows between one and
  three relationships, with type alternatives, direction, and property maps applied to
  every hop. `*n` means exactly `n`, `*n..m` a bounded range, and `*0..m` includes the
  zero-hop match. Trails are relationship-unique and nodes may repeat, matching the
  existing `paths()` semantics. An upper bound is required; bare `*` and `*n..` are
  rejected with a semantic error rather than allowed to explore without limit. A
  variable-length relationship variable binds the list of traversed relationships, and a
  path variable includes them in traversal order.
- **Multiple patterns in one `MATCH`.** `MATCH (a:Program), (b:Program)` evaluates the
  patterns as one stage. Variables shared across patterns join on the same element;
  patterns with no shared variables produce a cartesian product.
- **Multiple `MATCH` clauses.** Each clause is a stage that joins against the rows the
  previous stage produced. A later `MATCH` may constrain variables bound earlier and may
  introduce new ones.
- **`OPTIONAL MATCH`.** A left join. Rows with no match survive with the variables the
  optional stage introduces bound to null; variables bound before the stage keep their
  values. The stage's `WHERE` is part of the optional match, and a null never satisfies a
  downstream `WHERE`.
- **`WITH`.** A stage boundary carrying projection, `DISTINCT`, `WHERE`, `ORDER BY`,
  `SKIP`, `LIMIT`, and aggregation. Only the names projected by a `WITH` remain in scope
  for later stages; a non-variable projected expression requires an alias. Aggregate
  aliases are ordinary names downstream, so grouped results can be filtered, ordered, and
  paginated.
- **Statement shape.** A statement becomes read stages, then optional write clauses, then
  an optional final `RETURN`. Write clauses still follow every read stage; a `MATCH` after
  a write clause remains rejected. A read statement still requires a matching stage and a
  `RETURN`.
- **Plan inspection.** The plan becomes an ordered list of stages, and `Graph.explain`
  reports the access path of each stage rather than of a single match.
- **Explicit rejection.** `UNWIND`, subqueries (`CALL { ... }`, `EXISTS { ... }`), `CASE`
  expressions, map literals, `MERGE` and its conditional updates, map assignment, index
  access, and `WITH *` remain rejected with a query error. The unsupported list shrinks;
  it does not become permissive by accident.

No public entry point changes: `Graph.query`, `Graph.prepare`, `PreparedQuery.execute`,
`Graph.explain`, and `Transaction.query` keep their signatures and result model. The
statements they accept grow.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `graph-query-language`: the statement shape, pattern matching, scope, aggregation,
  ordering, projection, plan inspection, and error boundary change to support
  variable-length patterns, multiple patterns and match stages, `OPTIONAL MATCH`, and
  `WITH`.

## Impact

- Query front end: `tokens`, `parser`, and `ast` gain quantified relationship patterns,
  pattern lists, optional matching, and `WITH` stages.
- Analysis: `semantic` replaces the single-match model with a stage model, tracks variable
  scope across stages, validates optional-variable use, and applies grouping per stage.
- Planning and execution: `plan` reports stages; `compiler` compiles a joinable pattern
  set and a bounded quantified expansion; `executor` applies stages in order and keeps
  the existing snapshot, aggregation, ordering, and pagination behavior for each stage.
  `explain` reports each stage.
- Tests: the parser and semantic suites that assert these forms are rejected must change
  to assert the new behavior; the conformance suite gains every new form; traversal
  fixtures cover diamond, directed cycle, parallel relationships, and self-loop for
  quantified matching.
- Documentation: `docs/query-language.md` gains the grammar, semantics, and limits;
  `README.md` gains runnable examples; `CHANGELOG.md` gains an `[Unreleased]` entry.
- No storage, schema, index, transaction, or migration change. No dependency change.
- Performance: a statement may now execute more than one SQL statement, one stage at a
  time, and quantified segments expand in Python under the declared bound. Each stage
  keeps index use and the existing single read/write transaction boundary.

## Non-Goals

- `MERGE`, `ON CREATE SET` / `ON MATCH SET`, `UNWIND`, subqueries, `CASE`, map literals,
  index access, and `WITH *`.
- `shortestPath()` or other path functions inside the dialect; the Python traversal API
  is unchanged.
- Streaming results, early `LIMIT` termination in SQL, query optimization across stages,
  or merging consecutive stages into one SQL statement.
- Composite, label-scoped, full-text, or uniqueness indexes; bulk import; schema or file
  format changes.
