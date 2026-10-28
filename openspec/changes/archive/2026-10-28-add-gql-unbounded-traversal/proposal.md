# Proposal: add GQL unbounded traversal

## Why

Every open-ended quantifier is rejected today: `*`, `+`, `*n..`, and `{m,}` raise a
deferred-construct error. The gated `Open-ended quantifiers` row is the remaining traversal
blocker for the 1.0 profile, and the engine cannot yet execute it safely. Quantified patterns are
matched over a region materialized to a fixed depth, and `LIMIT` is applied after every row has
been built, so accepting an open upper bound would either truncate results or exhaust memory before
the budget can help.

## What Changes

- Accept these open-ended quantifiers with the path-semantics matrix:
  - `*` means zero or more hops and defaults to `WALK`.
  - `+` means one or more hops and defaults to `WALK`.
  - `{m,}` means `m` or more hops and defaults to `WALK`.
  - Legacy `*n..` keeps `TRAIL`.
- Keep the legacy `*n`, `*n..m`, and `*0..m` forms and the existing mix rule unchanged.
- Add frontier-based, on-demand adjacency for open patterns. An open walk reads only the levels it
  visits instead of capturing a depth-bounded region.
- Add a demand-driven read pipeline so a final `LIMIT` can stop matching, and therefore expansions,
  early. `ORDER BY`, `DISTINCT`, aggregation, `GROUP BY`, set operations, writes, `NEXT`, and
  `FINISH` still require full evaluation and are documented as such.
- Give a statement that contains an open pattern a consistent read snapshot by running its read
  stages inside one read transaction and draining them before any write stage.
- Charge open-walk expansions and rows to the existing budget. An open `WALK` without a demand
  bound runs until the budget error; it never returns a truncated path set, and a
  write statement still rolls back completely.
- Keep the Python traversal API unchanged. `Graph.paths` remains a bounded, relationship-unique
  trail enumerator with an optional limit.
- Flip `Open-ended quantifiers`, `*`, `+`, `{m,}`, and legacy `*n..` to `supported`, add the
  conformance cases, and update the profile, query-language reference, grammar summary, querying
  guide, performance notes, path tour, README, and changelog.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-query-language`: open-ended relationship quantifiers are accepted and matched under the
  resolved path mode; read stages support demand-driven execution; open traversal uses a consistent
  statement snapshot; the deferred open-bound diagnostic is removed.

## Impact

- Query frontend: `engine/query/parser.py` (open quantifier bounds), `semantic.py` (bound
  validation and path-mode resolution), `ast.py` and `plan.py` (open markers in the plan).
- Pattern engine: `engine/query/pattern.py` (live frontier, open segments, demand cancellation,
  optional and quantified-stage iteration).
- Execution: `engine/query/executor.py` (streaming stage pipeline, final demand, snapshot
  transaction, write draining, explain output).
- Traversal: `engine/traversal.py` (single-node `edges` access on the traversal source and an
  on-demand neighborhood backed by the repositories).
- Budget: `engine/query/budget.py` (lazy counting and cancellation behavior); no public budget
  change.
- Compatibility: queries that use an open quantifier were rejected before, so no working query
  changes. Bare `*` now includes zero-hop matches; `+` is the one-or-more spelling.
- Public API: no signature changes; `Graph.query`, `Graph.prepare`, `Transaction.query`, and
  `PreparedQuery.execute` keep their contracts and still return a materialized `QueryResult`.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md`,
  `docs/guides/querying.md`, `docs/reference/performance.md`, `examples/tours/04-paths.gql`,
  `README.md`, and `CHANGELOG.md`.
- Tests: parser, semantic, pattern, executor, snapshot, budget, rollback, traversal, conformance,
  profile consistency, performance notes, and TRON-themed cycle, dense, self-loop, diamond, and
  parallel-relationship fixtures.
- Out of scope: match modes, path search, grouped quantified paths, result streaming, path
  indexing, weighted traversal, and Python traversal API changes.
