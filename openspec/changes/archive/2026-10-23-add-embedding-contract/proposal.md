# Proposal

## Why

`pygrafito` is safe for one handle in one thread and offers no way to declare that a property
must stay unique, so it cannot be embedded where a second process reads the file and the caller
relies on an upsert idiom. This change makes the file shareable and the data self-defending; it
follows `add-batch-ingestion` and precedes `add-data-interop`.

## What Changes

- Define the embedding contract for file-backed graphs. A handle belongs to the thread that
  opened it; several handles may open the same file, in one process or several; at most one
  writer runs at a time; each public read observes a single committed state; a lock wait that
  exceeds the busy timeout raises a dedicated error. Using a handle from another thread raises a
  dedicated error instead of a driver error.
- Make first open safe when several processes race on a new file. The journal-mode switch is
  retried because the busy timeout does not cover it, and schema bootstrap runs inside a write
  transaction that re-reads the schema version.
- Prefer WAL and report the effective journal mode. Where the platform cannot provide WAL, the
  graph still opens and stays consistent, but a reader is not guaranteed to read while a writer
  commits.
- Refuse to open a foreign SQLite file for writing, matching the read-only path, so that opening
  a database never adds a graph schema to an unrelated file.
- Add uniqueness constraints scoped to one label and one property key for nodes, and to one
  relationship type and one property key for relationships. Constraints are declared, listed,
  and dropped through `Graph`, persist in the file, and are enforced by the database on every
  write, including writes made by an older build or an external SQLite client.
- Enforce uniqueness type-sensitively: `true`, `1`, `1.0`, and `"1"` are four distinct values.
  An element that does not carry the scope label or type, or does not have the property, is
  exempt.
- Detect a violation at the statement that causes it rather than at commit, so a transaction
  cannot hold a transient duplicate. Swapping two unique values needs a temporary value or two
  statements.
- Raise a dedicated violation error that names the constraint, the offending value, and the
  existing element that holds it. Declaring a constraint over data that already violates it
  raises the same error and creates nothing.
- Reject constraint changes while an explicit transaction is open on the same handle, or on a
  read-only handle, consistent with index changes.
- Record that the schema version tracks incompatible storage layout, not features: additive
  objects such as constraints never change it.
- Out of scope: existence constraints, node-key constraints, streaming results, async,
  connection pooling, a server mode, and weighted shortest paths. Streaming is a later change
  because it changes the materialized-result contract rather than the embedding contract.

## Capabilities

### New Capabilities

- `graph-constraints`: uniqueness constraint declaration, listing, removal, persistence,
  type-sensitive enforcement on every write path, and violation reporting.

### Modified Capabilities

- `property-graph`: replaces the single-writer concurrency statement with the embedding
  contract, and adds the read-snapshot, journal-mode, schema-layout, foreign-file, and
  portable-file requirements.

## Impact

- Affected code: connection and schema bootstrap; a new constraint registry; graph facade;
  error translation on the node, label, property, relationship, query, and import write paths;
  the error model; CLI metadata commands; documentation, README, and `CHANGELOG.md`.
- Public API: `Graph.create_node_uniqueness_constraint`,
  `Graph.create_relationship_uniqueness_constraint`, `Graph.constraints`, `Graph.drop_constraint`,
  a `Constraint` value type, `ConstraintViolationError`, `LockTimeoutError`, a handle-affinity
  error, and a readable journal mode. `ElementKind` becomes the shared element-kind name, with
  `IndexKind` kept as an alias. Existing signatures keep their behavior.
- Storage: constraints are standard indexes and triggers in `sqlite_master`; there is no catalog
  table and no schema version change. A file written by this change stays openable by older
  builds, which remain bound by the constraints.
- Dependencies: none. Concurrency tests use the standard-library `multiprocessing` and
  `threading` modules.
- Tests: concurrent first open, multi-handle and multi-process read and write, a read-only reader
  during a commit, foreign-file refusal, per-read snapshots, enforcement on every mutation path,
  type distinction, label acquisition, `MERGE`, import batches, violation payload, declaration
  over existing data, and reopen persistence.
