# Proposal

## Why

The canonical GQL composition surface is the last major language gap before the expression
vocabulary and 1.0 hardening. `LET`, `NEXT`, `GROUP BY`, `FOR ... WITH ORDINALITY`/`WITH OFFSET`,
`FINISH`, and `RETURN NO BINDINGS` are still gated, so callers must lean on the `WITH` extension,
the `UNWIND` alias, and implicit grouping, and cannot compose linear queries or end a write
pipeline without a result. Path semantics and the query budget are implemented; composition is the
next dependency.

The project is GQL-first, with Cypher-compatible extensions. That means valid GQL must work: a
`NEXT` segment ends in its own `RETURN`, `YIELD` selects the columns that pass to the next segment,
`FINISH` is the canonical no-result clause, and `RETURN DISTINCT ... GROUP BY ...` is accepted.
Cypher compatibility means the no-`YIELD` and write-only-segment forms are accepted too, and that
`WITH`, `UNWIND`, and implicit grouping remain available as labeled extensions.

## What Changes

- Add canonical `LET` as an additive, row-wise read stage. It extends the current scope instead of
  replacing it, can lead a query, evaluates its definitions left to right, and rejects aggregates
  and shadowing.
- Add full GQL `NEXT` composition. Each segment is a linear query and a read segment ends with
  `RETURN`; `NEXT` carries the preceding `RETURN` table into the next segment. An optional `YIELD`
  selects and renames the columns that pass; without `YIELD`, every preceding column remains in
  scope. A non-final `RETURN` acts as a projection and scope reset, so it can aggregate, group,
  order, and paginate. A write-only segment that passes its bindings unchanged remains accepted as
  a Cypher-compatible extension.
- Add `FINISH` as the canonical GQL no-result clause. It ends the statement, applies every
  preceding side effect, and returns an empty result. A write statement may also omit the result
  clause, which is the Cypher-compatible equivalent.
- Keep `RETURN NO BINDINGS` as a labeled pygrafito extension rather than a canonical GQL form. It
  returns zero columns and one empty row per input binding and is final-only. GQL's user-facing
  no-result form is `FINISH`.
- Add explicit `GROUP BY` as a suffix of `RETURN`, including `GROUP BY ()`, and allow `RETURN
  DISTINCT ... GROUP BY ...`. GQL grouping keys are direct variable references; pygrafito
  additionally accepts expressions as a labeled extension. Keys may be grouped without being
  returned, and `GROUP BY` without aggregates deduplicates.
- Add `FOR ... WITH ORDINALITY` (1-based) and `WITH OFFSET` (0-based), also accepted after the
  `UNWIND` alias. The index variable is fresh and mutually exclusive between the two forms.
- Replace the "all reads, then all writes" plan with an ordered read/write pipeline so `NEXT`
  segments can interleave matching and mutation while preserving one transaction and one budget.
- Remove the composition gates from `gated.py`. Open-ended traversal remains the only gated
  construct, owned by `add-gql-unbounded-traversal`.
- Flip the profile matrix/status board, expand the query-language reference and querying guide,
  rewrite the `03-compose` tour, add conformance cases, update the changelog, and record the
  benchmark impact.

No breaking changes: `WITH`, `UNWIND`, and implicit grouping remain accepted as extensions or
aliases. The deliberate deviations from ISO GQL are expression-based `GROUP BY` keys and the
`RETURN NO BINDINGS` extension; the write-only `NEXT` segment is a Cypher-compatible extension.
`YIELD` is supported, and its absence is accepted for Cypher compatibility. A no-`YIELD` `NEXT`
passes every preceding column, which is both the GQL default and the Cypher behavior.

Out of scope: `UNION`/`EXCEPT`/`INTERSECT`, `CALL` subqueries and `YIELD` for call results,
`WITH *`, the expression vocabulary (`CASE`, map literals, `EXISTS {}`), and open-ended traversal.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `gql-profile`: the canonical surface adds `NEXT`, `YIELD`, and `FINISH`, and the extensions table
  adds `RETURN NO BINDINGS` with `FINISH` as its canonical no-result alternative.
- `graph-query-language`: statement shape for linear segments, per-segment `RETURN`, `NEXT YIELD`,
  `FINISH`, the `LET` clause, explicit `GROUP BY`, `FOR` ordinality and offset, the `RETURN NO
  BINDINGS` extension, and deferred-construct diagnostics after the composition gates are removed.

## Impact

- AST and parser: `LET`, `NEXT`, `YIELD`, `FINISH`, and `GROUP BY` forms, an ordinality field for
  iteration, and a no-bindings extension return.
- Semantic analysis: segment-aware clause order, non-final `RETURN` projections, `YIELD` scope
  resets, an ordered operation pipeline, and explicit grouping validation.
- Planner and executor: interleaved read stages and write clauses, one-clause mutation
  application, segment result tables, grouping projection, `FINISH`, and zero-column results.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md`,
  `docs/guides/querying.md`, `docs/guides/examples.md`, `examples/tours/03-compose.gql`,
  `examples/tours/README.md`, `docs/reference/performance.md`, `README.md`, and `CHANGELOG.md`.
- Tests: parser, semantic, executor, plan/explain, conformance corpus, profile coverage, docs
  examples, tour, readme, and budget/rollback coverage for interleaved writes.
- Public API: no new public classes or signatures; `Graph.query`, `Graph.prepare`,
  `PreparedQuery.execute`, and `Transaction.query` keep their current contracts.
