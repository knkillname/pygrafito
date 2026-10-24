# Design

## Context

See `proposal.md` for motivation and `specs/graph-query-language/spec.md` for the behavior contract.
The current front-end parses one `MATCH` pattern, one optional `WHERE`, and one required `RETURN`
into a flat `Statement` dataclass, analyses it once, and compiles the pattern to indexed SQL. The
executor materializes every matched binding, then filters, projects, aggregates, orders, and
paginates in Python. `Graph.query` opens a deferred read transaction, materializes the result, and
closes it; `Transaction.query` reuses the active transaction and opens nothing.

Storage already exposes the operations writes need: node and relationship create, property set and
remove, label add and remove, and delete with detach. The strict value rules, deletion protection,
and `BEGIN IMMEDIATE` write boundary are implemented and tested there. The query layer must reuse
them, not reimplement them.

Constraints that shape the approach:

- One `sqlite3.Connection` per graph, `check_same_thread=True`, one writer.
- Only `Graph` and `Transaction` may call into the query package; the query package may import
  `model`, `storage`, and the rest of `engine`, never the reverse.
- No module-level functions; behavior lives in classes.
- `Graph.query` raises `TransactionError` while an explicit transaction is active, which keeps a
  single place able to open a write transaction.

## Goals / Non-Goals

**Goals:**

- Represent a statement as an ordered clause sequence that can grow with later changes.
- Execute read and write clauses over one binding pipeline without forking the read path.
- Keep every mutation rule delegated to the storage layer.
- Make write atomicity observable: one statement, one transaction, all or nothing.
- Keep read statements byte-for-byte compatible in behavior and result shape.

**Non-Goals:**

- `MERGE`, conditional `ON CREATE` / `ON MATCH` updates, or upsert semantics.
- `WITH` pipelines, `UNWIND`, `OPTIONAL MATCH`, subqueries, or multiple patterns.
- Streaming results, early `LIMIT` termination, or pushdown of mutation stages into SQL.
- Property indexes, constraint enforcement, or bulk import.
- Changing the object API or the schema.

## Decisions

### D1: `Statement` becomes an ordered clause sequence

```
Statement
  clauses: tuple[Clause, ...]

Clause = Match | Create | Set | Remove | Delete | Return

Match(pattern, where)            # where stays attached to the match it filters
Create(patterns)                 # one or more path patterns
Set(assignments, labels)         # property assignments and label additions
Remove(properties, labels)
Delete(detach)                   # detach distinguishes DELETE from DETACH DELETE
Return(items, distinct, order_by, skip, limit)
```

`where`, `distinct`, `order_by`, `skip`, and `limit` move from the statement onto the clause they
belong to. `Delete` targets the currently bound variables named in the clause; the parser keeps the
variable list so the clause is self-describing.

Alternatives considered:

- Keep the flat `Statement` and add optional write fields. Rejected: clause order is part of the
  contract, and the field combination grows with every clause.
- One statement class per shape (`ReadStatement`, `CreateStatement`, ...). Rejected: it duplicates
  semantic, plan, and executor wiring and makes mixed statements awkward.
- A generic clause list of `(kind, payload)` tuples. Rejected: it loses static typing, which the
  project enforces with Pyrefly strict.

### D2: Scope tracking in the semantic analyzer

The analyzer walks clauses in order with one scope map from variable name to kind (`node`,
`relationship`, `path`, `scalar`). A node pattern in `MATCH` or `CREATE` binds a node variable; a
relationship pattern binds a relationship variable; `RETURN` items bind nothing. New rules:

- `CREATE` node patterns introduce new variables; their property maps stay literal-or-parameter.
- `CREATE` relationship endpoints must already exist in scope, because a relationship cannot
  invent its endpoints.
- `SET` and `REMOVE` targets must be in scope and must be a node or relationship.
- `DELETE` targets must be in scope and must be node or relationship values.
- `RETURN` may reference any variable bound before it, including variables introduced by `CREATE`.

`Analysis` gains `is_write` and an empty `columns` tuple when the statement has no `RETURN`. An
`Analysis` with no `columns` and no write clause is impossible: a read statement requires
`RETURN`.

### D3: One binding pipeline, mutations applied between stages

```
planned stages
  MATCH  -> bindings: tuple[Binding, ...]
  FILTER -> bindings
  CREATE -> bindings extended with newly created elements
  SET    -> bindings refreshed in place
  REMOVE -> bindings refreshed in place
  DELETE -> bindings keep the pre-deletion snapshot
  PROJECT -> rows
  AGGREGATE / DISTINCT / ORDER / SKIP / LIMIT -> rows
```

`Binding` stays the existing `dict[str, QueryValue]`. A write clause never changes the number of
rows except `CREATE`, which appends one binding per input row and per created pattern. This keeps
`RETURN` semantics on top of writes identical to reads.

**Snapshot refresh.** Bindings hold immutable `Node` and `Relationship` snapshots. After a `SET` or
`REMOVE` clause, the executor reloads the affected elements by id and replaces them in every
binding that references them, so a later clause and `RETURN` observe the new state. After
`DELETE`, bindings keep the snapshot captured before deletion, so `RETURN` can still project a
deleted element; a later **write** clause that targets a deleted element raises a query execution
error.

Alternative considered: persist bindings as ids and resolve snapshots lazily at projection time.
Rejected for this change: the read path already materializes eagerly, and mixing lazy resolution
into only the write path would create two snapshot rules.

### D4: Per-clause cardinality with deduplication

Each write clause converts its input bindings into an ordered, deduplicated operation list keyed by
entity id:

```
SET      for each binding row, compute (id, property, value) or (id, label)
         keep the LAST computed operation per (id, property)
         keep the union of labels per id
         apply every remaining operation once, in first-seen id order

REMOVE   same shape, with last-wins for properties and set union for labels

DELETE   collect ids in first-seen order, detach where requested,
         delete each id once, relationship targets before node targets
```

This is what makes `MATCH (a)-[*1..3]->(b) DETACH DELETE b` safe once variable-length paths land:
duplicate rows collapse to one deletion instead of a `NotFoundError` on the second. It also means a
node matched by several rows ends with the value computed from the last row, which the cardinality
requirement states explicitly.

Alternative considered: raise on a repeated entity. Rejected: it makes the natural delete-from-a-
match statement unusable and forces callers to rewrite patterns to avoid duplicates they did not
ask for.

### D5: Transaction boundary per statement kind

```
Graph.query(statement)
  read  -> BEGIN (deferred) ... COMMIT  (unchanged)
  write -> BEGIN IMMEDIATE ... COMMIT, ROLLBACK on any exception

Transaction.query(statement)
  read or write -> no boundary; the active transaction already holds the write lock

Graph.query while an explicit transaction is active -> TransactionError (unchanged)
```

Classification happens once in analysis, before any SQL runs, so a read statement can never
accidentally acquire the write lock. Rollback runs in a `finally` block; a failed rollback is
logged into the raised error path but never masks the original query error.

Alternative considered: reuse the existing `Transaction` context manager from inside `Graph.query`.
Rejected: `Transaction` re-enters the graph's own guard and would report the internal transaction as
a caller conflict.

### D6: Storage calls and error mapping

The executor calls `NodeRepository`, `RelationshipRepository`, and `PropertyCodec` directly, using
the connection it already holds. It does not call `Graph.add_node` and friends, which would
re-enter the convenience-write guard and could open a second transaction.

Errors map at one boundary:

```
ValidationError        -> QueryExecutionError (invalid stored value, label, or type)
NotFoundError          -> QueryExecutionError (element vanished during the statement)
ConnectedNodeError     -> QueryExecutionError (DELETE without detach)
sqlite3.Error          -> QueryExecutionError
```

`QueryError` subclasses are never double-wrapped. A source position is attached when the failure
originates from a clause or expression; storage-only failures carry no position, which the error
hierarchy already allows.

### D7: Result shape and mutation summary

`QueryResult` gains an optional third field:

```python
@dataclasses.dataclass(frozen=True, slots=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    summary: MutationSummary = MutationSummary()
```

```python
@dataclasses.dataclass(frozen=True, slots=True)
class MutationSummary:
    created_nodes: int = 0
    created_relationships: int = 0
    deleted_nodes: int = 0
    deleted_relationships: int = 0
    properties_set: int = 0
    properties_removed: int = 0
    labels_added: int = 0
    labels_removed: int = 0
```

A default-valued third field keeps existing keyword and positional construction of `QueryResult`
working; no caller has to change. Counts are applied operations after deduplication, so they
describe what happened, not how many rows requested it. `MutationSummary` is exported from the
package root.

Alternatives considered: a separate `WriteResult` type (rejected: callers would branch on result
type for every statement); returning a bare summary for writes without `RETURN` (rejected: two
return shapes for one entry point).

### D8: Compiler and plan changes stay additive for reads

`Compiler` continues to compile one `Match` clause into `CompiledMatch`. The change adds a clause
walker on top of it; the SQL it emits for an existing read statement is unchanged, so the read
conformance suite doubles as a regression guard.

`PlanOperator` gains `CREATE`, `SET`, `REMOVE`, and `DELETE` members, built by `PlanBuilder` from
the clause sequence. The pipeline is still a linear operator list, not a graph, because clause
order is already linear and no clause reorders rows.

### D9: Documentation and spec bookkeeping

- `docs/query-language.md` loses the read-only framing, gains a statement-shape section, a clause
  reference, cardinality rules, the summary, and the transaction boundary.
- README gains write examples; `tests/test_readme.py` executes them.
- `CHANGELOG.md` gains an `[Unreleased]` entry in the same task group as the code.
- The durable `graph-query-language` spec still describes the capability as read-only in its
  `Purpose` line. That line must be corrected when the change is archived or synced; the delta does
  not carry a `Purpose` section for an existing capability.

### D10: Testing strategy

- Parser: clause sequences, optional `MATCH`/`RETURN`, `RETURN` before a write clause rejected,
  write clause before `MATCH` rejected, `DETACH DELETE` recognized as one clause.
- Semantic: scope rules for every clause, unbound targets, relationship endpoints in `CREATE`,
  write classification, empty columns without `RETURN`.
- Executor: `CREATE` per row, `SET` from expressions, null removal, label add and remove, delete
  protections, deduplication with last-row-wins, snapshot refresh before `RETURN`.
- Transaction: implicit commit, rollback on clause failure, no transaction left open, transaction
  visibility and rollback through `Transaction.query`, active-transaction guard unchanged.
- Value rules: invalid parameter values rejected with nothing committed.
- Fixtures use TRON names per the project convention; cardinality cases cover diamond, cycle,
  parallel relationships, and self-loop.
- The three existing rejection tests (`test_parser.py:294-300`, `test_semantic.py:340-345`) become
  acceptance tests for the same statements.

## Risks / Trade-offs

- **Stale snapshots after mutation** -> Refresh affected bindings after every `SET`/`REMOVE` clause
  and test that `RETURN` observes the new value.
- **Deduplication changes what a caller expects from row-wise writes** -> State the rule in the
  spec and the language reference, and test last-row-wins for properties.
- **Deleted elements stay reachable through bindings** -> Keep the pre-deletion snapshot for
  `RETURN`, reject later write clauses that target a deleted element, and test both paths.
- **Two transaction code paths** -> Classification happens before SQL, and both paths share the
  same commit/rollback helper; tests assert no transaction is left open on failure.
- **`CREATE` from an unselective `MATCH` duplicates edges** -> Document "one row, one creation" and
  point at `MERGE` as the deferred answer; the conformance suite includes the case.
- **No property index** -> Writes derived from property filters scan candidates; acceptable at the
  stated target size and unchanged from the read path's cost profile.
- **Summary counts are applied operations, not rows** -> Document the definition next to the field
  and assert it in tests, including the deduplicated case.
- **One large executor module** -> Mutation stages live in their own class behind the executor, not
  as new methods on `QueryExecutor`.

## Migration Plan

No schema change, no data migration, and no version bump of `PRAGMA user_version`. Existing
databases open unchanged. Rollback is a code and documentation revert: dropping the write clauses
restores the read-only rejection, and no stored data was transformed. Behaviorally, statements that
previously raised a read-only error now execute; callers that depended on that rejection must
validate untrusted statements themselves, as recorded in the removed requirement's migration note.

## Open Questions

- Whether `SET` should accept whole-map assignment (`SET n = {...}`) and merge assignment
  (`SET n += {...}`) depends on map literals, which the dialect does not support yet. That is a
  later expression-language change, not a write-clause change; the clause grammar reserves the
  form without accepting it.
