# Design

## Context

See `proposal.md` — Why. The current engine analyses a statement into two separate collections:
`Analysis.stages` for read stages and `Analysis.write_clauses` for writes. `PlanBuilder` fuses
adjacent mandatory matches, emits all stage operators, then all write operators, and `_execute`
runs every read stage, then `MutationExecutor.apply` once for every write, then the final
projection. That model cannot express `NEXT`, because a later segment must be able to read what an
earlier segment wrote and must see the preceding `RETURN` table.

The parser also enforces one global clause order: every `MATCH`/`FOR`/`FILTER`/`WITH` must precede
every write, and `RETURN` is final. The composition change must keep those rules *within a segment*
while allowing a new segment to start from the previous segment's result.

The current aggregator already exposes an explicit grouping parameter: `WithStage.grouping` holds
the implicit keys, and `_aggregate_project(items, grouping, bindings, ...)` produces one row per
group. `RETURN NO BINDINGS` currently has no representation because `Return.items` is always
non-empty for a parsed return; `FINISH` has no AST node or token at all.

## Goals / Non-Goals

**Goals:**

- Add GQL-compliant `NEXT` with per-segment `RETURN`, result-table flow, and optional `YIELD`.
- Add canonical `FINISH` for no-result statements, and keep `RETURN NO BINDINGS` as a labeled
  pygrafito extension.
- Add `LET`, `GROUP BY` (with `DISTINCT`), `FOR` ordinality/offset, and the zero-column extension
  without breaking the existing `WITH`, `UNWIND`, or implicit-grouping behavior.
- Keep one transaction, one savepoint, and one query budget per statement, even when segments
  interleave writes and reads.
- Reuse the existing projection/aggregation machinery instead of introducing a second one.
- Keep the plan/explain pipeline observable and testable after interleaving.

**Non-Goals:**

- `UNION`, `EXCEPT`, `INTERSECT`, `OTHERWISE`, `CALL` subqueries, or `YIELD` for call results.
- `WITH *`, the expression vocabulary (`CASE`, maps, `EXISTS {}`), or open-ended traversal.
- Changing the public Python traversal API or storage format.
- Making `GROUP BY` keys variable-only, as strict ISO does; this change deliberately allows
  expressions as a labeled extension.

## Decisions

### D1. One ordered operation pipeline with segment result projections

`Analysis` gains `operations: tuple[ReadStage | WriteStage, ...]` in source order. `WriteStage` is a
frozen wrapper around one write clause. A non-final `RETURN` is lowered to a `SegmentReturnStage`
that reuses the `WithStage` projection/aggregation/order/pagination fields and resets the scope to
its projected columns. A `YIELD` after `NEXT` is lowered to a `YieldStage` that selects and renames
existing columns. The final `RETURN` stays `Analysis.return_clause`; `FINISH` sets
`Analysis.finish = True` and has no final projection.

The planner emits one `PlanStage` per operation, preserving order, and inserts a `NEXT` boundary
operator. Match fusion only combines adjacent `MatchStage` entries with no intervening operation.
The executor iterates `operations`: read stages go through `_run_stage`; a `WriteStage` calls
`MutationExecutor.apply` for that single clause and keeps the returned bindings. After the pipeline,
the final `RETURN` projects the result or `FINISH` returns an empty result.

Alternatives considered:

- **Keep the global read-before-write rule and reject a later `MATCH` after an earlier write.**
  Rejected: it does not match GQL's linear-query pipeline or Cypher's sequential queries.
- **Run each segment as its own transaction.** Rejected: breaks statement atomicity and the budget
  contract.
- **Re-run the executor per segment with serialized bindings.** Rejected: duplicates planning and
  loses the natural in-memory binding flow.

Risk to verify in the first task: applying consecutive write clauses one at a time must be
equivalent to applying them as one list. A test covers `SET` followed by `REMOVE` and `CREATE`
followed by `SET` across the split.

### D2. `NEXT` follows the GQL linear-query model

A statement is one or more linear segments separated by `NEXT`. Each read segment ends in `RETURN`;
the `RETURN` table becomes the next segment's input. An optional `YIELD` after `NEXT` selects and
renames columns; without `YIELD`, every preceding column remains in scope, which is both the GQL
default and the Cypher behavior. A write-only segment passes its bindings unchanged as a
Cypher-compatible extension. The final segment may end in `RETURN` or `FINISH`; an intermediate
`RETURN` is not the call result.

A non-final `RETURN` is a projection and scope reset: it may aggregate, group, order, and paginate,
so mid-query grouping no longer requires `WITH`. `YIELD` is a second scope reset that sees only the
preceding result's columns; an unknown column or duplicate output name is rejected. The whole
statement stays in one transaction and one `BudgetTracker`.

Alternatives considered:

- **Final-`RETURN`-only with implicit binding flow.** Rejected: it rejects valid GQL and Cypher 25,
  makes mid-query grouping impossible without `WITH`, and is a special case that is harder to
  explain.
- **Full `YIELD`-only with no no-`YIELD` form.** Rejected: Cypher compatibility requires accepting
  the no-`YIELD` form.
- **Separate transactions per segment.** Rejected for the same atomicity reasons as D1.

### D3. `LET` is an additive stage, aligned with Cypher 25

`Let` carries ordered assignments. `LetStage` evaluates each assignment per input row, left to
right, and appends to the existing binding. The analyzer validates each expression against the
scope including earlier assignments, rejects a name already in scope or repeated in the clause, and
rejects aggregates. A direct `Variable` assignment inherits that variable's kind; any other
expression binds a scalar. `LET` counts as a row source, so `LET x = 1 RETURN x` is valid without a
`MATCH` or `FOR`.

Alternatives considered:

- **Lower `LET` to `WITH`.** Rejected: `WITH` resets the scope, which is exactly what `LET` must not
  do.
- **Evaluate every assignment against the input row only.** Rejected: left-to-right is the
  documented order and the more useful composable form.

### D4. `FOR` ordinality is an `UnwindStage` field

`Unwind` and `UnwindStage` gain an optional index name and an `OrdinalityKind` (`ORDINALITY` for
1-based, `OFFSET` for 0-based). The parser accepts the suffix after both `FOR ... IN ...` and
`UNWIND ... AS ...`. It requires a fresh index name, rejects the element name as the index, and
rejects combining both forms. The executor enumerates the list with the corresponding start value
and binds both names; null and empty lists still produce no rows.

Alternatives considered:

- **A separate ordinality stage.** Rejected: it would duplicate the list evaluation and make the
  index count per input row harder to reason about.
- **Support only `FOR`.** Rejected: `UNWIND` is an alias for `FOR` and must stay behaviorally
  identical.

### D5. `GROUP BY` is a `RETURN` suffix with an explicit key set

`Return` gains `group_by: tuple[Expression, ...] | None`; `None` means no explicit clause, `()`
means `GROUP BY ()`, and a non-empty tuple means the listed keys. The parser reads keys after the
return items, before `ORDER BY`/`OFFSET`/`LIMIT`.

The analyzer sets `grouped = group_by is not None or has_aggregates`. When `group_by` is present it
is the grouping; otherwise the existing non-aggregate items form the implicit keys. Validation:

- Every non-aggregate return item's expression must structurally equal one grouping key.
- A key may be a direct variable in scope and need not be returned.
- GQL keys are variable references; expressions are accepted as a labeled pygrafito extension.
- `RETURN *` and `RETURN NO BINDINGS` cannot combine with `GROUP BY`.
- `RETURN DISTINCT ... GROUP BY ...` is accepted; `DISTINCT` applies after grouping.
- `GROUP BY ()` requires at least one aggregate and no non-aggregate item.
- Null key values form one group; empty input produces no groups unless `GROUP BY ()` is used.

The executor reuses `_aggregate_project` with the explicit keys. When there are no aggregates but
an explicit `GROUP BY`, it still takes the grouping path so the keys are deduplicated. The key
equality uses the same value equality as the existing aggregation keys. `DISTINCT` remains the
existing post-projection step.

Alternatives considered:

- **A standalone `GROUP BY` stage with hidden group rows.** Rejected: it would leak a private
  "group of rows" value into the binding table and complicate later stages.
- **Only strict ISO variable keys.** Rejected for this change: expression keys are a small,
  explicit leniency that keeps the current implicit-grouping ergonomics; the deviation is recorded
  in the profile.
- **Reject `DISTINCT` with `GROUP BY`.** Rejected: GQL allows the combination; the result is just
  redundant.

### D6. `FINISH` is canonical; `RETURN NO BINDINGS` is an extension

`FINISH` is a final clause with no result. It applies every preceding read and write clause and
returns an empty `QueryResult` (no columns, no rows) with the mutation summary. A write statement
may also omit the result clause, which is the Cypher-compatible equivalent. `FINISH` cannot be
followed by another clause or `NEXT`.

`RETURN NO BINDINGS` is retained as a labeled pygrafito extension: zero columns and one empty row
per input binding, final-only, with no `DISTINCT`, `ALL`, `*`, `GROUP BY`, `ORDER BY`, `OFFSET`, or
`LIMIT`. The analyzer sets empty columns/items/grouping/sorts; the executor projects one
`Row((), ())` per surviving binding. The result model already accepts a zero-length `Row`;
`QueryResult` must be checked and, if necessary, relaxed to allow zero columns.

Alternatives considered:

- **Keep `RETURN NO BINDINGS` as canonical GQL.** Rejected: GQL uses it as an internal
  specification device; multiple conforming implementations reject it as user syntax, and Cypher 25
  uses `FINISH`. Presenting it as canonical would misstate compliance.
- **Drop `RETURN NO BINDINGS` entirely.** Rejected: it is a useful zero-column/debug form, and the
  existing profile already lists it; labeling it as an extension preserves the behavior without
  overclaiming.
- **One row total for `RETURN NO BINDINGS`.** Rejected: it loses the observable row cardinality and
  does not match the "project every input row to the empty binding" reading.

### D7. Gates and profile status

`Gated` keeps only the open-bound entry. The composition constants and entries are deleted, so a
composition construct no longer reaches a gate. The parser's `_reject_ordinality` helper becomes
positive parsing code. `tests/engine/query/test_gated.py` keeps only the open-bound case; the
former composition cases become acceptance tests in the parser/executor suites.

The spec removes the old "Gated construct diagnostics" requirement and adds "Deferred construct
diagnostics" for open bounds only. The profile matrix flips the composition rows to supported:
`LET`, `NEXT` (with `YIELD`), `FINISH`, `GROUP BY`, and `FOR` ordinality/offset. It adds a
`RETURN NO BINDINGS` pygrafito-extension row with `FINISH` as the canonical alternative, and records
the `GROUP BY` expression-key deviation. The status board and gated table are updated accordingly.

### D8. Benchmark the composition pipeline

Add a small composition scenario to `benchmarks/run.py` that exercises `LET`, an intermediate
`RETURN ... GROUP BY`, and a `NEXT` chain, and compare it with the existing pipeline at 20,000
nodes. Run the existing scenarios as a regression check and record the result in
`docs/reference/performance.md`. The pipeline iterates one entry per operation, so the expected
cost is within noise; the measurement makes that explicit.

## Risks / Trade-offs

- **Interleaving changes write/read visibility.** → The pipeline is the source of truth; tests
  cover an earlier write followed by a later match, a write inside the final segment, and a budget
  failure that rolls back an earlier segment.
- **Segment result tables add a second scope reset alongside `WITH`.** → Reuse the `WithStage`
  projection/aggregation path and add a test that an intermediate `RETURN ... GROUP BY` feeds a
  later `FILTER`/`MATCH`.
- **`YIELD` can hide a column a later segment expects.** → Reject unknown and duplicate yielded
  names and test the no-`YIELD` pass-through explicitly.
- **One-clause mutation application diverges from the batch behavior.** → Add a parity test for
  `SET` + `REMOVE` and `CREATE` + `SET`, and keep the same `MutationExecutor.apply` call shape.
- **`GROUP BY` expression keys and null grouping differ from strict ISO.** → Record both in the
  profile deviation column and cover null, empty-input, and `GROUP BY ()` cases.
- **Zero-column results surprise existing result assertions.** → Test `QueryResult.columns == ()`,
  `len(result.rows)`, and `Row` lookup behavior; keep the result dataclasses unchanged unless the
  constructor rejects empty columns.
- **`FINISH` and write-only finals both produce no result.** → Test both, and document that a write
  statement may omit the result clause.
- **Full `NEXT` increases the change size.** → Keep the spec and tasks split by segment result,
  `YIELD`, placement, and `FINISH`; the implementation reuses the existing projection machinery.
- **`LET` kind preservation is limited to direct variables.** → Document that a computed expression
  is scalar; users can keep the element binding or use a direct assignment for element values.
- **New keywords (`FINISH`, `YIELD`, `LET`, `NEXT`, `GROUP`, `ORDINALITY`) can be reserved in
  variable positions.** → This matches GQL's keyword set and Cypher 25's new keywords; document the
  quoting escape hatch and add parser coverage for keyword-as-name positions that already work.

## Migration Plan

- No storage migration. The change is query-language only; existing graphs and indexes are
  untouched.
- Existing `WITH`, `UNWIND`, and implicit-grouping statements keep working. There are no breaking
  changes, so no release-note migration is required beyond documenting the new canonical forms and
  the `RETURN NO BINDINGS` extension.
- `RETURN NO BINDINGS` moves from a gated canonical form to a supported pygrafito extension; this
  is an addition, not a behavior removal.
- Rollback is a code/docs revert; no persistent state changes.
- The conformance corpus and profile matrix are the release gate: a row flips only when its cases
  pass, and the existing "supported row needs a case" test stays in force.

## Open Questions

None. The remaining choices (expression grouping keys, empty-key grouping, zero-column
cardinality, left-to-right `LET`, write-only segments) are decided above and recorded in the specs;
any later change to them is a separate spec change.
