# Design

## Context

See `proposal.md` for motivation. The behaviour contract is in
`specs/property-graph/spec.md` and `specs/graph-constraints/spec.md`.

The codebase already has the shape this design needs:

- `Database` owns one `sqlite3.Connection` with `check_same_thread=True`, sets
  `busy_timeout = 5000`, and enables WAL only for file-backed writable handles.
- `Schema.bootstrap` runs its DDL in autocommit, reads `PRAGMA user_version`, then writes it.
- Write statements already run under `BEGIN IMMEDIATE`; `Graph.query` already wraps a read
  statement in `BEGIN`/`COMMIT`.
- `IndexRegistry` discovers declared indexes from `PRAGMA index_list` by decoding a hex name,
  with no metadata table and no schema version change.
- Properties are canonical JSON text, and every predicate pairs `json_type(...)` with
  `json_extract(...)`, so `true`, `1`, `1.0`, and `"1"` are already distinct.

The archived index change deferred label-scoped uniqueness, on the grounds that the stored model
cannot express it without a normalized property table. That reasoning holds for *indexes* that
must be seekable across a label join; it does not hold for *uniqueness*, as D1 shows.

Measurements below were taken on the development runtime (SQLite 3.53.4) with six competing
processes over twenty-five fresh database files. The minimum supported runtime is 3.38, so
nothing in the design depends on behaviour newer than that.

## Goals / Non-Goals

**Goals:**

- Keep the file's guarantees enforced by SQLite itself, so a writer that predates the feature
  cannot break them.
- Add no schema version bump, no metadata catalog, and no migration.
- Make every failure introduced by the change a domain error with an actionable payload.
- Make the concurrency promise measurable: one test per sentence of the contract.

**Non-Goals:**

- A normalized property table, a constraint catalog, or a migration framework.
- Commit-time (deferred) uniqueness validation.
- A connection pool, thread-local connections, or a shared handle across threads.
- A relationship or node key constraint made of several properties.
- Query-language DDL for constraints; the dialect still has no DDL.

## Decisions

### D1. Constraints are self-describing DDL, in two shapes

There is no catalog table and no `user_version` bump. Every constraint is one or more objects
in `sqlite_master` whose *DDL text* names the label or type and the key, so the invariant
travels with the file and binds any writer, including an older build and an external SQLite
client.

```sql
-- relationship constraint: (type, key) is expressible in one table
CREATE UNIQUE INDEX pygrafito_uniq_rel_<hex(type)>_<hex(key)>
  ON relationships (json_extract(props, '$."<key>"'), json_type(props, '$."<key>"'))
  WHERE rel_type = '<type>';

-- node constraint: (label, key) spans two tables, so triggers enforce it
CREATE INDEX pygrafito_uniq_node_<hex(label)>_<hex(key)>_idx
  ON nodes (json_extract(props, '$."<key>"'), json_type(props, '$."<key>"'));
CREATE TRIGGER pygrafito_uniq_node_<...>_props
  BEFORE UPDATE OF props ON nodes
  WHEN EXISTS (SELECT 1 FROM node_labels WHERE node_id = NEW.id AND label = '<label>')
   AND json_extract(NEW.props, '$."<key>"') IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'pygrafito:constraint:node:<hex>') WHERE EXISTS (...);
END;
CREATE TRIGGER pygrafito_uniq_node_<...>_labels
  AFTER INSERT ON node_labels
  WHEN NEW.label = '<label>' AND json_extract((SELECT props FROM nodes WHERE id = NEW.node_id), ...)
       IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'pygrafito:constraint:node:<hex>') WHERE EXISTS (...);
END;
```

Verified on the development runtime: a single unique index on `(json_extract, json_type)` stores
`true`, `1`, `1.0`, and `"1"` side by side, rejects a second `true` with
`UNIQUE constraint failed: index '<name>'`, and treats an absent property as NULL, so any number
of elements may omit it. The trigger pair behaves the same way for a label: the first `User` with
an address is accepted, a second node gains the label only when its value is free, and a
properties update that duplicates a value is rejected. Both shapes report their own identity, and
the node shape's message is our own token rather than SQLite's text.

Two details for the implementation:

- `NodeRepository.create` inserts the node row before its labels, so the label trigger must be
  the `AFTER INSERT ON node_labels` one. A test must pin that ordering, because moving the label
  insert before the node insert would silently hide violations.
- The trigger body repeats its `EXISTS` subquery twice (once in the `WHEN` guard, once in the
  `WHERE`). Keeping the guard first means a node without the label or without the property
  never runs the subquery.

Alternatives considered:

- **Catalog table plus a maintained key table.** Supports deferred validation and richer
  metadata, but every mutation path must remember to resynchronise, the uniqueness guarantee
  depends on that code, external writers are unbound, and it requires schema version 2 with a
  migration. Rejected.
- **Validation only in Python before each write.** No DDL, but every write path — including
  future ones — must remember, and an external writer can bypass it.
- **A `unique` flag on the declared index.** Attractive because one concept covers acceleration
  and invariants, but a node index cannot see `node_labels`, so the flag would not cover the one
  case that matters.

### D2. Scope is always one label or one type

There is no element-kind-wide form. Labels and types are the type system, so a constraint that
applies to every node sharing a key would not describe a property graph. This also keeps the API
symmetric with the index API: two explicit methods instead of one with an optional scope.

The asymmetry in D1 is a direct consequence of the storage model, not a design preference:
`rel_type` is a column, a label is a row in `node_labels`. The relationship form therefore costs
one index and the node form costs an index plus two triggers.

### D3. The unique key is the value/type pair, and the type predicate is the same one used by reads

The index key and the trigger comparison both use `(json_extract(...), json_type(...))`.
`json_type` is what separates `true` from `1` and `1` from `1.0`; `json_extract` alone would
conflate them. This is the same pairing the read paths already use, so a constraint cannot
disagree with a filter.

List values are compared as their canonical JSON text, so order matters, matching the equality
rule already in `graph-indexes`. Absent properties are NULL in the index and excluded by the
trigger guard, so absence is never a value.

### D4. Enforcement is immediate

SQLite refuses a duplicate at the statement that produces it. The alternative — a commit-time
check — would allow a transaction to pass through a transient duplicate, which makes swaps work,
but it requires the catalog of D1's rejected alternative, and it gives up enforcement for writers
outside the library.

Consequence to document rather than hide: assigning two elements each other's values in one
statement fails. A caller uses a temporary value or two statements. The spec states this, and a
scenario pins it.

### D5. Declaring is a write transaction

Validation and DDL creation run inside one `BEGIN IMMEDIATE`. Otherwise a concurrent writer can
insert a duplicate between the validation `SELECT` and the trigger that would have caught it,
producing a constraint that reports success over violating data. Declaring also refreshes planner
statistics, like index creation.

Declaration is idempotent, matching `create_node_index`. Removal drops every object that carries
the constraint's prefix and raises `NotFoundError` when none is present.

### D6. First open retries the journal switch, then bootstraps transactionally

Two independent fixes, because the measurements separate them:

| harness: 150 opens, 6 processes, fresh file | failures |
|---|---|
| `journal_mode = WAL` with no retry | 32-43 |
| bootstrap DDL + version, autocommit, after WAL was already on | 0 |
| bootstrap DDL + version inside `BEGIN IMMEDIATE`, WAL already on | 0 |
| journal switch retried 3 times with 10/20 ms backoff | 0 |

The busy handler does not cover `PRAGMA journal_mode = WAL`; it returns `database is locked`
immediately. So the switch gets a bounded retry, and the bootstrap gets `BEGIN IMMEDIATE` with a
version re-read inside it. The retry budget is internal and fixed — not a knob — because a caller
must not have to configure correct behaviour.

A read-only handle does not run the transactional bootstrap: it cannot take a write lock, and its
existing tables make the `CREATE ... IF NOT EXISTS` statements no-ops.

### D7. One snapshot per public read call

`Graph.query` already starts a deferred transaction for a read. `node`, `find_nodes`,
`traverse`, `shortest_path`, and `paths` read several statements without one, which a second
handle can interleave.

The fix wraps the *capture*, not the iteration:

- `node` and `find_*` fetch their rows and then their labels; both inside one `BEGIN`/`COMMIT`.
- `traverse` and `paths` materialise an `AdjacencySnapshot` before returning a lazy iterator, so
  the transaction closes before the iterator escapes and an abandoned iterator cannot leak one.
- `shortest_path` materialises its result, so the whole evaluation is one snapshot.
- Inside an explicit transaction, the helper reuses it instead of starting a second one; that
  preserves today's behaviour where a convenience read inside `with graph.transaction()` sees
  uncommitted writes.

A long `shortest_path` holds a read snapshot for the duration of the search, which delays WAL
checkpointing but never blocks a writer. Acceptable for the guarantee it buys.

### D8. WAL is preferred, verified, and reported

`PRAGMA journal_mode = WAL` returns the mode it ended in; the current code ignores it. The design
reads the result back and exposes it. On platforms where WAL is unavailable the graph keeps
working in the rollback journal: **consistency is never lost, only read/write concurrency**.

Measured: a second process opens the file read-only while a writer holds it and sees each new
commit; a write through that handle is refused. After the last handle closes, the log and
shared-memory sidecars are gone and the file opens read-only from read-only media, which is what
makes "close cleanly, then copy" true.

### D9. The schema version tracks layout, not features

`user_version` changes only when the stored layout becomes incompatible. Additive objects never
move it. An older build therefore opens a file that contains constraints, and — because SQLite
enforces them — cannot violate them; it merely reports a raw integrity error instead of a domain
error. That safety is what makes the bump unnecessary.

### D10. Opening never adopts a foreign database

The read-only path already refuses a non-graph file, but only because it cannot write. A writable
open currently adds the graph schema to any SQLite file, including one with unrelated tables.
The rule: refuse when `user_version = 0`, none of the graph tables is present, and at least one
unrelated table is. Views never count. A fresh file, an empty file, and a graph file that gained
an external table all open normally.

Both paths raise `UnsupportedSqliteError`; its docstring widens from "the runtime cannot provide
the features" to "the runtime or the file cannot provide what the graph requires", so one error
covers both and the existing read-only test keeps its expectation.

### D11. Public surface and error model

```text
Constraint(kind, scope, key)                     frozen; scope is a label or a relationship type
ElementKind                                      NODE | RELATIONSHIP; IndexKind stays as an alias

Graph.create_node_uniqueness_constraint(label, key) -> Constraint
Graph.create_relationship_uniqueness_constraint(rel_type, key) -> Constraint
Graph.constraints() -> tuple[Constraint, ...]
Graph.drop_constraint(constraint) -> None
Graph.journal_mode -> str
Graph.open(..., busy_timeout: int | None = None)

ConstraintViolationError(PygrafitoError)         kind, scope, key, value, existing
LockTimeoutError(PygrafitoError)                 a lock wait exhausted the busy timeout
HandleAffinityError(PygrafitoError)              a handle used from a thread that does not own it
```

`ConstraintViolationError` is a data-state error like `ConnectedNodeError`, not a
`ValidationError`. `LockTimeoutError` and `HandleAffinityError` stay flat rather than sharing a
base, because their remedies differ: one is retried, the other is a programming mistake.

`ElementKind` is the honest name for the enum both `Index` and `Constraint` use. Keeping
`IndexKind` exported as an alias means nothing breaks.

The support index belongs to its node constraint, is not reported by `indexes()`, and is dropped
with it. A relationship constraint's unique index doubles as a covering index, so declaring a
plain index on the same key is redundant.

Error translation is conservative: a raised `UNIQUE constraint failed: index '<name>'` counts as
a violation only when the name decodes to a constraint this registry would have created, and the
`pygrafito:constraint:` token counts only when its payload decodes. A foreign-key failure from a
delete therefore never masquerades as uniqueness. On the error path, one diagnostic `SELECT`
finds the existing holder and fills `existing`; when the duplicate was created and rolled back by
the same statement, nothing survives to name and `existing` is `None`.

The violation message is a static token. The development runtime accepts an expression as the
`RAISE` argument, but the documented grammar allows a string literal, so relying on it would
break on older runtimes for no benefit.

### D12. Object naming

Every constraint object is named `pygrafito_uniq_<node|rel>_<hex(scope)>_<hex(key)>`, with a
suffix for the several node objects. The `pygrafito_uniq_` prefix keeps constraint objects out of
`IndexRegistry.all()`, whose prefixes stay as they are. The name is opaque on purpose; the DDL
text carries the readable label, type, and key.

## Risks / Trade-offs

- [A value swap needs a temporary value] → stated in the spec and covered by a scenario, so it is
  a documented consequence rather than a surprise.
- [A trigger is invisible in the Python source] → `Graph.constraints()` and the shell read the
  DDL, and one test declares, closes, reopens, and asserts enforcement without any Python state.
- [An external tool can drop the support index] → the constraint stays correct because the
  trigger enforces it, only slower; the DDL text still names the invariant.
- [Per-row trigger cost on bulk loads] → the support index turns the check into a seek; the
  alternative costs correctness.
- [Older builds report a raw integrity error] → safe, not silent; the changelog says so.
- [Multiprocess tests are slow and can flake] → use the `fork` context with plain top-level
  helpers, generous timeouts, and a single assertion per scenario; keep them in one file so the
  suite's slow section is easy to run alone.
- [A read snapshot can delay checkpointing] → bounded by the call; no writer is ever blocked.
- [Refusing a foreign file is a behaviour change] → changelog entry and a test that asserts the
  foreign tables and version are untouched.
- [A dynamic `RAISE` expression works today but is undocumented] → deliberately unused.

## Migration Plan

None. The schema version does not move, existing files open unchanged, and constraint DDL is
additive. Removing every constraint returns a file to the previous shape. An older build can
still read a file that contains constraints, and remains bound by them.

## Open Questions

- Whether `check_integrity` should report a constraint whose support index was removed by an
  external tool. Deferrable: the constraint remains correct, and the answer does not change the
  specs or the task order.
