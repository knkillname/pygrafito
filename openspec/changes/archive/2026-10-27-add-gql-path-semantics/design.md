# Design

## Context

See `proposal.md` for motivation and `specs/` for the behavior contract.

The current matcher is trail-only by construction. `WalkState` carries a single
`used: frozenset[int]` of relationship identifiers, and `_walk_fixed` and `_walk_quantified` in
`engine/query/pattern.py` reject any extension whose edge id is already in that set. There is no
place to record a path mode and no budget to stop a walk that keeps finding edges.

Fixed-length patterns are executed two ways. `engine/query/compiler.py` pushes them down to indexed
SQL, while quantified patterns and residual predicates run through `pattern.py`. Every mode must
therefore be expressible in both, or explicitly fall back to one.

`Analysis` is flattened after parsing: one `return_clause`, one `columns`, one `variable_kinds`,
one `grouping`, and one `sorts`. That is fine for this change because path semantics stay within a
single statement; it becomes relevant to the composition change.

The profile already fixes the resolution order, the four modes, and the budget counters. This
design only chooses how to represent and enforce them.

## Goals / Non-Goals

**Goals:**

- Enforce `WALK`, `TRAIL`, `SIMPLE`, and `ACYCLIC` identically in the indexed and in-memory paths.
- Resolve a path's mode once, before execution, so mode errors are semantic errors.
- Bound every query by default so enabling `WALK` cannot hang an embedded process.
- Keep `WALK` allocation-free in the hot path and keep the trail fast path close to its current
  cost.
- Keep the public `paths()` and `Direction` APIs unchanged.

**Non-Goals:**

- Open-ended quantifiers, lazy frontier traversal, and unbounded `WALK` (deferred).
- Match modes (`DIFFERENT EDGES`, `REPEATABLE ELEMENTS`) and grouped quantified paths.
- Path search prefixes (`ANY SHORTEST` and friends).
- Pushing `LIMIT` into the pattern engine; the budget remains the guarantee.
- Changing the on-disk schema, the CLI command set, or the traversal API.

## Decisions

### The budget ships inside this change

The profile gates `WALK` on the budget, the budget has no syntax, and it has no matrix row of its
own. A separate `add-query-budget` change would contain only an error path and would be rewritten
by this change a week later. The budget is task group 1 here, tested on its own before any mode
work starts.

*Alternative rejected:* a standalone budget change, for the reasons above.

### `QueryBudget` is a frozen value object with an optional per-execution override

Add `QueryBudget` to `model.py` and export it. Fields are `max_expansions: int | None = 1_000_000`,
`max_rows: int | None = 100_000`, and `max_seconds: float | None = None`. `None` means unlimited,
so a caller can disable one counter without disabling the others. `Graph.open` takes the graph
default; `Graph.query` and `PreparedQuery.execute` take a per-execution override that never mutates
the default.

*Alternative rejected:* separate keyword arguments on every method. It spreads the same knobs across
three signatures and does not extend to future counters.

### A dedicated `QueryBudgetExceededError`

Subclass `QueryExecutionError`, carry `counter` and `limit` attributes, and phrase the message as
`query budget exceeded: expansions limit 1000000`. Callers embedding the library need to tell a
runaway query apart from a storage failure, and the profile requires the counter and limit to be
named.

*Alternative rejected:* a plain `QueryExecutionError` with a formatted message. It forces callers to
parse text.

### Mode resolution happens in static analysis

Add an internal `PathMode` enum to `engine/query/ast.py`, an optional per-path mode to
`PathPattern`, and an optional clause mode to `Match`. `SemanticAnalyzer` resolves each path's mode
with the profile rule and stores the result on the analyzed plan. The parser and evaluator never
re-derive it.

*Alternative rejected:* resolving at match time. It delays a detectable error until execution and
repeats the same work per row.

### A query-level `EdgeDirection` enum instead of extending `Direction`

`model.Direction` is public and is used by traversal, storage, and the CLI. The seven query forms
need a richer value: `OUTGOING`, `INCOMING`, `ANY`, `UNDIRECTED`, `DIRECTED_EITHER`,
`INCOMING_OR_UNDIRECTED`, and `OUTGOING_OR_UNDIRECTED`. Represent them with an internal enum in
`ast.py` and map to `Direction` plus the directed flag at the storage boundary.

*Alternative rejected:* extending the public `Direction` with four more members. It would change a
public traversal enum for a query-only concern and force every existing call site to handle values
it can never receive.

### Mode memory is per mode, not one universal tracker

- `WALK` tracks nothing beyond the current position and node.
- `TRAIL` keeps the existing relationship-id set.
- `ACYCLIC` keeps a node-id set.
- `SIMPLE` keeps a node-id set plus a `closed` flag: returning to the start node is allowed only as
  the final node, and once closed the state cannot be extended further.

This keeps `WALK` free of allocations and makes the `SIMPLE`/`ACYCLIC` distinction a terminal-state
rule rather than a separate traversal.

*Alternative rejected:* one tracker that always maintains node and relationship sets. It doubles
the per-hop allocation cost for the common `WALK` case.

### The indexed compiler enforces modes with predicates, not fallback

`compiler.py` gains mode predicates for fixed-length paths in one path:

- `TRAIL`: pairwise `edge_id <> edge_id` across relationship aliases.
- `ACYCLIC`: pairwise `node_id <> node_id` across node aliases in the path.
- `SIMPLE`: the same, except the first and last node aliases may be equal.
- `WALK`: no predicate.

This also closes an existing gap: a fixed pattern that traverses the same self-loop twice is
currently not rejected under trail semantics.

*Alternative rejected:* routing every non-`WALK` path through the in-memory matcher. It would
silently drop the indexed plan for `MATCH TRAIL`, which is the migration path for every existing
user.

### Open-ended upper bounds get their own follow-up gate

`*`, `+`, `*n..`, and `{m,}` are rejected with a deferred error naming
`add-gql-unbounded-traversal`. Closed forms use the existing quantifier fields, and no dynamic
bound is derived from the graph size.

*Alternative rejected:* deriving a finite bound from the relationship count so `*` "just works"
under `TRAIL`. It produces a search space the budget cannot protect and contradicts the documented
deferral.

### Counting points are explicit

- An expansion counts once per relationship considered when extending a path position.
- A row counts once per binding emitted by a stage, including pattern stages.
- The clock is checked at stage boundaries and every 1,024 expansions, so the hot path is not
  dominated by `time.monotonic`.
- The counters live in a per-execution tracker owned by `QueryExecutor` and passed to the matcher.
  Results are materialized, so exceeding the budget after some rows raises and returns nothing.

*Alternative rejected:* counting inside SQLite via a user-defined function. It is slower and
invisible to the in-memory matcher.

### `paths()` stays a trail enumerator

The Python API is unchanged and a test pins it: a cyclic fixture that `MATCH WALK` accepts must
still fail to enumerate under `paths()` beyond the trail.

*Alternative rejected:* making `paths()` mode-aware. It would break the documented public contract
for no gain in this change.

## Risks / Trade-offs

- **`WALK` on a cyclic graph explodes.** → The budget is on by default and this change does not
  enable unbounded quantifiers. A corpus case covers a cycle under `WALK`.
- **Mode bookkeeping slows trail queries.** → Benchmark before and after. If trail regresses by
  more than a few percent, replace the persistent frozenset copy with a mutable set plus undo on
  backtracking.
- **The `WALK` default changes results silently.** → Document it as **BREAKING** in the changelog,
  add the migration table to the profile, and add a corpus case that shows a repeated self-loop
  now matching under the default.
- **The compiler and the in-memory matcher diverge.** → Both consume the same resolved mode and the
  same `EdgeDirection` predicate helper; the corpus runs every case through whichever path the
  planner chooses, and dedicated tests force one path at a time.
- **`max_seconds` makes tests timing-dependent.** → It is opt-in and disabled by default; tests use
  a zero limit or an injected clock, never a real-time sleep.
- **Budget errors inside an explicit transaction could poison it.** → The write path uses a
  savepoint, as today, so the statement rolls back and the caller's transaction continues.
- **A budget error is not a query syntax error.** → It is raised during execution and leaves the
  graph handle usable; tests assert both.

## Migration Plan

1. Land budget support and tests with the current trail behavior unchanged.
2. Land mode plumbing, the canonical quantifier syntax, and the direction forms, still defaulting
   to `TRAIL` so the corpus keeps passing.
3. Flip the default to `WALK`, update the corpus and profile rows in the same commit, and add the
   migration cases.
4. Update the reference, guides, examples tour, README, and changelog; build the docs with
   warnings as errors.
5. Release as 0.9.0 with the breaking default called out.

No data migration is needed: the schema, the snapshot format, and the Python traversal API are
unchanged. Rollback is installing the previous release; queries that need the old behavior can add
`MATCH TRAIL` or keep a legacy quantifier.

## Open Questions

None that change the approach. The budget defaults are tuned by the benchmark task, which is a task
detail rather than an open design question.
