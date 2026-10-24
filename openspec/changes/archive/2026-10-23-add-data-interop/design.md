# Design

## Context

See `proposal.md` for motivation and `specs/` for the behavior contract. The current state that
shapes this approach:

- One `sqlite3.Connection` per `Graph`, owned by the opening thread. File databases prefer WAL;
  read-only handles open with `mode=ro` and `PRAGMA query_only`.
- The layout is three tables, `nodes`, `node_labels`, and `relationships`, with canonical JSON
  property text. `PRAGMA user_version` tracks the layout only and stays at `1`.
- `Schema.bootstrap(readonly=True)` replays the idempotent DDL because a read-only connection
  cannot take a write lock. `CREATE VIEW` is not a no-op when the view is missing.
- `Graph._read_snapshot()` starts one deferred read transaction for multi-statement reads.
  `Graph.backup_to()` writes a sibling temporary file and atomically renames it, and refuses an
  existing destination.
- `Schema.refuse_foreign_database()` ignores views, because it inspects `sqlite_master` for
  tables only.
- `engine.importing.JsonLinesReader` is a row-oriented reader for statement-driven imports; it
  accepts any JSON object and has no notion of graph identity, phases, or counts.
- `NodeRepository.create()` wraps each write in a savepoint and accepts arbitrary string property
  keys through `**properties`.

The new JSONL file and the SQL views are public contracts, so backward compatibility and failure
behavior drive the decisions below.

## Goals / Non-Goals

**Goals:**

- A snapshot that cannot silently lose data: strict field sets, duplicate-key rejection, explicit
  phase order, canonical bytes, and counts that detect truncation.
- An export that never leaves a partial destination and never replaces the live database.
- A restore that is atomic, including the clear performed by replace.
- Read-only SQL views that are additive and versioned, and that the engine never needs.
- Older files remain readable; no layout or schema-version change.

**Non-Goals:**

- A general row-import format. `graph-import` remains the statement-driven path for arbitrary
  rows.
- CSV export, a query-script dump, schema or constraint export, incremental sync, compression,
  or streaming a snapshot to standard output.
- Changing base table names, columns, or the layout version.
- A normalized per-property view, a server mode, or write-through SQL.

## Decisions

### 1. Snapshot envelope: header plus tagged records

The file begins with a header carrying `kind`, `format`, `version`, `nodes`, and
`relationships`, followed by records tagged `kind`. Alternatives considered:

- a version field on every record, which is repetitive and still provides no counts;
- two files, one for nodes and one for relationships, which complicates the shell and atomic
  publication;
- a footer record, which requires every consumer to handle a third record kind and still needs
  a count somewhere.

A header is the smallest self-identifying envelope that supports streaming and truncation
detection.

### 2. Counts in the header, verified at EOF

Export counts inside its read snapshot, writes the header, then streams. Restore counts the
records it accepts and compares them to the header before committing.

Without counts, a header-only file is a valid empty graph and a truncated export would restore
“successfully” as an empty graph. With counts, the same file fails and rolls back. A footer would
also work, but the header is already needed for identity and versioning.

### 3. Strict decoding

Records have exact field sets. Unknown fields, missing fields, wrong types, and duplicate JSON
keys are rejected. Duplicate keys need an `object_pairs_hook`, because Python's default decoder
keeps only the last value.

A permissive reader would silently accept a typo such as `lables`, restoring a node with no
labels. Silent loss is the failure mode this format exists to prevent.

### 4. Nodes before relationships

All node records precede every relationship record. Restore is then a single pass with no
relationship buffering. The alternatives are interleaving with an O(relationships) buffer, or a
second pass over the file, which a stream cannot guarantee. The exporter always emits the phases
in this order.

### 5. Identity: remap node ids; relationship ids are informational

Restore assigns new node ids in file order and keeps a source-id to new-id map. Relationship
endpoints resolve through that map. Source relationship ids are replaced and never referenced,
so they are not checked for uniqueness; this keeps restore memory at O(nodes) rather than
O(nodes plus relationships).

Preserving source ids would avoid the map but would trust arbitrary, sparse, or colliding
values, and would contradict the existing rule that `INTEGER PRIMARY KEY` ids are not durable
external keys. Remapping makes restore deterministic and safe.

### 6. Restore: empty-only by default, atomic replace

With `replace=False`, the target must be empty, checked inside `BEGIN IMMEDIATE` so another
writer cannot insert between the check and the restore. With `replace=True`, restore deletes all
relationships and then all nodes before loading, in the same transaction. Any failure rolls the
delete back with the data.

Clearing in a separate transaction is the one path that can leave an empty graph after a failed
restore. A separate `clear()` API would have the same problem. The atomic replace is the
explicit form of the proposal's “unless the caller explicitly clears it first.”

### 7. Export destination: refuse by default, explicit overwrite, path guards

Export writes a sibling temporary file and renames it into place. An existing destination is
refused unless overwrite is explicitly requested. Regardless of overwrite, the open database's
own path and its `-wal`, `-shm`, and `-journal` sidecars are refused.

Overwriting by default is convenient but makes a typo destructive, and exporting to the live
database path would replace the database itself. Writing directly to the destination would leave
a partial file on failure. The temporary file gives atomic publication; the guards protect the
live store.

### 8. Views: four views, with `graph_meta` as a view

The public views are:

- `graph_nodes(id, labels, properties)`;
- `graph_node_labels(node_id, label)`;
- `graph_relationships(id, start_id, end_id, type, properties)`;
- `graph_meta(key, value)`.

`graph_nodes.labels` is a JSON array produced by an ordered inner subquery and
`json_group_array`; `properties` is the canonical JSON text already stored. The normalized label
view serves readers that do not have JSON functions and scales better for label counts.
`graph_meta` carries `format` and `view_version`.

Alternatives:

- one wide view, which hides the normalized label path and makes label analytics awkward;
- a metadata table, which adds a table to the layout, touches `GRAPH_TABLES`, and weakens the
  “views are ignored” property;
- encoding the version in `PRAGMA user_version`, which is reserved for layout compatibility.

A view-based metadata record adds no table, does not move `user_version`, and stays out of the
foreign-database check by construction.

### 9. View publication on write-capable open only

A separate `Views.ensure(connection, readonly=...)` runs after `Schema.bootstrap()` and before
`PRAGMA query_only` is set. A write-capable open creates missing views, replaces older versions,
leaves newer versions untouched, and refuses when a reserved name is held by a table or by a
view not identified by `graph_meta`. A read-only open never writes and never tries to resolve a
collision.

Putting the view DDL in `Schema._STATEMENTS` would break read-only opens of older files, because
`CREATE VIEW` is not idempotent when the view is missing. Refusing a read-only open when views
are missing would break read-only archives and media. Tolerating the absent views keeps the
engine usable; the next write-capable open publishes them.

### 10. `Graph.view_version`

The property reads the published `view_version` and returns `0` when the views are absent. It
gives callers and tests an observable answer without opening a second SQLite connection, and it
makes the read-only publication gap explicit. A `.schema` line would serve operators only; the
property serves both.

### 11. `InteropSummary`

Export and restore return the same frozen `InteropSummary(nodes, relationships)`. Separate
`ExportSummary` and `RestoreSummary` types would duplicate the same two fields, and reusing
`ImportSummary` would report irrelevant rows, batches, and mutation counts.

### 12. Error mapping

Malformed snapshots, non-empty targets, existing destinations, and invalid options raise
`ValidationError`. Read-only, active-transaction, and closed-handle cases keep the existing
`ReadOnlyError`, `TransactionError`, and `GraphClosedError`. Restore attaches the file and
one-based line number as a note.

No new error class is introduced. The existing error taxonomy and the shell's handling already
cover these cases, and a new public exception would expand the surface without giving callers a
distinct recovery path.

### 13. Code placement and import direction

- `storage/views.py` owns the view SQL, version checks, publication, and collision detection.
- `engine/interop.py` owns the JSONL encoder and decoder, the exporter, the restorer, and
  `InteropSummary`.
- `Database` calls `Views.ensure` after the schema bootstrap.
- `Graph` exposes `export_jsonl`, `restore_jsonl`, and `view_version`; the CLI calls the same
  methods.
- Imports stay one-way: `model <- storage <- engine <- __init__`.
- New helpers are classes and methods, not module-level functions, matching the project style.

Putting the view DDL in `Schema` would couple the public interop contract to layout bootstrap;
putting the snapshot logic directly in `Graph` would make the facade too large.

### 14. Testing strategy

- Codec tests for the strict value matrix and malformed input.
- A golden snapshot for a TRON graph covering types, multiple labels, parallel relationships, a
  self-loop, an unlabeled node, and an empty graph.
- Determinism: export twice and compare bytes.
- Truncation, count mismatch, phase violation, duplicate keys, unknown fields, and invalid UTF-8.
- Restore into empty, non-empty refusal, atomic replace rollback, constraint enforcement,
  read-only refusal, and active-transaction refusal.
- Views through a separate read-only `sqlite3` connection: columns, labels, properties,
  `graph_meta`, refused writes, and engine reads with the views dropped.
- View publication on writable open, read-only tolerance, older/newer version drift, table and
  view collisions, and `Graph.view_version`.
- CLI tests for both commands: success, summaries, overwrite, replace, read-only, transactions,
  missing paths, bad options, and failure isolation.
- Graph-building fixtures use TRON names, as required by the naming convention test.
- Coverage remains at or above the project's 80% gate.

## Risks / Trade-offs

- **Read-only deployments on pre-view files do not see the views.** Document that one
  write-capable open publishes them, and expose `Graph.view_version` so the state is visible.
- **A restore holds a write lock for the whole file and one large transaction.** This is the
  price of atomicity; document it and recommend a quiet period for large snapshots.
- **Restore memory is O(nodes) for the id map.** Acceptable for v1; a temporary mapping table is
  a future optimization if graphs outgrow memory.
- **A source-valid snapshot can fail against a target with stricter indexes or constraints.**
  The transaction rolls back; the target's declarations are preserved.
- **View name collisions are possible.** Refuse rather than drop; document `graph_*` as a
  reserved namespace.
- **`graph_nodes.labels` depends on aggregate ordering.** Use an explicit inner `ORDER BY` and
  test on the minimum supported SQLite 3.38.
- **Untrusted JSON can carry duplicate keys, NaN, Infinity, integer overflow, invalid UTF-8, or
  deeply nested input.** Strict hooks, codec validation, and line-numbered wrapping cover these;
  the decoder catches decode-time exceptions instead of leaking driver errors.
- **External readers can misread booleans and integers.** Document quoted JSON paths and
  `json_type`, and provide the normalized label view.
- **Exporting to a journal sidecar would create a file SQLite may later treat as a log.** Refuse
  the live database path and its sidecars.
- **Restore pays a savepoint per record.** Correctness first; measure before adding a bulk path.
- **Schema objects are not in the snapshot.** Migrating indexes and constraints is a deliberate
  separate operation.

## Migration Plan

- No `user_version` change. Older builds ignore the views and continue to open the file.
- The first write-capable open after the upgrade publishes the views in one transaction; later
  opens are cheap no-ops.
- Read-only opens before publication keep working; `Graph.view_version` returns `0`.
- Older view versions are replaced on a write-capable open. Newer versions are left untouched so
  an older build cannot downgrade a newer file.
- No data rewrite and no automatic restore. `--replace` is opt-in and atomic.
- Rollback is a library rollback: the views remain in the file but are ignored by older builds,
  and no stored data changes.
