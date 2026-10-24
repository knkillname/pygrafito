# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Multiple comma-separated path patterns per `MATCH` and multiple `MATCH`
  clauses, joined on shared variables. A later match stage removes rows without
  a match.
- `OPTIONAL MATCH` with left-join semantics: unmatched rows survive with the
  variables the stage introduces bound to null.
- `WITH` stages that project rows into a new scope, with `DISTINCT`, `WHERE`,
  `ORDER BY`, `SKIP`, `LIMIT`, and per-stage aggregation.
- Quantified relationships with an explicit upper bound (`*n`, `*n..m`,
  `*0..m`). Trails are relationship-unique, a quantified relationship variable
  binds the traversed list, and path variables include the expanded
  relationships.

### Changed

- `Graph.explain` reports the access path of every read stage in order and
  includes a synthetic expansion line for a stage run by the pattern engine.

## [0.4.0] - 2026-10-23

### Added

- Explicit, key-scoped property indexes for nodes and relationships:
  `Graph.create_node_index`, `Graph.create_relationship_index`, `Graph.drop_index`,
  and `Graph.indexes`. Indexes persist in the database file without a schema version
  change and accelerate property equality, range, and membership filters.
- `Graph.explain`, returning the planned access path for a statement without executing
  it.
- A structural index on relationship type, so a type filter without a bound endpoint
  does not read every relationship.
- Planner statistics refresh after an index is declared or removed, and on close of a
  file-backed graph.
- Write clauses in the query dialect: `CREATE` for nodes and relationships,
  `SET` and `REMOVE` for properties and labels, and `DELETE` / `DETACH DELETE`
  for elements.
- `QueryResult.summary`, a `MutationSummary` with the number of created and
  deleted elements and the property and label changes applied by a statement.
- Optional `RETURN` after a write clause, and prepared write statements with
  empty columns.
- Deduplicated mutation cardinality: an entity bound by several match rows is
  written or deleted once per statement.
- Atomic write statements: a standalone statement runs in its own
  `BEGIN IMMEDIATE` transaction, and a write inside an explicit transaction runs
  in a savepoint.

### Changed

- `traverse`, `paths`, and `shortest_path` materialize only the region within the
  caller's depth and direction bounds instead of loading every node and relationship, so
  traversal cost tracks the explored region rather than the size of the database.
- Property filters and lookups embed the property key as an escaped JSON path in the
  statement instead of binding it as a parameter, so SQLite can match an index built over
  the same path. Statement results, ordering, and value equality are unchanged.
- Property keys containing null characters are rejected with a validation error, because
  a JSON path cannot address them.
- `Graph.query`, `Transaction.query`, and `PreparedQuery.execute` execute read
  and write statements. Statements containing a write clause no longer raise a
  read-only query error.
- A statement is now an ordered clause sequence with optional `MATCH` and
  `RETURN`, instead of one required `MATCH` and one required `RETURN`.
- Storage and domain failures raised during a write are surfaced as
  `QueryExecutionError`.

## [0.3.0] - 2026-10-23

### Added

- Read-only pattern query language with `MATCH`, `WHERE`, `RETURN`, `DISTINCT`,
  `ORDER BY`, `SKIP`, and `LIMIT`, including node and relationship property
  maps, relationship directions and type alternatives, path variables, repeated
  variables, and `$name` parameters.
- `Graph.query`, `Graph.prepare`, `PreparedQuery`, and `Transaction.query`,
  returning materialized `QueryResult` objects with ordered columns and
  immutable `Row` mappings.
- Scalar functions and `count`, `collect`, `sum`, `avg`, `min`, and `max`
  aggregates with implicit grouping, `DISTINCT` variants, numeric equality,
  query-only nulls, and documented ordering and empty-input semantics.
- `QueryError`, `QuerySyntaxError`, `QuerySemanticError`, and
  `QueryExecutionError` with optional source line and column positions.
- A language reference in `docs/query-language.md`, executable query examples in
  the README, and a dialect conformance suite.

## [0.2.0] - 2026-10-22

### Added

- `GraphClosedError`, raised consistently when a closed graph handle is used.

### Changed

- Using a closed graph handle now raises `GraphClosedError` instead of leaking
  SQLite exceptions or a transaction error.
- Convenience writes inside an active explicit transaction now raise
  `TransactionError` before executing SQL instead of failing at `BEGIN`; the
  active transaction remains usable when the caller handles the error.
- Graph-building test fixtures now use TRON names, enforced by
  `tests/test_naming_convention.py`, and README examples are executed by
  `tests/test_readme.py`.
- Added CI jobs for `hatch check`, `hatch test`, wheel build and install smoke
  testing, and verification that `py.typed` and `LICENSE.txt` are packaged.
- Updated the copyright holder, package author, and project URLs to Mario
  Abarca and the `knkillname/pygrafito` repository.
- Documented that test fixtures use TRON franchise names and avoid other graph
  database products or trademarks.

## [0.1] - 2026-10-22

### Added

- Embedded property-graph engine backed by a single SQLite database or an
  in-memory database.
- Nodes with multiple labels and strict typed properties: booleans, signed
  64-bit integers, finite floats, strings, and homogeneous lists of those
  scalars.
- Canonical JSON property storage with type-sensitive and list-order-sensitive
  equality lookups.
- Directed typed relationships, including self-loops and parallel
  relationships.
- Immutable `Node`, `Relationship`, and `Path` snapshots and a domain error
  hierarchy.
- Explicit transactions using `BEGIN IMMEDIATE`, with commit on success and
  rollback on failure; every convenience write is atomic on its own.
- Detaching node deletion, with connected-node protection by default.
- Direction-aware reachability traversal that yields each node once at its
  shortest depth.
- Shortest-path search using bidirectional breadth-first search.
- Lazy, depth-bounded enumeration of relationship-unique trails with optional
  result limits.
- Snapshot-consistent traversal results unaffected by later writes.
- Python 3.14 packaging with strict type hints, numpydoc docstrings, Ruff,
  Pyrefly strict, pytest, and a coverage gate.
- README documentation for persistence, CRUD, transactions, deletion, and
  traversal.

### Changed

- Raised the minimum Python version from 3.8 to 3.14.
- Configured Hatch `check` and `test` as the project quality gates, using Ruff
  and Pyrefly.
