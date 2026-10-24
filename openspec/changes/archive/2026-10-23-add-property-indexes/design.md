# Design

## Context

Properties live in `nodes.props` and `relationships.props` as canonical JSON text, and
the durable specs require that storage form and type-sensitive matching. Property
predicates are assembled in three independent places: the query compiler's predicate
builder and the two repository `find` paths. All three bind the JSON path as a statement
parameter and pair `json_type(...)` with `json_extract(...)`.

SQLite matches an expression index only when the same expression appears literally in the
query. Measured on 200,000 nodes: a bound path costs about 65 ms, the identical predicate
with a literal path and an expression index costs 0.1 ms with a covering-index plan.
`Schema.VERSION` is 1 and there is no migration framework, so anything this change adds
must be additive and version-neutral.

See `proposal.md` for motivation. The behavior contract is in
`specs/graph-indexes/spec.md`.

## Goals / Non-Goals

**Goals:**

- Make selective property filters and relationship-type filters resolve through an index.
- Keep canonical JSON as the single stored representation; let SQLite own index
  maintenance, including rollback.
- Keep index metadata discoverable after reopen with no schema version change and no
  metadata table.
- Make it possible to prove which plan a statement gets.
- Record reproducible before/after numbers.

**Non-Goals:**

- Label-scoped or composite `(label, key)` indexes; the stored model cannot express them
  without a normalized property table.
- Unique constraints, full-text search, vector indexes, automatic index selection, or
  index hints.
- A schema migration framework or a `user_version` bump.
- Changing property equality, ordering, or result shape in any way.

## Decisions

### D1. Expression index over the JSON document, not a property table

Each declared index is a compound, covering expression index over the stored document:

```sql
CREATE INDEX pygrafito_idx_node_<hex> ON nodes (
  json_extract(props, '$."<key>"'),
  json_type(props, '$."<key>"')
);
```

Ordering the value expression first makes equality and range seeks possible; the second
term carries the type guard into the same seek, so booleans, integers, floats, and strings
stay distinct without a post-filter. Relationships get the mirror image.

Alternatives considered:

- **Normalized property table** (`element_id, key, type, value`). More flexible, supports
  label-scoped and unique indexes, but changes the storage contract, doubles write work,
  needs schema version 2 plus a migration path, and introduces dual-write consistency
  risk. Rejected for now; this public API stays valid if it is added later.
- **Per-key generated columns.** Requires one schema change per key, so it cannot be a
  runtime API.

### D2. Inline JSON paths as escaped literals

Every property predicate embeds the path as a SQL string literal: the JSON path is
produced by the existing validated quoting (`$."key"`, with `\` and `"` escaped) and is
then embedded with single quotes doubled. One helper owns that step, and every predicate
builder uses it, so the three call sites cannot drift.

Binding stays for **values** and for labels, types, and ids. Nothing that originated from
a `$name` parameter is ever inlined; only literal keys from the parsed statement or the
Python API, both already validated as non-empty strings.

Alternatives considered: keeping the parameter makes indexes unreachable, which defeats
the change; switching storage to a property table is rejected in D1.

### D3. Index identity encoded in the index name

Indexes are named `pygrafito_idx_<node|rel>_<hex of the UTF-8 key>`. Discovery reads
`PRAGMA index_list` for each table and filters by prefix, then hex-decodes the key. This
needs no metadata table, no schema version change, and no parsing of stored DDL.

Alternatives considered: a metadata table requires schema version 2 plus migration;
parsing `sqlite_master.sql` is brittle against formatting and quoting.

Consequence: index names grow with the key (two hex characters per byte). Acceptable;
SQLite imposes no practical limit. The fixed prefix is reserved for this library.

### D4. Public API shape

```text
Index(kind: IndexKind, key: str)          immutable value, new model type
Graph.create_node_index(key) -> Index
Graph.create_relationship_index(key) -> Index
Graph.drop_index(index: Index) -> None
Graph.indexes() -> tuple[Index, ...]
Graph.explain(text, parameters=None) -> tuple[str, ...]
```

`Index` is frozen so `indexes()` results are snapshots and can be passed back to
`drop_index`. `IndexKind` is an enum (`NODE`, `RELATIONSHIP`) for the same reason
`Direction` exists, rather than string literals. Creating is idempotent; dropping an
absent index raises `NotFoundError`.

`explain` compiles the statement through the normal parse, analyze, and compile stages,
then runs `EXPLAIN QUERY PLAN` without executing it. It returns the `detail` text of each
plan row in order, which is what a caller needs to distinguish "scan" from "index search".
Write statements are compiled, so `explain` can inspect them without side effects.

### D5. Index DDL runs outside caller transactions

Index creation, removal, and statistics refresh execute on the graph's connection but are
rejected with `TransactionError` while an explicit transaction is open on that handle,
matching the existing convenience-write guard. Reason: `ANALYZE` is expensive, and
silently participating in a caller's transaction would make commit cost unpredictable.

### D6. Statistics policy

`ANALYZE` runs after a successful create or drop, which is an explicit administrative
action. `PRAGMA optimize` runs when a file-backed graph closes. Both are best-effort: a
failure to refresh statistics must not fail the index operation or the close, because
statistics affect plan choice only, not correctness.

Without statistics SQLite guesses, and after this change two candidate indexes plus the
label index compete for the same query. `explain` exists so a caller can verify the guess.

### D7. Structural relationship-type index

Bootstrap adds `rel_by_type (rel_type, src, dst)`. It covers a type filter with no bound
endpoint, where today every relationship is read, and its endpoint columns make it
covering for queries that project only ids. The statement is `IF NOT EXISTS`, so existing
files gain it on next open with no version change.

### D8. Benchmark harness as a first-class task, not a test

`benchmarks/` holds a runnable script that builds synthetic themed data, times the
documented scenarios, and prints a table. It is not part of `hatch test` because it is
slow; a tiny smoke test asserts the harness runs. `docs/performance.md` records the
machine, the method, and the numbers quoted in the README.

## Risks / Trade-offs

- **Planner still prefers a scan** (no index intersection in SQLite; a selective label
  plus a non-selective key can favor the label index). → Refresh statistics, keep the
  plan assertions in tests, and expose `explain` so users see reality.
- **List-valued keys may not match the index expression text.** → Verify list equality
  against an indexed key; if the stored array text and the canonical comparison text
  diverge, keep list matching unaccelerated and document it rather than changing equality.
- **Inline escaping is a security boundary.** → One helper, hostile-key corpus (quote,
  double quote, backslash, NUL, SQL-shaped text, unicode), and no parameter values ever
  inlined.
- **Write amplification.** Every declared index adds work per property write. → Measure
  insert and update throughput before and after in the benchmark; document the cost.
- **`ANALYZE` cost on large graphs.** → Only on explicit index operations, plus
  `PRAGMA optimize` on close.
- **First open of an existing large file builds `rel_by_type`.** → One-time cost, recorded
  in docs; no data rewrite.

## Migration Plan

No data migration and no schema version change. Bootstrap adds the structural index
idempotently; declared indexes exist only when a caller creates them. Older builds open
newer files unchanged because they ignore unrecognized indexes and the recorded version
stays 1. Rolling back the package version leaves extra indexes in the file, where they
are harmless and are re-adopted if the newer build runs again.

## Open Questions

- Should scanning filters produce a warning or a suggested index in a future change?
  Deferrable; it adds no contract.
- Should label-scoped indexes arrive with a normalized property table later? Deferrable;
  the API in D4 does not preclude it.
