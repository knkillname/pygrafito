# Design

## Context

See `proposal.md` for motivation and `specs/graph-query-language/spec.md` for the behavior
contract. Today the front end produces a `Statement` with at most one `Match`, a trailing
set of write clauses, and one `Return`. `SemanticAnalyzer` builds one `Analysis` for that
single match; `PlanBuilder` flattens it into one operator tuple; `Compiler` turns the one
`Match.pattern` into a single indexed SQL statement; `QueryExecutor` materializes the
bindings, applies mutations, then projects, aggregates, orders, and paginates in Python.
`Graph.explain` runs `EXPLAIN QUERY PLAN` over that one compiled statement.

Three properties already hold and must survive the change:

- A statement runs inside one transaction. Read statements use `BEGIN`, write statements use
  `BEGIN IMMEDIATE`, and `Transaction.query` reuses the active transaction. The executor's
  `execute_graph` / `execute_active` split already gives every statement one snapshot and
  one atomic boundary.
- The compiler already unifies repeated variables inside one pattern by reuse of the table
  alias, and it already supports an `expected_id` constraint when the same node variable
  appears twice.
- Traversal primitives (`TraversalCapture`, `AdjacencySnapshot`, `TrailEnumerator`) already
  materialize a depth-bounded region and enumerate relationship-unique trails.

Constraints that shape the approach: one `sqlite3.Connection` per graph, no module-level
functions, one-way imports, and no storage or schema change.

## Goals / Non-Goals

**Goals:**

- Represent a statement as an ordered pipeline of read stages without forking the read and
  write paths.
- Keep every existing statement's result, ordering, and error behavior byte-for-byte
  identical while the pipeline is introduced.
- Compile pattern sets with shared variables as joins, and support a bounded expansion for
  quantified relationships.
- Make `WITH` reuse the projection, aggregation, distinct, ordering, and pagination code
  that `RETURN` already uses.
- Keep `Graph.explain` meaningful for every stage.

**Non-Goals:**

- A query optimizer, cost model, or plan reordering. Stages run in source order.
- Merging a `WITH` stage or an `OPTIONAL MATCH` into the surrounding SQL.
- Pushing `LIMIT` into SQL, streaming rows, or early termination.
- Changing the schema, storage layout, indexes, or transaction API.
- Interpreting `*` as an unbounded traversal.

## Decisions

### D1: Statements become a read-stage pipeline plus trailing writes

```
Statement
  clauses: tuple[Clause, ...]

ReadStage  = MatchStage | OptionalMatchStage | WithStage
MatchStage(patterns, where)
OptionalMatchStage(patterns, where)
WithStage(items, distinct, where, order_by, skip, limit)

Statement = read stages, then write clauses, then optional Return
```

`Analysis` gains `stages: tuple[ReadStage, ...]` and `write_clauses: tuple[WriteClause, ...]`;
`match_clause` is removed. Every `WithStage` carries its own items, grouping keys, sort
specs, pagination values, and output columns, because each stage has its own aggregation and
ordering boundary.

Rationale: a flat operator tuple cannot express "project, rebind scope, then match again".
A stage list makes the boundary explicit and lets the executor loop over one uniform unit.

Alternative rejected: keep the flat clause list and special-case `WITH` in the executor.
That would scatter scope handling across projection and mutation code and make `OPTIONAL
MATCH` impossible to place reliably.

### D2: One planner stage per read stage, fused where fusion is safe

```
Plan
  stages: tuple[PlanStage, ...]     # one per read stage, in source order
  operators: tuple[PlanOperator, ...]  # flattened, kept for explain and tests

PlanStage
  kind: MATCH | OPTIONAL_MATCH | WITH
  operators: tuple[PlanOperator, ...]
```

Adjacent mandatory `MatchStage` instances are fused in the plan into one stage whose
pattern list is their concatenation. This is sound because two consecutive mandatory
matches are a join on their shared variables, and a cartesian product when they share none.
Fusion keeps `MATCH ... MATCH ...` as one SQL statement in the common case.

`OPTIONAL MATCH` is never fused, and `WITH` is always a boundary. `Plan.operators` remains a
flattened property so `explain` and existing single-stage tests keep working; new tests
assert stage boundaries.

### D3: A match stage compiles as a pattern *set*

`Match.pattern` becomes `Match.patterns: tuple[PathPattern, ...]`. The compiler is extended
to compile every pattern of a stage into the same SQL statement against one shared alias
map:

- A variable appearing in a second pattern reuses the existing table alias, so the join
  condition is `alias.id = alias.id` (or a predicate), exactly as repeated variables already
  work inside one pattern.
- A variable with no earlier binding starts a new `nodes` / `relationships` join, which
  gives the cartesian product for disconnected patterns.
- `Create` keeps its single `pattern`; multiple creates remain separate clauses.

Alternative rejected: build a separate SQL statement per pattern and join rows in Python.
That would materialize an unnecessary cartesian product and lose the shared predicates that
make the join selective.

### D4: Stages after the first run per input row, with bound variables as parameters

The compiler gains an optional `bound` mapping from variable name to a node id, relationship
id, or scalar. When a pattern references a bound variable, the compiler adds
`alias.id = ?` with that value instead of opening a new join. The executor runs the stage
once per input row:

```
bindings = [{}]
for stage in plan.stages:
    bindings = run(stage, bindings)     # each input row seeds one SQL execution
```

The SQL text depends only on the pattern shape and the set of bound variable names, so the
compiler caches compiled statements per (stage, bound-name set) and only the argument tuple
changes per row.

Rationale: this reuses the existing compiler, keeps predicate pushdown and index use, and
avoids building a correlated join across stages. The cost is one SQL execution per input row
for a stage that follows a `WITH` or `OPTIONAL MATCH`. Fusion removes that cost for
consecutive mandatory matches.

Alternative rejected: compile the whole pipeline into one SQL statement. That would require
modeling aggregation stages, optional joins, and scope resets in SQL, and would duplicate the
semantics the Python executor already implements.

### D5: `OPTIONAL MATCH` is a left join over the stage result

For each input row the optional stage runs like a normal match. Zero matches produce one
output row: the input bindings unchanged, plus `None` for every variable the stage would
have introduced. One or more matches produce one output row per match. The stage's `WHERE`
is evaluated inside the stage, so it filters matches, never input rows.

The analyzer records `introduced: frozenset[str]` per optional stage. The set gives the
executor the names to null and gives the analyzer the variable kinds for later stages.
Null values then flow through the existing value and expression rules: property access on
`None` yields `None`, and `WHERE` accepts only `True`, so a null never satisfies a filter.

Alternative rejected: implement `OPTIONAL MATCH` by rewriting to `UNWIND`-style expansion.
No `UNWIND` exists, and the left-join loop is simpler and matches the spec directly.

### D6: `WITH` reuses the return pipeline as a row transformer

`WITH` and `RETURN` share one implementation:

```
project -> aggregate (if needed) -> distinct -> order -> skip/limit
```

The difference is what happens to the result. `RETURN` produces the final `QueryResult`;
`WITH` produces a new binding list keyed by the projected names and continues. A projected
variable keeps its `Node`, `Relationship`, or `Path` snapshot; a scalar alias becomes an
ordinary value. Scope after the stage is exactly the projected names, and the analyzer
records their kinds so later stages can validate `a.designation` but reject `b`.

Rules:

- A non-variable item must have an alias; otherwise the output name would be an expression
  string that later stages cannot reference. The analyzer raises `QuerySemanticError`.
- Duplicate output names are rejected, as in `RETURN`.
- `WHERE` after `WITH` sees the projected scope and may reference an aggregate alias.
- `ORDER BY` resolves aliases first, then expressions in the projected scope; `SKIP` and
  `LIMIT` apply to the stage output.

Alternative rejected: require every `WITH` item to be a bare variable. That would force a
second `MATCH` for aggregates and defeat the stage's purpose.

### D7: Quantified relationships are a property of the relationship pattern

`RelationshipPattern` gains `min_hops: int | None` and `max_hops: int | None`. Both are
`None` for an ordinary relationship; both are integers for a quantified one. The parser
accepts:

```
[TYPE]                 ordinary, exactly one hop
[TYPE*n]               exactly n
[TYPE*n..m]            between n and m
[TYPE*0..m]            zero through m
[*n], [*n..m]          anonymous quantified relationship
```

A bare `*` or `*n..` parses but leaves the upper bound unset; the analyzer rejects it with a
semantic error because an embedded engine must not explore an unbounded trail space. Bounds
are validated as non-negative integers with `n <= m`. A relationship variable on a
quantified pattern gets a new `VariableKind.RELATIONSHIP_LIST`; it may be projected, passed
to `size`, and included in a path, but `type(...)` and property access reject it.

Alternative rejected: desugar `*1..3` into three fixed patterns joined by a union. That
would multiply the AST and the SQL, duplicate property predicates, and still need explicit
relationship-uniqueness enforcement.

### D8: Patterns containing quantifiers run on a bounded in-memory pattern engine

A match stage has two execution modes:

```
stage has no quantified relationship  ->  SQL pattern set (D3, D4)
stage has a quantified relationship   ->  Python pattern engine over a captured region
```

The Python engine:

1. Selects candidate start nodes for the first node pattern using the existing indexed
   node predicates (labels, property map, or a bound variable from an earlier stage).
2. Captures the region reachable from each candidate with `TraversalCapture` in `BOTH`
   direction, all types, bounded by the sum of the relationship-position maxima in the path
   (a fixed position contributes one).
3. Walks the path positions depth-first over the snapshot, applying each position's
   direction, types, property map, and node pattern; carries the set of used relationship
   ids so the path stays relationship-unique; prunes below `min_hops` and above `max_hops`.
4. Emits one binding per trail, including the relationship list for a quantified relationship
   variable and a `Path` for a path variable.

Patterns in the same stage that share variables are joined in Python on those variables;
patterns that share none form the cartesian product. A variable bound by an earlier stage
filters the candidate set instead of being re-bound.

Rationale: correctness first. Relationship uniqueness across a path that mixes quantified
and fixed positions is easy to enforce on one in-memory walk, and the bounded region reuses
traversal code that is already tested against diamond, cycle, parallel, and self-loop
fixtures. The SQL path stays the fast path for the overwhelmingly common fixed pattern.

Alternative rejected: recursive SQL CTE. Relationship uniqueness would need a per-path set
of relationship ids encoded into the CTE, which SQLite cannot express cheaply; the resulting
statement would be harder to read than the Python walk.

Alternative rejected: hybrid SQL for fixed runs between quantified segments. It saves work
on selective fixed hops but multiplies query executions per partial trail and complicates
uniqueness. Deferred until measurements justify it.

### D9: Relationship uniqueness spans the whole matched path

Both engines carry one used-relationship set for a path. The SQL engine adds
`alias.id NOT IN (...)` predicates for fixed hops that follow a quantified segment; the
Python engine checks the set at every hop. Nodes may repeat. This matches the existing
`paths()` contract rather than inventing a second set of traversal semantics.

### D10: Writes stay trailing and keep their cardinality rule

The analyzer still requires every write clause to follow every read stage. Mutations
therefore run once, after the stage pipeline produces its final bindings, through the
existing `MutationExecutor`. Deduplication stays per statement, `RETURN` still sees created
bindings and pre-deletion snapshots, and the `BEGIN IMMEDIATE` / savepoint boundaries do not
change.

A `WITH` before a write is allowed and simply shapes the input rows. A `WITH` after a write
is rejected by the clause-order rule. This keeps the mutation contract unchanged and avoids
redefining when a created entity becomes visible to a later read stage.

### D11: `explain` reports stage by stage

`Graph.explain` keeps its signature and return type. For each plan stage it collects the
`EXPLAIN QUERY PLAN` lines of the compiled SQL, concatenated in stage order. For a stage run
by the Python engine it reports the start-node selection plan plus one synthetic line naming
the quantified bounds, because SQLite cannot explain a Python traversal. For a statement
with no matching stage it returns an empty tuple, as today.

Stage inputs that are only known at execution time (after `WITH`) are compiled for planning
with placeholder bound values. SQLite's access-path choice does not depend on the value, so
the report stays representative.

Alternative rejected: return a richer plan object. That would change the public return type
for a diagnostic API and is not needed for this change.

### D12: Error classification follows the existing hierarchy

- Malformed quantifier syntax (`*..`, `*a`, missing integer) → `QuerySyntaxError` with
  position.
- Unbounded or inverted bounds, quantified variable used as a single relationship, duplicate
  path variable, missing `WITH` alias, unbound variable in a later stage → `QuerySemanticError`
  before execution.
- Clause-order violations (read after write, `WITH` last, missing `RETURN` on a read) →
  `QuerySyntaxError`, matching how the current parser rejects clause shapes.
- Runtime expansion failures (storage read failure) → `QueryExecutionError`; raw SQLite
  exceptions never escape.

### D13: The transaction and snapshot model is untouched

Every stage runs inside the statement's existing transaction. For a read statement that is
the deferred `BEGIN`; for a write statement it is `BEGIN IMMEDIATE`; inside an explicit
transaction it is the caller's transaction. Because all stages of one statement share that
transaction, the "all stages share one snapshot" scenario needs no new locking.

## Risks / Trade-offs

- **Pipeline refactor regresses existing behavior** → Introduce the stage model in a
  behavior-preserving step first, with the full existing suite green before any new syntax
  is enabled. Keep the flattened `Plan.operators` for single-stage statements.
- **Quantified expansion explodes** → The upper bound is mandatory, the region is bounded by
  the sum of maxima, and trails are relationship-unique, so the search is finite. Document
  that a large bound over a dense region is expensive and that the bound is the caller's
  cost control.
- **A stage after `WITH` executes one SQL statement per input row** → Fuse consecutive
  mandatory matches, cache compiled SQL by shape, and document the cost. Aggressive
  stage-to-SQL fusion is a future optimization, not a requirement.
- **Python and SQL engines disagree on a corner case** → Run a conformance matrix that
  evaluates the same fixed pattern through both paths (for example, by feeding it through a
  stage that forces the Python engine) and compares rows.
- **Uniqueness across mixed quantified and fixed hops is subtle** → The shared used-set
  lives in one place per engine; tests cover diamond, directed cycle, parallel relationships,
  and self-loop for both declared bounds.
- **Scope leaks after `WITH`** → Scope is rebuilt from projected names only, and the
  analyzer records kinds per stage. Tests assert both a surviving variable and a rejected
  one.
- **`explain` becomes misleading for expanded stages** → Emit the start-node plan and an
  explicit expansion line instead of pretending SQL plans the traversal.

## Migration Plan

No schema, file-format, or dependency migration. This is a minor release: statements that
were previously rejected now execute, and no previously accepted statement changes meaning.
The changelog records the expanded dialect under `[Unreleased]`. Rolling back is a code
revert; databases written by the change are identical to databases written before it.

## Open Questions

- Whether to push `SKIP`/`LIMIT` into the compiled SQL of a stage. Deferrable; it changes
  performance only, not semantics or the task breakdown.
- Whether a later change should fuse a `WITH` stage into the following SQL. Deferrable for
  the same reason.
