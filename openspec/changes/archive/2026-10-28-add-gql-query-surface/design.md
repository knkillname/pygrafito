# Design

## Context

See `proposal.md` — Why. The current frontend already has a recursive-descent parser, a frozen AST,
a semantic analyzer, a SQL compiler for simple pattern predicates, a residual expression evaluator,
and a materialized result pipeline. The expression, subquery, and set-operation rows are listed as
gated in `docs/reference/gql-profile.md` but are rejected by the parser today.

The existing architecture matters for this change:

- `Expression` is a closed union in `ast.py`; every expression consumer uses `isinstance` dispatch.
- `SemanticAnalyzer` produces `Analysis`, and `PlanBuilder` turns its operations into a linear plan.
- `QueryExecutor` owns one connection, one transaction, one budget tracker, and one execution
  snapshot per statement.
- `ExpressionEvaluator` has no execution context beyond scalar functions, so subqueries need a
  narrow callback rather than direct access to the connection.
- The GQL profile consistency test requires every `supported` matrix row to have at least one
  corpus case.

## Goals / Non-Goals

**Goals:**

- Add all three gated families without weakening existing evaluation, grouping, write, budget, or
  snapshot behavior.
- Keep the parser, analyzer, planner, executor, documentation, and profile aligned in one change.
- Preserve the existing public `Graph.query`, `Graph.prepare`, `Transaction.query`, and result APIs.
- Keep runtime dependencies standard-library only.

**Non-Goals:**

- No path-engine work: match modes, grouped quantified paths, path search, or open-ended traversal.
- No path indexing. Path values are consumed through `nodes`, `relationships`, and `length`.
- No `CALL { ... }`, write subqueries, `INTERSECT ALL`, `EXCEPT ALL`, whole-map assignment,
  `exists(n.prop)`, regex predicates, temporal values, or catalog operations.
- No streaming result API.

## Decisions

### Land one change with three ordered implementation phases

The expression surface lands first, subqueries second, and set operations third. Subqueries depend
on the expression AST and evaluator; set operations depend on both the projection contract and the
subquery-aware execution path. One change keeps the profile and corpus from passing through
intermediate inconsistent states.

### Extend the AST with explicit nodes

Add `Case`, `MapLiteral`, `ListAccess`, `ListSlice`, `ListComprehension`, and `Subquery` to the
`Expression` union. Add `With.star`. Add `CompoundStatement` as a top-level parsed query with
`terms`, `operators`, and compound ordering/pagination. Existing `Statement` remains the linear
query node; `Parser.parse_statement` returns a typed union of the two.

The nodes stay behavior-oriented: they carry the parsed structure, not SQL or execution details.
`ListAccess` and `ListSlice` are separate nodes so normalization and error positions stay clear.

### Parser strategy

- Add `WHEN`, `THEN`, `ELSE`, `END`, `UNION`, `INTERSECT`, and `EXCEPT` to the reserved keyword
  catalog. Add `||` as an operator before the existing `|` punctuation.
- `CASE` parses a simple form when the next token can start a value expression and a searched form
  when it starts with `WHEN`.
- Map literals use the existing property-key parser, reject duplicate keys at parse time, and
  produce a `MapLiteral`.
- List post-processing parses `[index]`, `[start:end]`, `[:end]`, `[start:]`, and `[:]`. A bracket
  expression whose first token is an identifier followed by `IN` is a comprehension instead of a
  list literal.
- `EXISTS` and `COUNT` remain ordinary identifiers. A following `{` selects a query expression;
  `COUNT(...)` continues to parse as the aggregate function. This avoids reserving common names.
- `WITH *` is a star-only projection. `WITH DISTINCT *` is accepted; mixing `*` with other items is
  a syntax error.
- A compound query parses one linear term, then a set operator and another linear term, until the
  input ends. A term's final `RETURN` must not carry `ORDER BY`, `OFFSET`, or `LIMIT`; the parser
  leaves those clauses for the compound. A non-final `RETURN` before `NEXT` keeps its existing
  ordering and pagination. A single-term query keeps today's behavior by attaching the trailing
  clauses to that term's result.

### Expression semantics

- `CASE`: simple `CASE` uses dialect equality and null never matches; searched `CASE` selects the
  first true predicate. Branches are lazy. A missing `ELSE` is null. Branch values are not coerced.
- Map literals: keys are static identifiers/backtick names, values evaluate left to right, and the
  result is a read-only mapping. Maps are equality-comparable and groupable through the existing
  canonical key, but `Values.ordering_key` continues to reject maps.
- List indexing/slicing: zero-based, negative indexes from the end, out-of-range index null,
  end-exclusive slices clamped to the list. Null list yields null; non-list target is an error.
- List comprehensions: evaluate the source once, bind the loop variable locally, reject shadowing,
  filter true predicates, emit either the element or the projected expression. Null source yields
  null; non-list source is an error.
- String concatenation: `||` requires string operands; `+` remains numeric except when both operands
  are statically or dynamically strings. Mixed string/number is an error, and null propagates.
- Path functions: `nodes` and `relationships` return the path snapshots in traversal order;
  `length` counts relationships. Null path yields null; non-path is an error.
- Extended functions: add signatures and handlers for `range`, `head`, `last`, `tail`, `reverse`,
  `split`, `substring`, `replace`, `toBoolean`, `round`, `ceil`, and `floor`. The spec fixes the
  edge cases: empty delimiters, zero steps, negative positions, and invalid boolean text.
- `WITH *`: the analyzer expands the current scope in introduction order, preserving each
  variable's kind and snapshot, then applies the normal `WITH` filter, distinct, ordering, and page
  behavior.

### Map/list values versus stored property values

Map literals and list comprehensions produce query values, including values inside result rows.
They do not relax the stored-value contract. A map or nested list assigned to a property is still
rejected by write value validation, and `INSERT`/`SET` still commit nothing when that happens.

### Subquery analysis and execution

Add a `Subquery` expression carrying the inner clause list and a kind (`EXISTS` or `COUNT`). The
inner body is a read-stage block: `MATCH`, `OPTIONAL MATCH`, `FILTER`, `LET`, `FOR`, and `WITH` are
allowed; `RETURN`, `FINISH`, `NEXT`, `YIELD`, and every write clause are rejected. The body must
contain at least one row source.

The semantic analyzer runs a child analysis seeded with the outer variable kinds. Outer names are
visible and correlate the inner pattern; new inner names are local and are discarded after the
subquery. A `LET`/`WITH` alias that would shadow an outer name is rejected. The child's parameters
are merged into the outer statement's parameter set.

Execution uses a `SubqueryRunner` protocol injected into `ExpressionEvaluator`; the executor
implements it with the current connection, snapshot source, parameter mapping, and budget tracker.
`EXISTS` may stop after the first inner row; `COUNT` runs the full inner row set. The runner never
opens a transaction or a savepoint and never creates a second budget.

### Set operation analysis and execution

Add `CompoundStatement` and a `CompoundPlan` that wraps the per-term `Plan` objects. Analysis
validates every term as read-only, requires a final `RETURN`, rejects `FINISH`, `RETURN NO
BINDINGS`, and operand-level ordering/pagination, and checks column count and names against the
first term. The first term owns result columns and parameters are the union of all terms.

Execution opens one transaction and one tracker for the whole compound. Each term runs its stages
and projection against the same snapshot, with its own input binding `[{}]`. Set combination is
left-associative:

- `UNION ALL` appends rows.
- `UNION` appends then removes duplicate rows.
- `INTERSECT` keeps rows present in both sides.
- `EXCEPT` removes rows present in the right side.

Row equality uses the existing canonical value key, so `36` and `36.0` collide as dialect equality
requires. After combination, compound `ORDER BY` resolves output column names from the first term,
then `OFFSET` and `LIMIT` apply. Without `ORDER BY`, result order remains unspecified; the
implementation preserves first-seen order for deterministic tests.

### Compiler and evaluator boundaries

`PushdownAnalyzer` continues to push only simple property comparisons into SQL. Any expression it
cannot prove is a simple predicate becomes a residual and is evaluated by `ExpressionEvaluator`.
`ConstantEvaluator` is extended for constant map/list/CASE forms used by pattern property maps;
subqueries are never constant. `GroupEvaluator` learns the new expression nodes so aggregates inside
`CASE`, maps, list expressions, and subqueries evaluate over the group representative or the group
as appropriate.

### Prepared queries and results

`PreparedQuery` accepts either a linear `Plan` or a `CompoundPlan`. `columns` comes from the first
operand for a compound, `is_write` is false, and `parameters` is the union of all operands.
`QueryResult` is unchanged: rows may already contain mappings and lists, and a compound read has a
zero mutation summary.

### Profile and documentation updates

The profile page keeps the existing matrix rows but changes the affected statuses from `gated` to
`supported`, replaces the follow-up owner with `—`, and names the new corpus cases. The gated table
shrinks to the path-engine rows. The query-language reference gains sections for each new form,
updates the grammar summary, and removes the affected entries from the gated table. Tours demonstrate
the new surface and no longer avoid map literals or expression forms.

### Reserved keywords and compatibility

Reserving `WHEN`, `THEN`, `ELSE`, `END`, `UNION`, `INTERSECT`, and `EXCEPT` is the only breaking
change. Existing variables or aliases using those spellings become invalid unless backtick-quoted.
The changelog and migration guidance state the exact migration. `EXISTS` and `COUNT` stay
identifiers, so existing variable names using them remain valid.

## Risks / Trade-offs

- **Parser ambiguity between map literals and pattern property maps** → Keep property-map parsing in
  the pattern grammar and map-literal parsing in the expression primary; never reuse one parser for
  both contexts.
- **`EXISTS`/`COUNT` versus function calls** → Use `{` lookahead for query expressions and `(` for
  function calls; add parser tests for both.
- **Set-operation ordering ambiguity** → Reject operand-level final ordering; apply trailing
  ordering only to the compound and test single-term backward compatibility.
- **Subquery budget or snapshot leaks** → Pass the existing tracker and snapshot source through the
  runner; test budget failure and concurrent-write snapshots.
- **Map/list values accidentally stored** → Keep write value validation unchanged and add a focused
  rejection test for map/nested-list properties.
- **Extended function edge cases drift from the docs** → Put every edge case in the delta spec and
  mirror it in corpus or focused tests.
- **Profile/corpus drift** → Update matrix statuses, feature IDs, and corpus cases in the same task
  group; `tests/test_gql_profile.py` is the guard.
- **Reserved-word breakage** → Call it out as breaking, add a changelog migration note, and test
  backtick-quoted variables using the new spellings.

## Migration Plan

1. Land the AST, parser, semantic, evaluator, and executor changes with focused tests.
2. Add corpus cases and flip the affected profile rows to `supported`.
3. Update the query-language reference, grammar summary, tours, and changelog.
4. Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; verify coverage stays at or
   above 80% and the profile consistency test passes.
5. Archive and sync the delta. There is no database or snapshot format migration.

Rollback is a normal revert: no stored data changes, and the previous release continues to reject
the new forms as gated.

## Open Questions

None.
