# Proposal

## Why

The database file is ordinary SQLite, but the library treats that as an implementation detail.
There is no way to export a graph without writing Python, and no documented view that another
SQLite client can read, so spreadsheets, BI tools, notebooks, and other languages must
reverse-engineer private tables. "Your data is yours" is the core promise of an embedded
engine; this change makes the file a public interface. It follows `add-batch-ingestion` and
`add-embedding-contract`, which establish the writes and the multi-process reads this change
exposes.

## What Changes

- Add a strict, self-verifying JSONL snapshot: a versioned header with element counts, tagged
  node and relationship records, canonical ordering, and rejection of unknown fields, duplicate
  keys, truncated files, and count mismatches. `Graph.export_jsonl` writes one consistent
  snapshot, streams rather than materializing the graph, and returns element counts.
- Add a matching restore path. `Graph.restore_jsonl` loads a snapshot into an empty graph by
  default, remaps node and relationship ids, verifies the header counts, and runs in one
  transaction. A non-empty target is refused unless the caller requests an atomic replace,
  which clears and restores in the same transaction so a failure leaves the original graph
  intact.
- Add stable read-only views over nodes, labels, and relationships, plus a metadata view
  carrying the view version. Views are published on a write-capable open and never used by the
  engine for its own reads; a read-only open leaves them untouched so older files stay
  readable. `Graph.view_version` reports the published version or zero.
- Add `.export PATH [--format jsonl] [--overwrite]` and `.restore PATH [--replace]` to the
  shell, with the same transaction, error, and output-stream rules as the other maintenance
  commands.
- Refuse an export destination that already exists unless overwrite is explicit, and always
  refuse the live database path and its sidecars. A failed export leaves the destination
  untouched.
- Out of scope: a text query-script dump (the dialect cannot rebind variables across
  statements, so a faithful script dump cannot round-trip), CSV export, full-text search,
  vector search, write-through SQL, and a server mode.
- Full-text search is deliberately deferred to its own capability. It is a new index kind with
  its own schema object and query syntax, not an export concern.

## Capabilities

### New Capabilities

- `graph-interop`: the stable external representation of a graph: the JSONL snapshot and
  restore contract, the read-only view schema and its version, round-trip and identity rules,
  and the read-only guarantee for external readers.

### Modified Capabilities

- `graph-shell`: adds the `.export` and `.restore` dot-commands, their options, and their
  output and failure behavior.

## Impact

- Affected code: a new interop module for JSONL encoding, decoding, export, and restore; a
  storage view module for the view definitions and version checks; schema open sequencing; the
  graph facade; CLI command, session, and formatting modules; documentation, README, and
  `CHANGELOG.md`.
- Public API: `Graph.export_jsonl`, `Graph.restore_jsonl`, `Graph.view_version`,
  `InteropSummary`, plus the `.export` and `.restore` shell commands. No existing signature
  changes.
- Storage: four derived views, including a view-version record. The node and relationship
  tables are unchanged, no table is added, and the schema version does not move for this
  change.
- Compatibility: a read-only open of a database that predates the views still works; the next
  write-capable open publishes them. Older builds ignore the views and continue to open the
  file.
- Dependencies: none. JSONL uses the standard-library `json` module.
- Tests: strict format and count verification, unknown fields and duplicate keys, phase order,
  round-trip with types, labels, parallel relationships, self-loops, and an empty graph;
  deterministic output; export overwrite and destination guards; restore into a non-empty graph
  refused; atomic replace rollback; views queried from a separate read-only SQLite connection;
  view publication, version drift, and name collisions; `Graph.view_version`; shell commands.
