# Proposal

## Why

Property filters cannot use an index today. SQLite stores properties as JSON text and
the dialect pairs `json_type(...)` with `json_extract(...)` correctly, but the JSON path
is bound as a parameter, so SQLite cannot match an expression index even if one exists.
Every property predicate is therefore a scan of the candidate rows: measured on a
200,000-node graph, a single equality filter costs about 65 ms, and cost grows with the
number of nodes carrying the label. That contradicts the library's defining promise:
query cost should be proportional to the query, not to the database.

This is the first of two engine changes that make the embedded cost story true. It lands
now because every later capability (broader language, operational tooling, a public
performance statement) is measured against an engine that currently scans.

## What Changes

- Add an explicit property-index API on `Graph`: `create_node_index(key)`,
  `create_relationship_index(key)`, `drop_index(...)`, and `indexes()` returning the
  declared indexes. Indexes are key-scoped, not label-scoped, because one expression
  index on the `props` column serves every label.
- Create each declared index as a compound expression index over
  `(json_extract(props, path), json_type(props, path))`, so the existing type/value
  pairing becomes a seek instead of a scan and SQLite maintains the index itself.
- Emit JSON paths as escaped SQL literals instead of bound parameters in every property
  predicate: the query compiler and both repository lookup paths. The property key is
  validated and escaped by one audited helper; parameter *values* stay bound.
- Discover declared indexes from `PRAGMA index_list` using reversibly encoded index
  names, so no schema version bump is required and files stay usable by older and newer
  builds in both directions.
- Keep planner statistics current: analyze after index creation, and run
  `PRAGMA optimize` when a file-backed graph closes.
- Add a structural index on relationship type, so a type filter without a bound endpoint
  does not scan every relationship.
- Add `Graph.explain(text)` returning the planned query plan, so a caller can see when a
  statement still scans.
- Add a reproducible benchmark harness and `docs/performance.md` recording the measured
  before/after numbers, linked from the README.
- Record the change in `CHANGELOG.md`.

No statement results change. An index is a performance declaration only; the same
statement returns the same rows with or without one.

## Capabilities

### New Capabilities

- `graph-indexes`: declared property and structural indexes: creating, dropping, listing,
  encoded identity, maintenance across writes and deletes, statistics, plan inspection,
  and the guarantee that an index never changes results.

### Modified Capabilities

<!-- None. Property lookup semantics, strict values, and query results are unchanged. -->

## Impact

- `src/pygrafito/storage/`: index registry and DDL (`schema.py`), a shared escaped
  property-predicate helper, and the two repository `find` paths that currently build
  predicates independently.
- `src/pygrafito/engine/query/compiler.py`: property predicates in `PredicateBuilder`,
  plus the plan needed for `explain`.
- `src/pygrafito/engine/graph.py` and `__init__.py`: the index API, `explain`, close-time
  optimization, and the new public `Index` value type.
- `src/pygrafito/model.py`: immutable index description.
- `docs/performance.md`, `README.md`, `CHANGELOG.md`, `benchmarks/`, and tests across
  storage, query compilation, planning, and integration.
