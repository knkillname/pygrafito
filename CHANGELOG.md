# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A data-driven conformance corpus at `tests/conformance/cases.json`, executed by
  `tests/test_conformance.py`. The matrix/corpus consistency test keeps every `supported` row
  covered and every case tied to a matrix feature.
- The canonical GQL surface is executable: `INSERT`, `FOR`, `FILTER`, `OFFSET`, `RETURN ALL`,
  `RETURN *`, `NULLS FIRST`/`NULLS LAST`, `NODETACH DELETE`, the `->`, `<-`, `-`, and `~`
  directions, label expressions with `&`, `|`, `!`, and `%`, `IS` labels, inline element
  `WHERE`, and `--` line comments. `CREATE`, `UNWIND`, stage `WHERE`, `SKIP`, `-->`, `<--`, and
  `:A:B` remain compatibility aliases.
- A runnable example layer under `examples/` with a `python -m examples` front door, three
  audience lanes, terminal tours, and a deterministic builder. It ships a curated franchise graph
  spanning three sources, derived cast and place aggregates, and a version 2 JSONL snapshot.
- The example cast and place datasets use weighted edges with explicit `basis` metadata, and the
  synthetic scale generator is shared with the benchmark harness.
- A GQL tour catalog classifies each `examples/tours/*.gql` file by profile tier and names the
  follow-up change that will migrate it.
- A local-only screenplay and transcript extractor that emits aggregate JSON without dialogue or
  action text, tested with an invented fixture.
- A published GQL language profile at `docs/reference/gql-profile.md`, covering the five-tier
  construct classification, canonical surface, compatibility aliases and constructs, pygrafito
  extensions, path-mode and query-budget decisions, conformance matrix, corpus contract, and
  migration guidance. The current release continues to use the transitional Cypher-flavored
  dialect; the profile marks unimplemented canonical forms as target or gated.
- A documentation contract test that keeps the GQL profile page, tier headings, and conformance
  matrix statuses consistent.
- Relationships carry zero or more labels, can be directed or undirected, and expose a sorted
  label tuple and a `directed` flag. The Python API, traversal, query dialect, shell, indexes,
  constraints, and interop format use the new element model.
- `Graph.add_labels` and `Graph.remove_labels` accept a `Relationship` snapshot as well as a
  `Node`, so relationship labels can be added and removed directly.
- Schema version 2 and JSONL snapshot version 2. Snapshots carry relationship `labels` and
  `directed`, and the read-only views expose the same fields.

### Changed

- The frontend recognizes the target GQL vocabulary. Constructs the profile lists but this
  release cannot execute now raise a positioned semantic error naming the construct and the
  follow-up change, instead of a generic unexpected-token error.
- The query-language policy now classifies every construct as canonical GQL, synthetic alias,
  compatibility construct, pygrafito extension, or out of profile. The target default path mode
  is ISO `WALK`, gated on a query budget; the legacy `*n..m` quantifier keeps `TRAIL`.
- **BREAKING** Element ids are allocated with `AUTOINCREMENT` and are never reused after a
  delete.
- **BREAKING** `Relationship.type` is replaced by `Relationship.labels` and
  `Relationship.directed`; `Graph.add_relationship` and `Graph.find_relationships` take labels
  and an optional direction filter.
- **BREAKING** Relationship uniqueness constraints scope by label instead of a single
  relationship type.
- **BREAKING** A version 1 database or JSONL snapshot is refused. This pre-1.0 release does not
  migrate the old layout; create a fresh graph or export with 0.8 first.
- `/opsx-apply` runs must now update the Sphinx documentation under `docs/` for every behavior,
  public API, CLI, or configuration change they implement, and pass `hatch run docs:build` before
  marking the affected tasks complete.

### Removed

- **BREAKING** `--` is no longer an undirected relationship arrow. It is a line comment, a `--`
  that immediately follows a node or relationship pattern is a syntax error, and the replacement
  for the old form is `-`.
- **BREAKING** `Relationship.type`, the single relationship-type column, the version 1 snapshot
  reader, and the version 1 view definitions.

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
