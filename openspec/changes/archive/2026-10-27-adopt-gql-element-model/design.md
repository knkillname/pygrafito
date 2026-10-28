# Design

## Context

See `proposal.md` for motivation and the delta specs for the behavioral contract.

The current store is schema version 1: `relationships(id, src, dst, rel_type, props)` with
three structural indexes keyed by `rel_type`, directed edges only, and `INTEGER PRIMARY KEY`
ids that SQLite may reuse after deletion. The public `Relationship` snapshot exposes a single
`type`; `Graph.add_relationship` and `Graph.find_relationships` take that type. The JSONL
snapshot is version 1 with a `type` field, and the read-only views are version 1 with a `type`
column. The current query dialect is Cypher-flavored and is being replaced by GQL in a later
change; this change keeps it working as a transitional subset.

Constraints that shape the approach:

- Runtime standard library only; SQLite 3.38 or newer.
- One connection per graph, WAL for files, `BEGIN IMMEDIATE` for writes.
- Strict property values; no null storage; JSON text properties with quoted paths.
- Pre-1.0, no backwards compatibility: version 1 databases and snapshots are refused.
- Docs under `docs/` must be updated and `hatch run docs:build` must pass in the apply run.

## Goals / Non-Goals

**Goals:**

- Persist the GQL element model: label sets on nodes and edges, directed and undirected
  edges, stable element identity.
- Keep every existing behavior that is not part of the element model, including strict
  values, transactions, snapshots, indexes, constraints, and the shell.
- Refuse schema version 1 databases and version 1 JSONL snapshots with a clear error.
- Keep the current query dialect coherent with the new model as a transitional subset.
- Make the storage and API shape the target for the later GQL query-core rewrite.

**Non-Goals:**

- The GQL grammar, parser, AST, planner, and executor rewrite.
- Temporal values, `POINT`, `VECTOR`, records as stored properties, closed graph types, the
  catalog, sessions, procedures, and in-language transactions.
- GQL path modes (`WALK`, `SIMPLE`, `ACYCLIC`), path search (`ANY SHORTEST`), quantified
  path groups, and the final GQL edge-direction matching matrix.
- A `dialect="cypher"` compatibility layer.
- In-place migration of version 1 databases or version 1 snapshots.
- Multi-label or undirected edge creation through the transitional query dialect; the
  Python API and snapshot restore cover the full model.

## Decisions

### Label sets live in a join table

`relationship_labels(relationship_id, label)` mirrors `node_labels`, with a primary key on
`(relationship_id, label)`, `ON DELETE CASCADE`, and an index on `(label, relationship_id)`.
An edge may have zero labels. Lookup by label uses conjunction (all specified labels),
matching node lookup; traversal label filters use disjunction (any listed label), matching the
old allowed-type traversal.

Alternatives considered:

- **JSON array in `relationships.props` or a separate column.** Simpler to write, but
  filtering by label needs `json_each`, the planner cannot use a normal B-tree, and label
  uniqueness/maintenance is awkward. Rejected.
- **A single "primary label" plus an optional set.** Keeps `rel_type` for old queries, but
  creates two sources of truth and a non-GQL distinction. Rejected.

### Direction is a stored flag, endpoints are storage slots

`relationships` gains `directed INTEGER NOT NULL DEFAULT 1 CHECK (directed IN (0, 1))`.
`src` and `dst` remain the two endpoint columns. For a directed edge they are start and end;
for an undirected edge they are only endpoint slots and have no source/destination meaning.
Endpoint indexes remain `(src, dst)` and `(dst, src)`, so both endpoints are equally
searchable.

Alternatives considered:

- **Two directed rows for one undirected edge.** Changes identity, multiplicity, and
  `ELEMENT_ID`, and makes deletion and constraint enforcement ambiguous. Rejected.
- **A separate `edge_endpoints` table.** Models undirected edges naturally but adds a join
  to every traversal and complicates indexes. Rejected for a single-file embedded store.
- **Canonicalizing undirected endpoints (`src <= dst`).** Unnecessary because both endpoint
  indexes are maintained and no semantics depend on order. Rejected to preserve insertion
  order in snapshots and exports.

### Stable ids use `INTEGER PRIMARY KEY AUTOINCREMENT`

SQLite's `AUTOINCREMENT` prevents reuse of a deleted maximum id and leaves gaps after rolled
back inserts. The version 2 schema declares it from the start; no migration rebuild is
provided.

Alternatives considered:

- **Keep id reuse.** Violates GQL element identity and can make a stale id alias a new
  element. Rejected.
- **UUID or string element ids.** Larger, changes the snapshot and API types, and adds no
  value for a single-file store. Rejected.
- **An application-managed `next_id` counter in `graph_meta`.** Adds a hidden invariant and
  does not protect against external inserts. Rejected.

`AUTOINCREMENT` creates `sqlite_sequence`. The foreign-database check already ignores
`sqlite_%` tables, and backup/export/integrity are unaffected.

### Schema version 2 is a clean break

Version 2 is a fresh layout. A database that records version 1 is refused on both
read-write and read-only opens with an `UnsupportedSqliteError` that names the current
version; the file is not modified. No table rebuild, data copy, or compatibility view is
provided. An uninitialized database (version 0) is bootstrapped to version 2.

This is acceptable because the project is pre-1.0 and the published release is days old. It
also keeps the change smaller and removes the riskiest part of an otherwise mechanical
storage rewrite.

Alternatives considered:

- **In-place migration with a table rebuild.** Preserves a handful of files at the cost of a
  foreign-key-off rebuild, index/trigger recreation, and a new failure mode. Rejected.
- **Change the layout without bumping the version.** A version 1 file would open silently
  and fail at read time, or worse, be written with the wrong shape. Rejected.
- **`ALTER TABLE ADD COLUMN directed` plus a label-table backfill and leaving `rel_type`.**
  Leaves a non-GQL column and cannot add `AUTOINCREMENT`. Rejected.

### Relationship label mutation is part of the graph and transaction API

`Graph.add_labels` and `Graph.remove_labels` are generalized from `Node | int` to
`Node | Relationship | int`. They return the updated `Node` or `Relationship` snapshot. The
`Transaction` methods follow. This matches GQL's `SET r:Label` and `REMOVE r:Label` and avoids
two parallel API families.

Alternatives considered:

- **Separate `add_relationship_labels` / `remove_relationship_labels` methods.** Explicit,
  but duplicates validation, snapshots, and docs. Rejected.
- **Keep labels node-only until the GQL rewrite.** Contradicts the full element model and
  leaves the query dialect unable to express GQL's label mutation. Rejected.

### Traversal direction and the transitional query direction differ

The traversal API is a walk-direction API:

- `OUTGOING` follows directed edges from the current node and undirected edges incident to it.
- `INCOMING` follows directed edges into the current node and undirected edges incident to it.
- `BOTH` follows every incident edge.

The transitional query dialect is a storage-direction constraint:

- `-->` follows directed edges whose `src` is the current node.
- `<--` follows directed edges whose `dst` is the current node.
- `--` follows every incident edge, including undirected edges.
- An undirected edge does not match `-->` or `<--`.

This keeps the query dialect close to GQL's `-[e]->` versus `~[e]~` distinction while the
dialect has only three direction forms. The final GQL direction matrix belongs to the query
core; the transitional rule must not be treated as the GQL rule.

Alternatives considered:

- **Make `-->` include undirected edges to match the traversal API.** Convenient, but it
  blurs the distinction the GQL core will need. Rejected.
- **Make `--` create undirected edges.** Ambiguous in a Cypher-shaped `CREATE` and would
  change existing behavior. Rejected; undirected creation stays in the Python API until the
  GQL core.

### The snapshot format becomes version 2 only

Relationship records carry a `labels` array and a `directed` boolean. Node records are
unchanged. Export writes version 2. Restore rejects any other header version with an error
that names the supported version.

Alternatives considered:

- **A version 1 reader.** Small, but the project is explicitly dropping backwards
  compatibility before 1.0 and the reader would add a second code path to maintain. Rejected.
- **Keep the `type` field and add `labels`.** Two representations of the same fact and
  ambiguous when they disagree. Rejected.

Export sorts both node and relationship labels, so repeated exports remain byte-identical.
The restore remapping rules are unchanged: nodes receive new ids, relationship ids are not
preserved, and endpoints are remapped.

### Views move to version 2

`graph_relationships` exposes `labels` as a JSON array and `directed` as 0/1; the `type`
column is removed. `graph_meta` reports view version 2. A write-capable open replaces views
from an older version; a version 1 database is refused before view publication. External
readers must change their queries; the view version is the signal.

### Constraints scope by one label

A relationship uniqueness constraint stores the label in its existing `scope` field and
applies to every edge carrying that label, including edges with other labels. A label
addition or removal is a write that triggers immediate enforcement, exactly as a node label
addition does. The constraint remains a documented extension, not GQL.

Alternatives considered:

- **Scope by a label set (all labels).** More expressive, but the constraint model has no
  expression language for label sets and the standard uses graph types instead. Deferred.

### Indexes: labels are structural, properties are orthogonal

The structural relationship indexes become:

```sql
CREATE INDEX rel_by_src ON relationships (src, dst);
CREATE INDEX rel_by_dst ON relationships (dst, src);
CREATE INDEX relationship_labels_by_label ON relationship_labels (label, relationship_id);
```

Declared property indexes keep their key-scoped shape. A relationship property index covers
every edge that stores the key, regardless of labels or direction; label and direction
filters narrow the candidate set before or after the property comparison. The planner joins
`relationship_labels` for label filters.

Alternatives considered:

- **Keep `rel_by_type` as `rel_by_label` on `relationships`.** Requires a single label column.
  Rejected.
- **Include labels in the endpoint indexes.** A composite index over a multi-valued column
  is not possible without a join table. Rejected.

### Import keeps its statement-driven shape

`Graph.import_rows` and `Graph.import_file` continue to bind rows to the current dialect's
write statement. That dialect creates single-label directed edges, so imports cannot create
multi-label or undirected edges in this change. The full model is available through the Python
API and `restore_jsonl`. The GQL query core will add `INSERT` label expressions and
undirected patterns; import then inherits them without a format change.

## Risks / Trade-offs

- **[Version 1 files cannot be opened after this change]** → This is a deliberate pre-1.0
  break. Refuse with a clear error that names the current version, document the break in the
  embedding guide and changelog, and advise exporting with 0.8 first if a file matters.
- **[`AUTOINCREMENT` adds `sqlite_sequence`]** → Excluded from the foreign-database check by
  the existing `sqlite_%` filter; backup and export are unaffected. Add a test that a fresh
  version 2 file passes the foreign-database and integrity checks.
- **[Label joins slow relationship filters]** → Keep the label index and both endpoint
  indexes, benchmark the common patterns, and do not add a label filter to a plan that can
  use a more selective property index. Document the change in the performance page.
- **[API break is wide]** → Pre-1.0, no deprecation layer. Update every test, doc example, and
  README snippet in the same change; add a breaking-change entry to `CHANGELOG.md`.
- **[Transitional direction rules could be mistaken for GQL]** → Mark them "transitional" in
  the reference page and keep the final direction matrix for the GQL query core. Tests for the
  transitional rule live in the dialect suite, not the traversal suite.
- **[Snapshot version 2 is a hard break]** → Refuse another version with an error that names
  the supported version; document the change in the snapshot reference and changelog.
- **[Stable ids change a documented behavior]** → New databases allocate ids monotonically
  from the start; tests cover delete-then-create and a fresh-file reopen.
- **[Undirected edges complicate deletion and constraint scope]** → One row per edge keeps
  relationship identity; `ON DELETE RESTRICT` on both endpoints keeps deletion rules; tests
  cover self-loops, parallel edges, detach, and constraints on multi-label edges.
- **[Temporal values will need another snapshot format change]** → This is an accepted
  trade-off for keeping this change reviewable. The GQL temporal change must bump the snapshot
  version or use additive tagged values; decide there.

## Rollout Plan

1. Land the schema and storage changes; every fresh graph uses version 2.
2. Add tests that a version 1 database is refused on read-write and read-only opens, and that
   a version 1 snapshot is refused with a version error.
3. Switch the public API and the transitional query dialect; update tests and docs together.
4. Update snapshots and views; verify a fresh export/restore round-trip.
5. Release as a pre-1.0 minor with a breaking-change note. Rollback is reinstalling 0.8; a
   version 2 file is not readable by 0.8. A user who needs an existing 0.8 file can export it
   with 0.8 before upgrading, but no in-place conversion is provided.

## Open Questions

- The final GQL edge-direction matching matrix and path-mode defaults are intentionally
  deferred to the GQL query-core change. The transitional rules above are not a substitute.
- Whether imported CSV/JSONL should grow explicit `labels` and `directed` columns is deferred;
  the statement-driven importer can stay single-label until the GQL query core lands.
