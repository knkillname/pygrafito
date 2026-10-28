# Design: GQL path search

## Context

See `proposal.md` — Why. This change builds on the unbounded walker and the clause-wide match mode:

- `PathPattern` currently carries `mode`, `variable`, `nodes`, and `relationships`. There is no
  search field.
- `PatternEngine` performs a depth-first walk and returns a list. `Compiler` handles stages without
  quantified relationships and already exposes a fixed SQL path.
- The unbounded change adds `iter_match`, a live `DatabaseNeighborhood`, a demand-driven row
  pipeline, and a statement read snapshot.
- The match-mode change adds a clause-wide used-edge set to the usage-aware matcher.
- Explain already prints one line per stage and a marker per quantified plan.

## Goals / Non-Goals

**Goals:**

- One evaluation path for search regardless of whether the pattern is fixed, closed-quantified,
  or open.
- Length-ordered evaluation that never enumerates longer paths than the selection needs.
- Deterministic selection and output order.
- Correct interaction with `WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC`, `DIFFERENT EDGES`, path
  variables, optional match, and the budget.
- A bounded per-partition memory footprint.

**Non-Goals:**

- No weighted shortest path, no graph algorithm, no `ALL` prefix.
- No search prefix inside a group; grouped paths land later and must reuse this evaluator.
- No change to the `QueryResult` or traversal API.

## Decisions

### AST and parser position

Add:

```text
PathSearchKind = ANY | ANY_SHORTEST | ALL_SHORTEST | SHORTEST
PathSearch(kind, k: int | None)
PathPattern.search: PathSearch | None
```

The prefix is parsed at the path head, after an optional `identifier "="` and before the path
mode. The clause path mode still precedes the first path pattern. This yields:

```text
MATCH p = ANY SHORTEST WALK (a)-[:TRUSTS]->{1,}(b) ...
MATCH TRAIL ANY (a)-[:TRUSTS]->{1,}(b) ...
```

`ANY` and `SHORTEST` become reserved keywords. `SHORTEST` requires an integer literal. The parser
records the token span for positioned errors.

Alternative considered: put the prefix before the path variable. GQL writes the variable first; it
also reads better and keeps the current variable lookahead unchanged.

### One search evaluator, not two matchers

A path pattern with a search prefix is evaluated by a new `PathSearchEvaluator` in `pattern.py`,
even when every relationship is fixed. The evaluator reuses `PatternEngine`'s node selection,
predicate checks, binding helpers, mode memory, and match-mode usage set, but replaces the
depth-first recursion with a queue of partial walk states ordered by path length.

Alternative considered: run the SQL compiler for fixed patterns and select afterwards. Anonymous
relationships and path identity are not exposed by the current compiled binding, so it would need
a second binding shape and a second selection implementation for fixed versus open patterns. The
uniform evaluator avoids that drift.

### Length-ordered expansion with a bounded frontier

The evaluator processes path-length layers. Each queue entry holds the partial `WalkState`,
accumulated path length, a tie-break sequence of `(relationship id, orientation)` pairs, and the
input-row partition prefix.

For each partition, the selection limit is:

| Prefix | Kept paths | Stop condition |
| --- | --- | --- |
| `ANY` | 1 | first completed path in layer order |
| `ANY SHORTEST` | 1 | first completed path in layer order |
| `ALL SHORTEST` | all at the minimum length | minimum length reached and its layer drained |
| `SHORTEST k` | up to `k`, increasing length | `k` completed paths |

`ANY` returns the first completed path in layer order. Because the layers are ordered by length,
that path is also a shortest one. GQL permits any path; returning a deterministic shortest path is
a valid choice and pygrafito documents it.

Pruning:

- A state key is `(input row, start node, current node, pattern position, mode memory)` where the
  mode memory is the relationship and node sets already used. The evaluator keeps at most the
  selection limit plus one arrivals per state key. A later, longer arrival cannot beat those
  entries and is discarded.
- Once a partition has its selection, completed paths for that partition are not queued.
- Partial paths longer than the worst kept path of a partition that already has enough results are
  not expanded.
- The frontier is finite: for `WALK` the mode memory is empty and the state key reduces to nodes
  and positions; other modes already bound the walk by the graph's elements; and each state keeps
  a finite number of arrivals.

Tie-break sequence: compare length, then the orientation-aware relationship sequence, then the
node sequence. The queue order is `(length, relationship sequence, node sequence)` so the first
completed path for a partition is the deterministic winner.

### Partitioning and output

The partition key is `(input row index, start node id, end node id)`. An input row with several
path patterns proceeds independently per pattern, as today. A selected result stores the complete
binding and, when the pattern has a path variable, the constructed `Path`.

Rows are emitted by ascending partition key and then the selection order. This is the only stable
order the evaluator promises; a statement `ORDER BY` runs afterwards in the existing pipeline.

### `SHORTEST k` validation

`k` is parsed as an integer literal. A parameter, expression, negative value, or float is a
semantic error before execution. `k = 0` is valid and produces no row for any partition without
walking; a dedicated test pins that no expansion is charged.

### Interactions

- Path modes and match modes are enforced by the reused walk helpers. A candidate rejected by
  either rule is never queued.
- `OPTIONAL MATCH` runs the search per input row and null-extends when the selection is empty.
- `EXISTS { ... }` and `COUNT { ... }` inherit the search; `EXISTS` can stop after the first
  selected row.
- The statement read snapshot covers search because search uses the same live source.
- Explain prints `PATH SEARCH <prefix>` before the stage operators, and the open marker still
  appears for open patterns.

### Budget

Each dequeued and expanded partial path charges the expansion counter for every candidate edge it
examines, before the mode checks. Selected or discarded paths add no extra expansions. A budget
failure propagates through the demand pipeline with no partial rows, and a write rolls back.

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| Frontier explosion for large k or many partitions | Bound arrivals per state, count expansions, and document that budget stops it |
| Tie-break order differs between the SQL and pattern paths | Search uses one evaluator; add a test that runs the same query on memory and file databases |
| `ANY` returning the shortest surprises GQL experts | Document the deterministic choice; it is a valid `ANY` result |
| `k` validation diverges from `LIMIT` | One helper validates page values and one validates `k`; tests cover parameter, expression, negative, float, zero |
| Optional match materializes per input row | It already does; search does not change null detection |
| Grouped paths later need search inside or outside groups | Search stays whole-path only; the grouped change reuses the evaluator and rejects inner prefixes |
| Reserved words break existing queries | Document backtick quoting and add a lexer regression test |

## Migration Plan

1. Land tokens, AST, parser, and semantic validation with no execution change.
2. Land the evaluator for fixed and closed patterns; keep existing queries on the current path when
   no search prefix is present.
3. Land open and match-mode integration.
4. Update explain, profile, corpus, reference, guide, tour, performance notes, and changelog.
5. Rollback is a code revert; no data change.
