# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Queries can now repeat a whole path shape with grouped terms such as
  `((a)-[r:TRUSTS]->(b)){2}`. Variables introduced inside a group bind ordered lists, nested groups
  flatten in traversal order, zero iterations bind empty lists, and a group can carry its own path
  variable and inner path mode.
- Queries can now select routes with `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST k`.
  Selection happens per start and end node, returns routes in deterministic length and path order,
  and stops expanding once each pair has enough routes. Use `SHORTEST 0` to return no route.
- Queries can now choose how relationships are shared across a `MATCH` clause with
  `DIFFERENT EDGES` or `REPEATABLE ELEMENTS`. `DIFFERENT EDGES` lets each relationship satisfy at
  most one pattern in the clause; `REPEATABLE ELEMENTS` is the default and keeps today's results.
- Queries can now follow relationships without a depth limit with `*`, `+`, `{m,}`, and the
  legacy `*n..` form. A bare `*` includes zero-hop matches, so use `+` or `{1,}` when at least one
  relationship is required. A final `LIMIT` stops an open walk as soon as the requested rows
  exist, and an open walk without one stops at the query budget instead of returning a truncated
  result.
- Queries can now use `CASE`, map literals, list indexing, slicing, and comprehensions,
  `||` string concatenation, path functions, and the extended scalar functions.
- Queries can now use read-only `EXISTS { ... }` and `COUNT { ... }` subqueries, including
  correlated forms that refer to the current row.
- Queries can now combine read-only results with `UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT`,
  with ordering and pagination over the combined rows.
- `WITH *` now keeps the full current scope without listing every variable.
- The GQL profile now publishes the complete 1.0 target, including the expression, subquery,
  set-operation, and path surfaces, and distinguishes what works today, what is planned for 1.0,
  and what is intentionally unsupported. The profile also defines the 1.0 completion gate and the
  policy for changing it after release.
- The GQL profile now explains how path modes, match modes, repetition counts, and shortest-path
  selection work together, including what each form binds when it matches nothing, which
  combinations are rejected, and how to migrate a query when the planned path features arrive.

### Changed

- **BREAKING:** `WHEN`, `THEN`, `ELSE`, `END`, `UNION`, `INTERSECT`, and `EXCEPT` are now reserved
  keywords. If an existing query uses one of these words as a variable or alias, wrap it in
  backticks; for example, `when` becomes `` `when` ``.
- **BREAKING:** `DIFFERENT`, `EDGES`, `REPEATABLE`, and `ELEMENTS` are now reserved keywords. Wrap an
  existing variable or alias that uses one of these words in backticks; for example, `edges`
  becomes `` `edges` ``.
- **BREAKING:** `ANY` and `SHORTEST` are now reserved keywords. Wrap an existing variable or alias
  that uses one of these words in backticks; for example, `any` becomes `` `any` ``.

## [0.9.0] - 2026-10-27

This is a pre-1.0 release focused on GQL composition and path control. It adds multi-step
queries, grouping, path modes, query budgets, richer relationship labels and directions, and
version 2 snapshots and views. The GQL profile is not complete yet: open-ended traversal, match
modes, grouped quantified paths, path search, and parts of the expression vocabulary remain
deferred; the [published GQL
profile](https://knkillname.github.io/pygrafito/reference/gql-profile.html) explains what is ready
and what is not.

This release also includes breaking changes: paths now default to `WALK`, element ids are not
reused, relationship uniqueness is label-scoped, relationships use labels and direction, `--` is a
comment, and storage moves to version 2.

**Upgrading from 0.8:** this release writes database and snapshot version 2 and refuses version 1
files. There is no in-place upgrade. Export any 0.8 data with 0.8 before moving it.

### Added

- Build multi-step GQL queries with `LET`, `NEXT`, `YIELD`, and `FINISH`, including statements that
  return no rows.
- Group results with `GROUP BY`, including `GROUP BY ()`, `RETURN DISTINCT ... GROUP BY`, and
  expression keys. `RETURN NO BINDINGS` remains available as a final-only zero-column result.
- Number rows with `FOR ... WITH ORDINALITY` or `WITH OFFSET`, using one-based and zero-based
  positions; both also work with `UNWIND`.
- Later `NEXT` steps can see earlier writes, while the whole statement still uses one transaction
  and one query budget.
- Every query is bounded by a configurable budget covering relationship expansions, intermediate
  rows, and optional wall-clock time. Set a graph-wide default or override it per query; exceeding
  the budget stops before returning a result and rolls back writes.
- Control path repetition with `WALK`, `TRAIL`, `SIMPLE`, and `ACYCLIC`, set per clause or per
  path. `SIMPLE` allows a closed path; `ACYCLIC` does not.
- Use the closed quantifiers `{n}`, `{m,n}`, and `{,n}`. The legacy `*n..m` form still works with
  trail semantics.
- All edge directions are available, including `<->`, `<~`, and `~>` for either-direction,
  incoming-or-undirected, and outgoing-or-undirected relationships.
- Canonical GQL runs end to end, including `INSERT`, `FOR`, `FILTER`, `OFFSET`, `RETURN ALL` and
  `RETURN *`, null ordering, `NODETACH DELETE`, label expressions, `IS`, inline `WHERE`, and `--`
  comments. The familiar `CREATE`, `UNWIND`, stage `WHERE`, `SKIP`, double-dash arrows, and
  `:A:B` spellings still work.
- Relationships carry zero or more labels and can be directed or undirected. The Python API,
  traversal, query language, shell, indexes, constraints, and interop format all use the new
  model, including sorted labels and a `directed` flag.
- You can add or remove labels directly on relationship snapshots with the same API used for
  nodes.
- A new runnable example layer includes a single command-line front door, three audience lanes,
  terminal tours, a deterministic builder that produces a database or version 2 snapshot, and a
  curated franchise graph spanning three sources. Tours are labeled by GQL profile tier.
- The example cast and place data include weighted relationships and source metadata. A local-only
  extractor can turn screenplay and transcript sources into aggregate JSON without storing
  dialogue or action text.
- The GQL profile is published with the five-tier construct classification, canonical surface,
  aliases, extensions, path-mode and budget rules, conformance matrix, and migration guidance.
  Open-ended traversal is marked deferred, the profile and matrix are checked for consistency, and
  a data-driven conformance suite backs the matrix.

### Changed

- The composition surface now executes end to end; only open-ended traversal remains gated.
- Unsupported constructs now fail with a clear, positioned message that names the missing feature
  instead of a generic parse error.
- Every query construct is now labeled as canonical GQL, compatibility, extension, or out of
  profile, so unsupported syntax has a clear status. An explicit path mode still wins over the
  default.
- **BREAKING** Canonical paths now default to `WALK` instead of the old relationship-unique trail.
  Use `MATCH TRAIL` or a legacy `*n..m` quantifier to keep the old behavior. The Python `paths()`
  helper remains a bounded trail enumerator.
- Open-ended bounds such as `*`, `+`, `*n..`, and `{m,}` are not available yet and fail with a
  clear message.
- **BREAKING** Element ids are never reused after deletion.
- **BREAKING** Relationships now use labels and direction instead of a single `type`. Relationship
  creation and lookup take labels and an optional direction filter.
- **BREAKING** Relationship uniqueness constraints now scope by label instead of a single
  relationship type.
- **BREAKING** Databases and JSONL snapshots now use version 2. Version 1 files are refused; there
  is no in-place upgrade. Export 0.8 data with 0.8 before moving it. Read-only views are also
  version 2 and expose relationship labels and direction.
- Contributors now update the documentation and pass the docs build as part of every apply run, so
  behavior changes ship with current documentation.

### Removed

- **BREAKING** `--` is now only a line comment. Use `-` for an undirected relationship; a `--` that
  follows a pattern is a syntax error.
- **BREAKING** The old single-type relationship model, the version 1 snapshot reader, and the
  version 1 views have been removed.

## [0.8.0] - 2026-10-26

### Added

- `UNWIND` expands a list-valued expression into rows, acts as a statement's row source, and
  feeds later stages and write clauses.
- `MERGE` matches one fixed-length pattern as a whole or creates its unbound elements,
  with `ON CREATE SET` and `ON MATCH SET` conditional updates. It runs once per input row, so
  later rows see earlier creations.
- Pattern property maps accept non-aggregate expressions evaluated against the current row, so a
  row can drive a `MATCH`, `CREATE`, or `MERGE` property value.
- `Graph.import_rows` and `Graph.import_file` import CSV, JSONL, and in-memory mappings with a
  statement-driven mapping, independent or atomic batch transactions, and row-level failure
  notes. `ImportSummary` reports the rows, batches, and aggregate mutation counts.
- The `.import` shell command exposes the importer with `--format`, `--batch`, and `--atomic`.
- `PreparedQuery.is_write` and `PreparedQuery.parameters` expose statement metadata before
  execution.
- The embedding contract for file-backed graphs: `Graph.journal_mode` reports the mode the
  connection obtained, `Graph.open(..., busy_timeout=...)` bounds a lock wait,
  `HandleAffinityError` rejects use from a thread that does not own the handle, and
  `LockTimeoutError` reports an exhausted write-lock wait. Each public read observes one
  committed state, including traversal capture and shortest-path evaluation. See
  `docs/embedding.md`.
- Node and relationship uniqueness constraints: `Graph.create_node_uniqueness_constraint`,
  `Graph.create_relationship_uniqueness_constraint`, `Graph.constraints`, and
  `Graph.drop_constraint`, plus the `Constraint` value type and `ElementKind`. Constraints
  persist in the file, are enforced by SQLite on every write path, and compare values by type
  and value. `ConstraintViolationError` reports the constraint, offending value, and surviving
  holder. See `docs/constraints.md`.
- The `.constraints` shell command lists declared constraints, and `.schema` also reports
  constraints and the effective journal mode.
- A strict, versioned JSONL snapshot format with a header, element counts, tagged node and
  relationship records, canonical ordering, and rejection of unknown fields, duplicate keys,
  truncated files, and count mismatches. See `docs/interop.md`.
- `Graph.export_jsonl` writes one consistent snapshot in a single read transaction, streams
  nodes and relationships, refuses an existing destination unless `overwrite=True`, and refuses
  the open database path and its journal sidecars.
- `Graph.restore_jsonl` loads a snapshot into an empty graph, remaps node and relationship ids,
  verifies the header counts, and runs in one transaction. `replace=True` clears and restores
  atomically, so a failure restores the original graph.
- Read-only `graph_nodes`, `graph_node_labels`, `graph_relationships`, and `graph_meta` views,
  published on a write-capable open with a view-version record. `Graph.view_version` reports the
  published version, or zero when the views are absent; read-only opens leave older files
  untouched. See `docs/interop.md`.
- The `.export` and `.restore` shell commands expose snapshot export and restore, including
  `--overwrite` and `--replace`, with the same transaction, read-only, and failure-isolation
  rules as the other maintenance commands.
- A Sphinx documentation site under `docs/`, built with MyST Markdown and Furo, with a landing
  page, a five-minute quickstart, task-first guides, reference pages, and a public API reference.
  The site deploys to GitHub Pages from `main`.
- `hatch run docs:build` and `hatch run docs:serve`, backed by an optional `docs` dependency extra.
  Every landing, quickstart, and guide example is executed by the test suite, and reference and API
  snippets are syntax-checked.

### Changed

- Documentation is organized into guides and reference pages, and `README.md` is now a compact
  GitHub/PyPI landing with one tested example and links to the published site. The
  `Documentation` URL points at `https://knkillname.github.io/pygrafito/`.
- Pattern property maps in `MATCH` and `CREATE` may reference variables from earlier stages;
  `CREATE` no longer requires literals or parameters. A pattern still cannot reference a
  variable it introduces itself.
- `ON` is a reserved word.
- `Database` initializes the schema inside one `BEGIN IMMEDIATE` transaction and re-reads the
  schema version after taking the write lock. An already-current schema skips the write
  transaction, so opening a graph while another process writes does not need a write lock.
- The journal-mode switch during open retries a bounded number of times, because SQLite's busy
  handler does not cover `PRAGMA journal_mode`.
- Opening an existing SQLite database that records no graph layout and contains unrelated tables
  now raises `UnsupportedSqliteError` on the writable path too, matching the read-only path and
  leaving the file unchanged.
- `IndexKind` is an alias of `ElementKind`, so indexes and constraints share one element-kind
  name. `IndexKind` remains exported.
- `.schema` output now includes a `Constraints` section and a `Journal mode` section.

### Fixed

- Several processes opening the same fresh database file no longer fail with
  `database is locked` while switching to write-ahead logging.
- A writable open no longer adds the graph schema to an unrelated SQLite file.

## [0.6.0] - 2026-10-23

### Added

- Read-only graph handles: `Graph.open(path, readonly=True)` serves reads, queries, and
  traversal from an existing file, never creates a missing file, and raises `ReadOnlyError`
  for every write, transaction, or index change.
- Manual transaction control: `Transaction.begin`, `Transaction.commit`, and
  `Transaction.rollback` drive a transaction without a context block, while the context-manager
  form keeps its previous behavior.
- `Graph.backup_to` writes a consistent copy of a live database through a temporary file and an
  atomic replace, and `Graph.check_integrity` reports storage and foreign-key problems. Both work
  on a read-only handle.
- A command-line shell available as the `pygrafito` command and as `python -m pygrafito`:
  interactive and scripted statement input, dot-commands, `table`/`json`/`jsonl`/`csv`/`line`
  output, redirection, parameters, explicit transactions, graph introspection, read-only
  sessions, and integrity and backup commands. See `docs/cli.md`.

### Changed

- The type checker also searches the repository root so test-package imports resolve during
  `hatch check`.

## [0.5.0] - 2026-10-23

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
