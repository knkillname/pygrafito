# Design: unbounded traversal

## Context

See `proposal.md` — Why. The current execution shape explains the constraints:

- `Parser` rejects any missing upper bound in `_legacy_quantifier` and
  `_canonical_quantifier` through the `Gated` diagnostic.
- `PatternEngine` matches quantified patterns over an `AdjacencySnapshot` captured by
  `TraversalCapture.region(start, depth)`. The depth is the sum of each relationship position's
  maximum, so an unbounded position has no depth to capture.
- `PatternEngine.match` returns a list; `_run_stage` returns a list; `QueryExecutor._execute`
  builds every row before projecting, ordering, and slicing for `LIMIT`.
- A statement already owns one `BudgetTracker`, one savepoint for writes, and one SQLite
  connection. Read stages run before write stages within a segment.
- `DatabaseNeighborhood` already reads adjacency from the repositories on demand, level by level,
  but `PatternEngine` needs a single-node `edges` view that only `AdjacencySnapshot` provides.
- `Graph.paths` is a separate bounded trail enumerator and must not change.

## Goals / Non-Goals

**Goals:**

- Accept the canonical open quantifiers and the legacy open form without changing closed forms.
- Read open patterns on demand, with no depth cap and no whole-component capture.
- Let a final `LIMIT` stop matching and expansion early when the result shape allows it.
- Keep one statement snapshot, one budget, one transaction, and no partial result.
- Preserve the performance and snapshot of bounded patterns by leaving their capture path intact.
- Keep the public result model materialized.

**Non-Goals:**

- No streaming `QueryResult`, cursor API, or async API.
- No path search, match mode, or grouped pattern; later changes build on this engine.
- No change to `Graph.paths`, `Graph.traverse`, or `Graph.shortest_path`.
- No new counter and no new public budget field.

## Decisions

### Reuse `min_hops` and `max_hops` instead of adding a quantifier node

`RelationshipPattern` already distinguishes an ordinary relationship (both bounds `None`) from a
quantified one (at least one bound present). An absent upper bound means unbounded, so the open
forms map as follows:

| Form | `min_hops` | `max_hops` | `canonical_quantifier` |
| --- | --- | --- | --- |
| `*` | 0 | `None` | `True` |
| `+` | 1 | `None` | `True` |
| `{m,}` | `m` | `None` | `True` |
| `*n..` | `n` | `None` | `False` |

This keeps the AST and every `is not None` check working. `SemanticAnalyzer._validate_quantifier`
stops rejecting a missing upper bound; it keeps rejecting negative bounds and a lower bound above
a present upper bound. `_resolve_path_mode` stays unchanged, so `*`, `+`, and `{m,}` resolve to
`WALK` and `*n..` resolves to `TRAIL`.

Alternative considered: a dedicated `Quantifier` dataclass. It would force a wider AST migration
for no behavioral gain, and the existing bounds already carry the needed information.

### Read open patterns from a live frontier

Add `edges(node_id, direction, labels)` to `TraversalSource`; `AdjacencySnapshot` implements it
from its materialized maps exactly as today, and `DatabaseNeighborhood` implements it with the
repository's incident-edge query. `PatternEngine._capture` chooses:

- Bounded or fixed patterns: `TraversalCapture.region` as today. This keeps the consistent region
  and the indexed reads.
- Any pattern with an open position: the live `DatabaseNeighborhood`.

The walker already keeps `used` and `visited` sets for `TRAIL`, `SIMPLE`, and `ACYCLIC`, so it does
not need the whole region to enforce the mode. `WALK` keeps no memory beyond the current path.

Alternative considered: capture the reachable component up to the budget. It still materializes a
large graph and defeats `LIMIT`. Rejected.

Alternative considered: cap an open pattern at a fixed depth. It silently truncates results.
Rejected.

### One read snapshot per read prefix

A plan is inspected for an open position. When one exists, the executor opens a deferred read
transaction (`BEGIN` / `COMMIT`) around the contiguous read stages if the connection is not already
in a transaction. `Transaction.query` reuses the caller's transaction and does not open another.
Before the first write stage of a segment, the executor drains and closes the read stream and ends
the read transaction, then runs the write in the existing write path. A later `NEXT` segment opens
its own read snapshot.

Alternative considered: rely on per-expansion reads without a transaction. Two expansions in one
walk could see different committed states. Rejected.

Alternative considered: keep the read transaction open across writes. It complicates savepoints and
lock upgrade behavior on file databases. Rejected.

### Demand-driven pull pipeline

Introduce three internal pieces:

- `RowStream`: an iterator of binding dictionaries with a `close()` that propagates cancellation
  upstream.
- `Demand`: the number of rows still needed, derived from the final `SKIP` and `LIMIT`, or `None`
  for unlimited.
- `PlanShape`: a static classifier that reports whether the final result can stop early.

`_execute` selects the streaming path only when all of the following hold:

- The statement is read-only.
- It is a single linear term, not a compound set operation.
- It has no `NEXT`, `FINISH`, aggregation, `GROUP BY`, `DISTINCT`, or `ORDER BY`.
- The final `RETURN` is a plain projection, or the statement has no result clause after writes
  (which is not streamable).

Otherwise the existing materialized path runs, with the documented note that pagination applies
after full evaluation.

Stage streaming:

- `PatternEngine` gains `iter_match`, a generator form of `match`. `match` stays as the list
  wrapper for write stages, `OPTIONAL MATCH` null detection, and non-streaming callers.
- `_run_stage` gains a generator variant. `UNWIND`, `LET`, `FILTER`, `MATCH`, and `OPTIONAL MATCH`
  yield rows. `WITH` yields only when it has no ordering, distinctness, or aggregation; otherwise
  it materializes.
- Projection is a generator. The evaluator consumes rows until `Demand` is exhausted, then closes
  the stream.
- A write stage consumes the read stream fully before it runs; a budget error or an exception
  closes the stream and releases the snapshot in `finally`.
- `LIMIT 0` closes the stream before the first pattern expansion. `OFFSET` consumes and discards
  the required rows without counting them as result rows.

Alternative considered: pass the `LIMIT` only into `PatternEngine`. Filters, `OPTIONAL MATCH`, and
projection can drop rows, so the engine cannot know how many matches are enough. Rejected.

### Budget and failure behavior

`BudgetTracker` is unchanged. Expansions are charged per candidate edge before the mode check;
rows are charged per produced binding. A closed stream simply stops charging. When the budget is
exceeded, `QueryBudgetExceededError` propagates through the executor, the read snapshot is released,
the statement savepoint rolls back any write, and the graph handle stays usable. There is no
"best effort" truncation.

### Explain output

A quantified explain entry names the open position and its path mode, for example
`MATCH QUANTIFIED OPEN WALK`, so users can see that the plan is not depth-bounded. Bounded
quantified plans keep their current SQL explanation.

### Documentation

- The profile moves the open-ended rows to `supported` and describes the demand and budget rules.
- The query-language reference replaces the deferred section with open-quantifier forms and the
  early-stop rules.
- The querying guide and path tour show `LIMIT`, `TRAIL`, and the budget error shape.
- The performance page records the measured expansion rates for open walks on memory and file
  databases, and explains why ordering and aggregation cannot stop early.
- `CHANGELOG.md` gets an end-user entry.

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| An open `WALK` still hangs | Streaming first, budget second, and a test that asserts the budget error with no rows |
| Lazy reads change snapshot results | Statement read transaction, WAL file databases, and a concurrent-writer test |
| Transaction nesting breaks writes | Drain read prefixes before writes; nested calls reuse the active transaction; rollback tests |
| `OPTIONAL MATCH` needs to know whether a row matched | The per-row pattern stream is drained for null detection; demand still stops the whole statement |
| Bounded patterns regress | Keep `TraversalCapture` for bounded patterns and run the existing traversal benchmarks |
| Path variables consume memory under open `WALK` | Document that an open path variable grows with path length; demand bounds it; budget stops the rest |
| Generator cleanup errors mask the original failure | Close in `finally`, suppress only cleanup errors, and test the error path |
| `LIMIT` stops too early under hidden ordering | The `PlanShape` classifier includes final ordering, stage ordering, distinctness, grouping, and set operations; tests cover each shape |

## Migration Plan

1. Land the parser, semantic, and AST changes behind the same rejection tests, then remove the
   open-bound gate.
2. Land the live frontier and open walker for bounded results first (TRAIL/SIMPLE/ACYCLIC), then
   the streaming pipeline, then the open `WALK` budget path.
3. Keep the old materialized path as a fallback selected by `PlanShape`.
4. Update the profile and corpus in the same change; no database format or version change.
5. Rollback is a code revert; no stored data changes.

## Open Questions

None.
