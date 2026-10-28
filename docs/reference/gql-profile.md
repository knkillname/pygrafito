# GQL profile

This page is the target language profile for `pygrafito`. It defines the canonical GQL surface,
the compatibility aliases and constructs, the pygrafito extensions, the path-mode and query-budget
policy, the 1.0 release gate, and how conformance is claimed. It is the contract for the
query-language changes that lead to 1.0.

:::{note}
This page is both the language profile and its conformance status board. Status describes target
membership and implementation state separately:

- **supported** — implemented in the current release and covered by at least one conformance
  corpus case.
- **gated** — in the 1.0 target profile, not implemented yet. The profile names the follow-up
  change that implements it.
- **deferred** — post-1.0 language direction, not part of the 1.0 profile or promise.
- **out of profile** — a rejected non-goal.

The current release contains `supported`, `gated`, and `out of profile` rows. There are no
`deferred` rows in the 1.0 target; the status is reserved for post-1.0 proposals. The
[query-language reference](query-language.md) describes the executable dialect only.
:::

## Current status

The current release implements the supported rows below. The 1.0 target adds the remaining gated
path rows. Gated constructs do not execute in this release; the parser or semantic analyzer rejects
them with a positioned query error, and the matrix names the follow-up change.

| Area | Current release | 1.0 target |
| --- | --- | --- |
| Pattern matching | `MATCH`, `OPTIONAL MATCH`, multiple patterns, repeated variables, inline `WHERE`, path variables | Same surface |
| Data modification | `INSERT`, `SET`, `REMOVE`, `DELETE`, `DETACH DELETE`, `NODETACH DELETE`; `CREATE` alias; `MERGE` extension | Same surface |
| Iteration and filtering | `FOR`, `UNWIND` alias, `FILTER`, stage `WHERE` alias, `MATCH ... WHERE` | Same surface |
| Binding, composition, and grouping | `LET`, `NEXT` with `YIELD`, `FINISH`, `GROUP BY`, `WITH` extension, implicit grouping | Same surface |
| Projection, ordering, and pagination | `RETURN`, `RETURN DISTINCT`, `RETURN ALL`, `RETURN *`, `RETURN NO BINDINGS`; `ORDER BY`, `OFFSET`, `SKIP`, `LIMIT` | Same surface |
| Quantifiers | Closed `{n}`, `{m,n}`, `{,n}`; legacy `*n`, `*n..m`, `*0..m` | Closed forms plus open-ended `{m,}`, `*`, `+`, and legacy `*n..` |
| Path modes | `WALK` default; `TRAIL`, `SIMPLE`, `ACYCLIC` explicit | Same modes plus match modes, grouped quantified paths, and path search |
| Expressions | Current operators, property access, list literals, `CASE`, map literals, list indexing and slicing, list comprehensions, string concatenation, path functions, core and extended scalar functions, aggregates | Same surface |
| Subqueries | Read-only `EXISTS { ... }` and `COUNT { ... }` | Same surface |
| Set operations | `UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT` | Same surface |
| Query budget | Expansion, row, and optional time counters with per-query override | Same surface |
| Out of profile | Rejected with an explicit query error | Rejected with an explicit query error |

The runnable examples in `README.md`, the quickstart, and the guides use the canonical spellings
where the release supports them; compatibility aliases appear only in the migration guidance.

## The five tiers

Every supported or gated construct belongs to exactly one tier. Rejected forms are invalid
combinations, not separate tiers.

| Tier | Meaning | Reader treatment |
| --- | --- | --- |
| Canonical GQL | The documented GQL spelling. | Use it first; new examples use it where the current release supports it. |
| Synthetic alias | A different spelling with identical semantics. | Accepted for compatibility; not advertised as canonical. |
| Compatibility construct | A legacy spelling with its own legacy default. | Accepted and documented beside the canonical form. |
| pygrafito extension | A supported feature with no GQL equivalent. | Documented as pygrafito-only; never claimed as GQL. |
| Out of profile | A GQL or pygrafito feature that is not supported. | Rejected with an explicit error, never ignored. |

A construct that is not listed on this page is out of profile. The query language rejects it with
an explicit error rather than silently ignoring it.

## Canonical surface

The canonical spellings follow ISO/IEC 39075 (GQL). The table groups the surface by purpose; the
[conformance matrix](#conformance-matrix) records the implementation and coverage status of each
entry.

| Area | Canonical spelling | Notes |
| --- | --- | --- |
| Matching | `MATCH`, `OPTIONAL MATCH` | Comma-separated path patterns and `WHERE` are in scope. |
| Data modification | `INSERT`, `SET`, `REMOVE`, `DELETE`, `DETACH DELETE` | `NODETACH DELETE` is the explicit non-detaching form. |
| Iteration | `FOR value IN list [WITH ORDINALITY index]` | `WITH OFFSET index` is the GQL synonym. |
| Filtering | `FILTER`, `MATCH ... WHERE`, inline element `WHERE` | `FILTER WHERE` is accepted as the explicit form. |
| Binding | `LET name = expression` | Adds a binding without dropping the current scope. |
| Composition | `NEXT [YIELD column [AS alias] [, ...]]` | Starts the next segment from the preceding `RETURN`; without `YIELD` every column passes. |
| Grouping | `GROUP BY key [, ...]`, `GROUP BY ()` | Explicit grouping; implicit grouping is an extension. Expression keys are an extension. |
| Projection | `RETURN`, `RETURN DISTINCT`, `RETURN ALL`, `FINISH` | `RETURN *` is canonical; `RETURN NO BINDINGS` is a pygrafito extension. |
| Ordering and pagination | `ORDER BY`, `OFFSET`, `SKIP`, `LIMIT` | `ASC`/`ASCENDING`, `DESC`/`DESCENDING`, and `NULLS FIRST`/`NULLS LAST` are in scope. |
| Quantifiers | `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, `+` | Placement follows the GQL path-pattern grammar. Open upper bounds are gated. |
| Labels | Conjunction, disjunction, negation, wildcard | Node and edge label expressions; `IS` is accepted in place of `:`. |
| Edge directions | `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | `-` is any direction; `~` is undirected only. |
| Comments | `//`, `--`, `/* ... */` | `--` is a GQL line comment; legacy double-dash arrows are an alias. |
| Path variables | `p = <path pattern>` | Paths expose their nodes and relationships in traversal order. |
| Parameters | `$name` | Bound as data, never as identifiers or SQL text. |
| Path modes | `WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC` | `WALK` is the canonical default, bounded by the query budget. |
| Expressions | `CASE`, map literals, list indexing and slicing, list comprehensions, string concatenation, function calls | Supported. |
| Path functions | `nodes(path)`, `relationships(path)`, `length(path)` | Supported. |
| Subqueries | `EXISTS { ... }`, `COUNT { ... }` | Read-only, correlated or uncorrelated. |
| Set operations | `UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT` | Read-only compound queries. |
| Path search | `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k` | In the 1.0 target; gated in the current release. |
| Match modes | `DIFFERENT EDGES`, `REPEATABLE ELEMENTS` | In the 1.0 target; gated in the current release. |
| Grouped quantified paths | Repetition of a grouped path pattern | Syntax and semantics are owned by `define-gql-path-semantics`; gated. |
| Open-ended quantifiers | `{m,}`, `*`, `+`; legacy `*n..` | In the 1.0 target; gated until lazy traversal lands. |

Label expressions use `&` for conjunction, the vertical-bar operator for disjunction, `!` for
negation, and `%` for the wildcard. For example, `(:Program&:ISO)` matches a node carrying both
labels, and `(:Program|:Agent)` matches either one.

Canonical example:

```text
// Canonical GQL.
INSERT (n:Program {designation: 'Quorra'})
MATCH (n:Program)
FILTER n.cycles > 36
RETURN n.designation AS name
```

## Synthetic aliases

A synthetic alias is a pure spelling change. It has exactly the same semantics as its canonical
form.

| Alias | Canonical | Scope |
| --- | --- | --- |
| `CREATE` | `INSERT` | Data patterns only. `CREATE GRAPH` is out of profile. |
| `UNWIND list AS value` | `FOR value IN list` | Row expansion. |
| `WHERE` after a read stage | `FILTER` | Stage-level filtering. `WHERE` inside `MATCH` and element patterns is canonical. |
| `-->`, `<--` | `->`, `<-` | Pattern arrows. `--` is a comment, not an edge. |
| `:A:B` | `:A&B` | Node label conjunction. |
| `+` on string operands | Canonical string concatenation | Compatibility alias for string operands only; numeric operands keep arithmetic `+`. |

The canonical string concatenation operator is `||`. The `+` alias applies only to string operands;
numeric operands keep arithmetic `+` and mixed operands are rejected.

`SKIP` is not an alias: GQL defines both `SKIP` and `OFFSET` as canonical synonyms.

The legacy double-dash arrows collide with the GQL `--` line comment. The frontend change must
define the disambiguation so a `--` comment is never silently reinterpreted as an edge, and a
legacy `-->` or `<--` arrow is never truncated into a comment.

## Compatibility construct: the legacy quantifier

The legacy Cypher quantifier is a compatibility construct. It keeps its Cypher default of
relationship-unique trails. The canonical closed forms are supported; the open forms are gated.

| Form | Default path mode | Status | Notes |
| --- | --- | --- | --- |
| `*n`, `*n..m`, `*0..m` | `TRAIL` | supported | Cypher-compatible. The upper bound is finite. |
| `*n..` | `TRAIL` | gated | Legacy open upper bound; lands with `add-gql-unbounded-traversal`. |
| `{n}`, `{m,n}`, `{,n}` | `WALK` (target) | supported | GQL canonical closed quantifiers. |
| `{m,}`, `*`, `+` | `WALK` (target) | gated | GQL canonical open forms; land with `add-gql-unbounded-traversal`. |
| Explicit `WALK`, `TRAIL`, `SIMPLE`, or `ACYCLIC` | The explicit mode | supported | Overrides both defaults. |

The effective mode for a path is resolved in this order:

```text
mode(path) =
    explicit per-path mode
  | explicit clause-level mode
  | TRAIL    if the path contains a legacy *n..m quantifier
  | WALK     otherwise
```

Mixing a legacy quantifier and a `{n,m}` quantifier in one path without an explicit mode is a
semantic error. The profile does not guess which default the author intended.

```text
MATCH (a)-[:ALLIES_WITH*1..3]->(b)          -- legacy: TRAIL
MATCH (a)-[:ALLIES_WITH{1,3}]->(b)          -- canonical: WALK
MATCH WALK (a)-[:ALLIES_WITH*1..3]->(b)     -- explicit WALK wins
MATCH TRAIL (a)-[:ALLIES_WITH{1,3}]->(b)    -- explicit TRAIL wins
```

The canonical closed forms require an explicit upper bound. The open upper bound (`*`, `+`,
`*n..`, and `{m,}`) is gated for 1.0 and names `add-gql-unbounded-traversal`. It is not deferred.

## Path modes

| Mode | Rule | Profile status |
| --- | --- | --- |
| `WALK` | Repeated nodes and relationships are allowed. | Canonical default; supported while the query budget is enforced. |
| `TRAIL` | A relationship may not repeat within one path; nodes may repeat. | Supported; also the default for the legacy quantifier. |
| `SIMPLE` | Nodes may not repeat, except that the start and end may be the same. | Supported. |
| `ACYCLIC` | No node may repeat. | Supported. |
| `DIFFERENT EDGES` | Distinct edge bindings within a match. | Gated; lands with `add-gql-match-modes`. |
| `REPEATABLE ELEMENTS` | Elements may repeat within a match. | Gated; lands with `add-gql-match-modes`. |
| Grouped quantified paths | Repetition of a parenthesized path pattern. | Gated; lands with `add-gql-grouped-quantified-paths`. |
| Path search | `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`. | Gated; lands with `add-gql-path-search`. |
| Open-ended quantifiers | `*`, `+`, `*n..`, and `{m,}` in any mode. | Gated; lands with `add-gql-unbounded-traversal`. This also enables unbounded traversal; `Unbounded WALK` is not a separate construct or matrix row. |

The path changes depend on `define-gql-path-semantics`, which owns the interaction between path
modes, match modes, quantifiers, and search prefixes.

The Python `paths()` API remains a relationship-unique, bounded trail enumerator. It does not
follow the query language's `WALK` default. Use `paths()` when you want a trail, and `MATCH TRAIL`
when you want a trail in the query language.

## Query budget

`WALK` is not enabled until the query budget exists. The budget is a safety valve for cyclic
graphs, dense fan-out, and cartesian products.

| Knob | Counts | Starting default | Notes |
| --- | --- | --- | --- |
| `max_expansions` | Each relationship expansion in a walk. | 1,000,000 | Tune with the benchmark. |
| `max_rows` | Each intermediate binding produced by a stage. | 100,000 | Tune with the benchmark. |
| `max_seconds` | Wall-clock time between expansion steps. | Disabled (opt-in) | Optional; tests should prefer deterministic counters. |

The policy is:

- A per-query override wins over the graph default.
- Exceeding either counter raises a query execution error that names the counter and the limit.
  No partial result is returned.
- A write statement that exceeds the budget rolls back entirely. The graph handle remains usable.
- `LIMIT` bounds the result, not the traversal work, in the first implementation. The budget is
  the guarantee; pushing `LIMIT` into the pattern engine is a follow-up optimization.
- The budget does not change the Python `paths()` API, which already requires a maximum depth.

The budget is enforced for every execution. `Graph.open` sets the graph default, `Graph.query`,
`Transaction.query`, and `PreparedQuery.execute` accept a per-execution override, and a counter
set to `None` is unlimited. The `WALK` row in the matrix is supported while this enforcement
holds.

## Extensions

These features have no GQL equivalent in the 2024 standard. The table records whether each is
supported today or gated for 1.0. They are never claimed as GQL.

| Extension | Status | Why it stays | Canonical alternative |
| --- | --- | --- | --- |
| `MERGE` with `ON CREATE SET` and `ON MATCH SET` | supported | Upsert is essential for imports and sync. | None in GQL 2024. |
| `WITH` projection, aggregation, and pagination | supported | A compact scope-reset stage. | `LET` + `NEXT` + `GROUP BY`. |
| Implicit grouping | supported | Compatibility with the transitional dialect and concise queries. | `GROUP BY`. |
| Expression grouping keys | supported | Concise grouping on a computed value. | `GROUP BY` a direct variable. |
| `RETURN NO BINDINGS` | supported | Zero-column debugging and internal result shape. | `FINISH`, or `RETURN` with the columns you need. |
| `type()` | supported | Returns the first sorted relationship label. | `LABELS()` returns the full sorted label list. |
| Query budget | supported | Bounded execution for cyclic and dense graphs. | No GQL equivalent. |
| `WITH *` | supported | A scope-preserving projection shorthand for the `WITH` extension. | `WITH` with explicit columns. |

Supported extensions remain part of the compatibility surface. Gated extensions are part of the
1.0 target but do not execute in the current release. They are documented on this page and labeled
pygrafito-only wherever they appear.

## Out of profile, gated, and deferred

`Out of profile` and `gated` are different. An out-of-profile construct is rejected and is not a
1.0 promise. A gated construct is in the 1.0 target but is not implemented yet. `Deferred` is
post-1.0 direction and is not used for any 1.0 target row.

### Out of profile

Out of profile means the construct is rejected with an explicit query error. It is a non-goal for
1.0, not a deferred backlog item. Promoting one requires a separate proposal.

| Construct | Why it is out | Error contract |
| --- | --- | --- |
| Catalog statements (`CREATE GRAPH`, `DROP GRAPH`, `INSERT GRAPH`, schemas) | `pygrafito` is a single embedded graph, not a catalog. | A positioned query error before execution; no statement text runs. |
| Graph types | There is no schema or type layer. | A positioned query error before execution. |
| Sessions | There is no server or session state. | A positioned query error before execution. |
| Procedures (`CALL name(...)`) | There is no catalog or procedure registry. | A positioned query error before execution. |
| In-language transactions (`START TRANSACTION`, `COMMIT`, `ROLLBACK`) | The Python `Graph` and `Transaction` APIs own transaction boundaries. | A positioned query error before execution. |
| `SELECT` | The query surface is pattern-based, not the SQL/PGQ-style `SELECT` surface. | A positioned query error before execution. |
| Full temporal values (`DATE`, `TIME`, `TIMESTAMP`, `DURATION`) | The stored value format does not have temporal types yet. | A positioned query error before execution. |
| `CALL { ... }` | Cypher-only subquery form. Use read-only `EXISTS { ... }` or `COUNT { ... }` when they land, or separate statements. | A positioned query error before execution. |
| Whole-map assignment (`SET n = {...}`, `SET n += {...}`) | Cypher-only convenience form. Assign or remove properties individually. | A positioned query error before execution. |
| `exists(n.prop)` | Cypher-only function form. Use `n.prop IS NOT NULL`. | A positioned query error before execution. |
| Regex predicates | Cypher-only regular-expression matching. Use `STARTS WITH`, `ENDS WITH`, and `CONTAINS` for literal predicates. | A positioned query error before execution. |
| `shortestPath()`, `allShortestPaths()` | Cypher-only path functions. Use `Graph.shortest_path`, or the target path-search prefixes when they land. | A positioned query error before execution. |
| Servers and drivers | The library is embedded; there is no network protocol or driver layer. | No query API exists; query text that attempts it is rejected. |
| Clustering, authentication, and multi-tenancy | There is no server, account, or tenant layer. | No query API exists; query text that attempts it is rejected. |
| Multi-graph storage | One graph handle owns one database. | No query API exists; query text that attempts it is rejected. |
| Graph-algorithm APIs | Algorithms are Python helpers, not query constructs. | No query API exists; query text that attempts it is rejected. |
| Full Cypher compatibility | Cypher convenience forms are not the target language. | A positioned query error before execution. |
| Vector search | No vector index or distance function is in the profile. | A positioned query error before execution. |
| Full-text search | No full-text index or query syntax is in the profile. | A positioned query error before execution. |

### Gated for 1.0

A gated construct is in the 1.0 target but cannot execute in the current release. The matrix below
records the owner for each family. The [conformance matrix](#conformance-matrix) has the exact
feature rows.

| Gated surface | Follow-up change |
| --- | --- |
| `DIFFERENT EDGES`, `REPEATABLE ELEMENTS` | `define-gql-path-semantics`, then `add-gql-match-modes` |
| Grouped quantified paths | `define-gql-path-semantics`, `add-gql-unbounded-traversal`, then `add-gql-grouped-quantified-paths` |
| `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k` | `define-gql-path-semantics`, `add-gql-unbounded-traversal`, `add-gql-match-modes`, then `add-gql-path-search` |
| Open-ended quantifiers `*`, `+`, `{m,}`, and legacy `*n..` | `define-gql-path-semantics`, then `add-gql-unbounded-traversal` |

### Deferred

No matrix row is `deferred` in the 1.0 target. The status remains in the vocabulary for constructs
that are outside 1.0 but may be reconsidered later. A deferred construct is not a 1.0 promise and
does not appear in the gated table.

## Rejected forms

Rejected forms are invalid combinations of supported features, or unsupported operations that are
not separate matrix features. Each is rejected with a positioned query error before any statement
text executes. The test owner column records the current focused test; the 1.0 release gate adds
any missing rejection test before the gate can pass.

| Form | Why it is rejected | Error contract | Test owner |
| --- | --- | --- | --- |
| `MERGE` over a quantified pattern | `MERGE` matches one fixed-length pattern as a whole. | `QuerySemanticError` naming the quantified pattern. | `TestUnwindAndMergeAnalysis::test_merge_rejects_a_quantified_relationship` |
| `MERGE` over a path variable | A merged pattern must name one path, not bind a path value. | `QuerySemanticError` naming the path variable. | `TestUnwindAndMergeAnalysis::test_merge_rejects_a_path_variable` |
| `MERGE` over more than one pattern | `MERGE` matches one pattern as a whole. | `QuerySemanticError` naming the multiple patterns. | `TestUnwindAndMerge::test_merge_rejects_multiple_patterns` |
| `MERGE` over a relationship without one explicit label and the `-->` direction | The merged pattern must be unambiguous and create only directed relationships. | `QuerySemanticError` naming the missing label or direction. | `TestUnwindAndMergeAnalysis::test_merge_rejects_a_missing_type` and `test_merge_rejects_an_undirected_relationship` |
| `MERGE` that rebinds a relationship variable or changes a bound node | `MERGE` reuses bound anchors but does not rewrite them. | `QuerySemanticError` naming the bound element. | `TestUnwindAndMergeAnalysis::test_merge_rejects_a_bound_relationship` and `test_merge_rejects_changing_a_bound_node` |
| Mixing a legacy and a canonical quantifier in one path without an explicit mode | The two forms have different legacy defaults, so the profile refuses to guess. | `QuerySemanticError` naming the mixed quantifiers. | `TestPathModeResolution::test_mixed_quantifiers_are_rejected` |
| Catalog operations such as `INSERT GRAPH` and `CREATE GRAPH` | The library has one embedded graph and no catalog. | `QuerySemanticError` naming the catalog operation; no statement text runs. | 1.0 gate: add a focused parser test in `complete-gql-profile` |

## Construct inventory

This inventory classifies every canonical spelling, alias, compatibility form, extension, and
out-of-profile construct named on this page or in the query-language reference. The matrix row or
rejected form column is the owning feature. A `rejected form` status is an invalid combination from
the previous table, not a matrix status.

| Construct | Tier | Status | Matrix row or rejected form | Notes |
| --- | --- | --- | --- | --- |
| Statement, linear segments, `NEXT`, `YIELD` | Canonical GQL | supported | `NEXT` | `NEXT` without `YIELD` and write-only segments are Cypher-compatible behaviors. |
| `MATCH`, `OPTIONAL MATCH`, multiple comma-separated patterns, repeated variables, `MATCH ... WHERE`, `OPTIONAL MATCH ... WHERE` | Canonical GQL | supported | `MATCH` and `OPTIONAL MATCH` | Read stages and left joins. |
| `FOR ... IN`, `WITH ORDINALITY`, `WITH OFFSET` | Canonical GQL | supported | `FOR` with ordinality/offset | One-based and zero-based positions. |
| `FILTER`, `FILTER WHERE` | Canonical GQL | supported | `FILTER` | Keeps true predicates. |
| `UNWIND ... AS` | Synthetic alias | supported | `UNWIND` for `FOR` | Row expansion. |
| Stage `WHERE` after `WITH` | Synthetic alias | supported | Stage `WHERE` for `FILTER` | `MATCH ... WHERE` remains canonical inside the match stage. |
| `LET` | Canonical GQL | supported | `LET` | Row-wise bindings. |
| `FINISH` | Canonical GQL | supported | `FINISH` | Final no-result clause. |
| `GROUP BY`, `GROUP BY ()` | Canonical GQL | supported | `GROUP BY` | Explicit grouping. |
| Expression grouping keys | pygrafito extension | supported | `GROUP BY` | Example: `GROUP BY n.cycles + 0`. |
| `RETURN`, `RETURN ALL`, `RETURN DISTINCT`, `RETURN *` | Canonical GQL | supported | `RETURN` with `DISTINCT`/`ALL` or `*` | Projection and scope reset. |
| `RETURN NO BINDINGS` | pygrafito extension | supported | `RETURN NO BINDINGS` | Zero-column final result. |
| `ORDER BY`, `ASC`, `ASCENDING`, `DESC`, `DESCENDING`, `NULLS FIRST`, `NULLS LAST` | Canonical GQL | supported | `ORDER BY` with null ordering | Explicit null placement. |
| `OFFSET`, `SKIP` | Canonical GQL | supported | `OFFSET` and `SKIP` | Canonical synonyms, not aliases. |
| `LIMIT` | Canonical GQL | supported | `LIMIT` | Result bound only. |
| `INSERT` | Canonical GQL | supported | `INSERT` | Creates data patterns. |
| `CREATE` | Synthetic alias | supported | `CREATE` for `INSERT` | Data patterns only. |
| `MERGE`, `ON CREATE SET`, `ON MATCH SET` | pygrafito extension | supported | `MERGE` with conditional updates | Upsert extension. |
| `SET`, property assignment, label addition | Canonical GQL | supported | `SET` | Assigning null removes a property. |
| `REMOVE`, property removal, label removal | Canonical GQL | supported | `REMOVE` | Absent entries are unchanged. |
| `DELETE`, `DETACH DELETE`, `NODETACH DELETE` | Canonical GQL | supported | `DELETE`, `DETACH DELETE`, `NODETACH DELETE` | Explicit non-detaching form. |
| `WITH` projection, aggregation, and pagination | pygrafito extension | supported | `WITH` projection and aggregation | Scope-reset extension. |
| Implicit grouping | pygrafito extension | supported | Implicit grouping | Non-aggregate return items form keys. |
| `type()` | pygrafito extension | supported | `type()` | First sorted relationship label. |
| Query budget (`max_expansions`, `max_rows`, `max_seconds`, per-query override) | pygrafito extension | supported | Query budget | Bounded execution. |
| Node patterns, relationship patterns, property maps, backtick-quoted identifiers | Canonical GQL | supported | `MATCH` and `OPTIONAL MATCH` | Shared by read and write clauses. |
| Label conjunction (`&`), label disjunction (vertical bar), label negation (`!`), label wildcard (`%`) | Canonical GQL | supported | Label expressions (and, or, not, wildcard) | Node and relationship labels. |
| `IS` label syntax | Canonical GQL | supported | `IS` label syntax | Explicit form in place of `:`. |
| `:A:B` conjunction syntax | Synthetic alias | supported | `:A:B` for `:A&B` | Node label conjunction. |
| Inline element `WHERE` | Canonical GQL | supported | Inline element `WHERE` | Scoped to one element. |
| Edge directions `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | Canonical GQL | supported | Edge directions `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | Storage-direction constraints. |
| `-->`, `<--` | Synthetic alias | supported | `-->`, `<--`, `--` for `->`, `<-`, `-` | Double-dash arrows. |
| `--` line comment | Canonical GQL | supported | Comments `//`, `--`, `/* ... */` | `--` is never an edge alias. |
| `//`, `/* ... */` comments | Canonical GQL | supported | Comments `//`, `--`, `/* ... */` | Line and block comments. |
| Path variables (`p = pattern`) | Canonical GQL | supported | Path variables | Exposes nodes and relationships in traversal order. |
| Parameters (`$name`) | Canonical GQL | supported | Parameters | Bound as data. |
| `WALK` | Canonical GQL | supported | `WALK` path mode | Default, bounded by the query budget. |
| `TRAIL` | Canonical GQL | supported | `TRAIL` path mode | Relationship-unique. |
| `SIMPLE` | Canonical GQL | supported | `SIMPLE` path mode | Allows a closed path. |
| `ACYCLIC` | Canonical GQL | supported | `ACYCLIC` path mode | Rejects a closed path. |
| `{n}`, `{m,n}`, `{,n}` | Canonical GQL | supported | `{n,m}` quantifier | Closed upper bound. |
| `*n`, `*n..m`, `*0..m` | Compatibility construct | supported | Legacy `*n..m` quantifier | Default `TRAIL`. |
| Comparison operators (`=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`) | Canonical GQL | supported | `FILTER` | Shared expression vocabulary. |
| Boolean operators (`AND`, `OR`, `NOT`) | Canonical GQL | supported | `FILTER` | Shared expression vocabulary. |
| `IN`, `IS NULL`, `IS NOT NULL` | Canonical GQL | supported | `FILTER` | Shared expression vocabulary. |
| `STARTS WITH`, `ENDS WITH`, `CONTAINS` | Canonical GQL | supported | `FILTER` | Case-sensitive literal predicates. |
| Arithmetic (`+`, `-`, `*`, `/`, `%`, unary `+`, unary `-`) | Canonical GQL | supported | `FILTER` | Numeric operands only. |
| List literals (`[...]`) | Canonical GQL | supported | `FILTER` | Query values. |
| Parentheses | Canonical GQL | supported | `FILTER` | Expression grouping. |
| Property access (`x.key`), backtick property keys, map field access | Canonical GQL | supported | `FILTER` | Shared expression vocabulary. |
| Core scalar functions (`id`, `labels`, `properties`, `keys`, `size`, `coalesce`, `toInteger`, `toFloat`, `toString`, `lower`, `upper`, `trim`, `abs`, `concat`, `startNode`, `endNode`) | Canonical GQL | supported | `RETURN` with `DISTINCT`/`ALL` or `*` | Shared expression vocabulary; `type()` is the extension row. |
| Aggregates (`count`, `collect`, `sum`, `avg`, `min`, `max`, `DISTINCT` variants) | Canonical GQL | supported | `GROUP BY` | Also available in `RETURN`. |
| Map values from `properties()`, parameters, row mappings, and map literals | Canonical GQL | supported | `RETURN` with `DISTINCT`/`ALL` or `*`; `FOR` with ordinality/offset | Map literals are supported query values. |
| `CASE` (simple and searched) | Canonical GQL | supported | `CASE` | First matching branch wins. |
| Map literals (`{key: expression}`) | Canonical GQL | supported | `Map literals` | Query values; not storable as properties. |
| List indexing and slicing (`list[0]`, slices) | Canonical GQL | supported | `List indexing and slicing` | Zero-based; negative indexes count from the end. |
| List comprehensions | Canonical GQL | supported | `List comprehensions` | Local loop variable. |
| Canonical string concatenation (double vertical bar) | Canonical GQL | supported | `String concatenation` | Null propagates. |
| `+` on string operands | Synthetic alias | supported | `String concatenation` | Compatibility alias; numeric `+` remains arithmetic. |
| `nodes(path)` | Canonical GQL | supported | `Path functions` | Nodes in traversal order. |
| `relationships(path)` | Canonical GQL | supported | `Path functions` | Relationships in traversal order. |
| `length(path)` | Canonical GQL | supported | `Path functions` | Number of relationships. |
| Extended scalar functions (`range`, `head`, `last`, `tail`, `reverse`, `split`, `substring`, `replace`, `toBoolean`, `round`, `ceil`, `floor`) | Canonical GQL | supported | `Extended scalar functions` | Exact list implemented by `add-gql-query-surface`. |
| `WITH *` | pygrafito extension | supported | `WITH *` | Part of the `WITH` extension. |
| `EXISTS { ... }` | Canonical GQL | supported | `EXISTS { ... }` | Correlated and uncorrelated read-only subquery. |
| `COUNT { ... }` | Canonical GQL | supported | `COUNT { ... }` | Correlated and uncorrelated read-only subquery. |
| `UNION` | Canonical GQL | supported | `UNION` | Set operation. |
| `UNION ALL` | Canonical GQL | supported | `UNION ALL` | Set operation preserving duplicates. |
| `INTERSECT` | Canonical GQL | supported | `INTERSECT` | Set operation. |
| `EXCEPT` | Canonical GQL | supported | `EXCEPT` | Set operation. |
| `DIFFERENT EDGES` | Canonical GQL | gated | `DIFFERENT EDGES` | `define-gql-path-semantics`, then `add-gql-match-modes`. |
| `REPEATABLE ELEMENTS` | Canonical GQL | gated | `REPEATABLE ELEMENTS` | `define-gql-path-semantics`, then `add-gql-match-modes`. |
| Grouped quantified path pattern | Canonical GQL | gated | `Grouped quantified paths` | `define-gql-path-semantics`, `add-gql-unbounded-traversal`, then `add-gql-grouped-quantified-paths`. |
| `ANY` | Canonical GQL | gated | `Path search prefixes` | `define-gql-path-semantics`, `add-gql-unbounded-traversal`, `add-gql-match-modes`, then `add-gql-path-search`. |
| `ANY SHORTEST` | Canonical GQL | gated | `Path search prefixes` | Same follow-up. |
| `ALL SHORTEST` | Canonical GQL | gated | `Path search prefixes` | Same follow-up. |
| `SHORTEST k` | Canonical GQL | gated | `Path search prefixes` | Same follow-up. |
| `*`, `+`, `{m,}` | Canonical GQL | gated | `Open-ended quantifiers` | `define-gql-path-semantics`, then `add-gql-unbounded-traversal`. |
| `*n..` | Compatibility construct | gated | `Open-ended quantifiers` | Legacy open upper bound; same follow-up. |
| Catalog statements (`CREATE GRAPH`, `DROP GRAPH`, `INSERT GRAPH`, schemas) | Out of profile | out of profile | `Catalog statements`; rejected forms | Embedded single graph. |
| Graph types | Out of profile | out of profile | `Graph types` | No schema layer. |
| Sessions | Out of profile | out of profile | `Sessions` | No server state. |
| Procedures (`CALL name(...)`) | Out of profile | out of profile | `Procedures` | No catalog or registry. |
| In-language transactions (`START TRANSACTION`, `COMMIT`, `ROLLBACK`) | Out of profile | out of profile | `In-language transactions` | Python API owns transaction boundaries. |
| `SELECT` | Out of profile | out of profile | `SELECT` | Pattern query surface only. |
| `DATE`, `TIME`, `TIMESTAMP`, `DURATION` | Out of profile | out of profile | `Full temporal values` | No temporal storage. |
| `CALL { ... }` | Out of profile | out of profile | `CALL { ... }` | Cypher-only subquery form. |
| Whole-map assignment (`SET n = {...}`, `SET n += {...}`) | Out of profile | out of profile | `Whole-map assignment` | Assign properties individually. |
| `exists(n.prop)` | Out of profile | out of profile | `exists(n.prop)` | Use `n.prop IS NOT NULL`. |
| Regex predicates (for example `=~`) | Out of profile | out of profile | `Regex predicates` | Use literal string predicates. |
| `shortestPath()`, `allShortestPaths()` | Out of profile | out of profile | `shortestPath()` | Use `Graph.shortest_path` or target path search. |
| Servers and drivers | Out of profile | out of profile | `Servers and drivers` | Embedded only. |
| Clustering, authentication, multi-tenancy | Out of profile | out of profile | `Clustering, authentication, and multi-tenancy` | No server or account layer. |
| Multi-graph storage | Out of profile | out of profile | `Multi-graph storage` | One database per handle. |
| Graph-algorithm APIs | Out of profile | out of profile | `Graph-algorithm APIs` | Python helpers only. |
| Full Cypher compatibility | Out of profile | out of profile | `Full Cypher compatibility` | GQL-first profile. |
| Vector search | Out of profile | out of profile | `Vector search` | No vector index or distance function. |
| Full-text search | Out of profile | out of profile | `Full-text search` | No full-text index or syntax. |
| `MERGE` invalid combinations | Rejected form | rejected form | Rejected forms | Quantified patterns, path variables, multiple patterns, invalid relationship shape, and bound-element rewrites. |
| Mixed legacy and canonical quantifiers without an explicit mode | Rejected form | rejected form | Rejected forms | Name a path mode explicitly. |
| Catalog operations `INSERT GRAPH` and `CREATE GRAPH` | Out of profile | out of profile | `Catalog statements`; rejected forms | Also listed as a rejected operation. |

## Conformance matrix

The matrix is the profile's honest status board. The `status` column uses exactly four values:

- **supported**: in the 1.0 profile, implemented, and covered by at least one conformance corpus
  case.
- **gated**: in the 1.0 profile, not implemented yet, with a named follow-up change.
- **deferred**: post-1.0 language direction, not in the 1.0 profile. No row uses it in this target.
- **out of profile**: rejected.

The `current` column records what the release does today. A `gated` row is not executable in the
current release. The `follow-up` column names the change that implements a gated row or the
prerequisite path. The `corpus` column is `pending` until the row becomes supported; out-of-profile
rows have no query case.

| Feature | Tier | Status | Current | Deviation | Follow-up | Corpus |
| --- | --- | --- | --- | --- | --- | --- |
| `MATCH` and `OPTIONAL MATCH` | Canonical GQL | supported | implemented | None | — | match-program-designations |
| `INSERT` | Canonical GQL | supported | implemented | None | — | insert-creates-a-node |
| `SET` | Canonical GQL | supported | implemented | None | — | set-assigns-a-property |
| `REMOVE` | Canonical GQL | supported | implemented | None | — | remove-removes-a-property |
| `DELETE`, `DETACH DELETE`, `NODETACH DELETE` | Canonical GQL | supported | implemented | None | — | nodetach-delete-removes-a-disconnected-node |
| `FOR` with ordinality/offset | Canonical GQL | supported | implemented | None | — | for-ordinality-binds-one-based-position |
| `FILTER` | Canonical GQL | supported | implemented | None | — | filter-stage-alias |
| `LET` | Canonical GQL | supported | implemented | None | — | let-adds-a-binding |
| `NEXT` | Canonical GQL | supported | implemented | `YIELD` supported; no-`YIELD` and write-only segments accepted for Cypher compatibility | — | next-carries-an-intermediate-return |
| `FINISH` | Canonical GQL | supported | implemented | None | — | finish-ends-a-read-without-a-result |
| `GROUP BY` | Canonical GQL | supported | implemented | Expression keys are a pygrafito extension; `RETURN DISTINCT` is accepted | — | group-by-groups-and-counts |
| `RETURN` with `DISTINCT`/`ALL` or `*` | Canonical GQL | supported | implemented | `RETURN NO BINDINGS` is a pygrafito extension | — | return-all-is-the-default |
| `RETURN NO BINDINGS` | pygrafito extension | supported | implemented | Zero columns, one empty row per input binding; final-only | — | return-no-bindings-projects-empty-rows |
| `ORDER BY` with null ordering | Canonical GQL | supported | implemented | None | — | nulls-first-explicit |
| `OFFSET` and `SKIP` | Canonical GQL | supported | implemented | Canonical synonyms, not aliases | — | offset-paginates |
| `LIMIT` | Canonical GQL | supported | implemented | None | — | limit-bounds-the-result |
| `{n,m}` quantifier | Canonical GQL | supported | implemented | Open upper bounds are gated under `Open-ended quantifiers` | — | quantifier-bounded-range |
| Label expressions (and, or, not, wildcard) | Canonical GQL | supported | implemented | None | — | label-conjunction |
| Edge directions `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | Canonical GQL | supported | implemented | None | — | arrow-outgoing |
| Comments `//`, `--`, `/* ... */` | Canonical GQL | supported | implemented | `--` is a comment, not an edge alias | — | dash-comment |
| Inline element `WHERE` | Canonical GQL | supported | implemented | None | — | inline-node-predicate |
| `IS` label syntax | Canonical GQL | supported | implemented | None | — | label-is-form |
| Path variables | Canonical GQL | supported | implemented | None | — | diamond-finds-two-trails |
| Parameters | Canonical GQL | supported | implemented | None | — | parameters-bind-data |
| `WALK` path mode | Canonical GQL | supported | implemented | Default; bounded by the query budget | — | walk-reuses-a-relationship |
| `TRAIL` path mode | Canonical GQL | supported | implemented | None | — | trail-rejects-a-reused-relationship |
| `SIMPLE` path mode | Canonical GQL | supported | implemented | None | — | simple-allows-a-closed-path |
| `ACYCLIC` path mode | Canonical GQL | supported | implemented | None | — | acyclic-rejects-a-closed-path |
| `CREATE` for `INSERT` | Synthetic alias | supported | implemented | Data statements only | — | create-alias-returns-a-node |
| `UNWIND` for `FOR` | Synthetic alias | supported | implemented | None | — | unwind-alias-iterates |
| Stage `WHERE` for `FILTER` | Synthetic alias | supported | implemented | `MATCH ... WHERE` stays canonical | — | stage-where-alias-filters |
| `-->`, `<--`, `--` for `->`, `<-`, `-` | Synthetic alias | supported | implemented | `-->` and `<--` are aliases; `--` is a comment, not an edge | — | arrow-double-dash-alias |
| `:A:B` for `:A&B` | Synthetic alias | supported | implemented | None | — | label-colon-conjunction-alias |
| Legacy `*n..m` quantifier | Compatibility construct | supported | implemented | Default `TRAIL` | — | legacy-quantifier-trails |
| `MERGE` with conditional updates | pygrafito extension | supported | implemented | No GQL equivalent; invalid forms are rejected | — | merge-conditional-updates |
| `WITH` projection and aggregation | pygrafito extension | supported | implemented | No GQL equivalent; `WITH *` is supported | — | with-aggregation |
| Implicit grouping | pygrafito extension | supported | implemented | `GROUP BY` alternative | — | implicit-grouping |
| `type()` | pygrafito extension | supported | implemented | `LABELS()` alternative | — | type-extension |
| Query budget | pygrafito extension | supported | implemented | No GQL equivalent; expansion, row, and optional time counters | — | budget-row-limit |
| `CASE` | Canonical GQL | supported | implemented | Simple and searched forms | — | case-searched-classifies-programs |
| Map literals | Canonical GQL | supported | implemented | `{key: expression}` | — | map-literal-projects-fields |
| List indexing and slicing | Canonical GQL | supported | implemented | Index and slice access | — | list-index-and-slice |
| List comprehensions | Canonical GQL | supported | implemented | List-producing expression | — | list-comprehension-filters-and-doubles |
| String concatenation | Canonical GQL | supported | implemented | Canonical double-pipe operator; `+` is a compatibility alias for string operands | — | string-concatenation-and-plus-alias |
| Path functions | Canonical GQL | supported | implemented | `nodes`, `relationships`, `length` | — | path-functions-expose-a-path |
| Extended scalar functions | Canonical GQL | supported | implemented | `range`, `head`, `last`, `tail`, `reverse`, `split`, `substring`, `replace`, `toBoolean`, `round`, `ceil`, `floor` | — | extended-scalar-functions |
| `WITH *` | pygrafito extension | supported | implemented | Part of the `WITH` extension | — | with-star-preserves-scope |
| `EXISTS { ... }` | Canonical GQL | supported | implemented | Read-only correlated and uncorrelated subquery | — | exists-correlated-programs |
| `COUNT { ... }` | Canonical GQL | supported | implemented | Read-only correlated and uncorrelated subquery | — | count-correlated-trusts |
| `UNION` | Canonical GQL | supported | implemented | Set operation | — | union-deduplicates-program-and-user |
| `UNION ALL` | Canonical GQL | supported | implemented | Set operation with duplicates | — | union-all-preserves-duplicates |
| `INTERSECT` | Canonical GQL | supported | implemented | Set operation | — | intersect-keeps-program-names |
| `EXCEPT` | Canonical GQL | supported | implemented | Set operation | — | except-removes-program-names |
| `DIFFERENT EDGES` | Canonical GQL | gated | not implemented | Match mode | `define-gql-path-semantics`, then `add-gql-match-modes` | pending |
| `REPEATABLE ELEMENTS` | Canonical GQL | gated | not implemented | Match mode | `define-gql-path-semantics`, then `add-gql-match-modes` | pending |
| Grouped quantified paths | Canonical GQL | gated | not implemented | Parenthesized path repetition | `define-gql-path-semantics`, `add-gql-unbounded-traversal`, then `add-gql-grouped-quantified-paths` | pending |
| Path search prefixes | Canonical GQL | gated | not implemented | `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k` | `define-gql-path-semantics`, `add-gql-unbounded-traversal`, `add-gql-match-modes`, then `add-gql-path-search` | pending |
| Open-ended quantifiers | Canonical GQL | gated | not implemented | `*`, `+`, `*n..`, `{m,}`; enables unbounded traversal. `Unbounded WALK` is not a separate row | `define-gql-path-semantics`, then `add-gql-unbounded-traversal` | pending |
| Catalog statements | Out of profile | out of profile | rejected | Embedded single graph | — | n/a |
| Graph types | Out of profile | out of profile | rejected | No schema layer | — | n/a |
| Sessions | Out of profile | out of profile | rejected | No server state | — | n/a |
| Procedures | Out of profile | out of profile | rejected | No catalog | — | n/a |
| In-language transactions | Out of profile | out of profile | rejected | Python API owns transactions | — | n/a |
| `SELECT` | Out of profile | out of profile | rejected | Pattern query surface only | — | n/a |
| Full temporal values | Out of profile | out of profile | rejected | No temporal storage | — | n/a |
| `CALL { ... }` | Out of profile | out of profile | rejected | Cypher-only subquery form | — | n/a |
| Whole-map assignment | Out of profile | out of profile | rejected | Cypher-only convenience form | — | n/a |
| `exists(n.prop)` | Out of profile | out of profile | rejected | Use `n.prop IS NOT NULL` | — | n/a |
| Regex predicates | Out of profile | out of profile | rejected | Cypher-only regular-expression matching | — | n/a |
| `shortestPath()` | Out of profile | out of profile | rejected | Cypher-only path function | — | n/a |
| Servers and drivers | Out of profile | out of profile | rejected | Embedded library only | — | n/a |
| Clustering, authentication, and multi-tenancy | Out of profile | out of profile | rejected | No server or account layer | — | n/a |
| Multi-graph storage | Out of profile | out of profile | rejected | One database per handle | — | n/a |
| Graph-algorithm APIs | Out of profile | out of profile | rejected | Python helpers only | — | n/a |
| Full Cypher compatibility | Out of profile | out of profile | rejected | GQL-first profile | — | n/a |
| Vector search | Out of profile | out of profile | rejected | No vector index or distance function | — | n/a |
| Full-text search | Out of profile | out of profile | rejected | No full-text index or syntax | — | n/a |

A feature is `supported` only while at least one corpus case covers it and passes in CI. This page
therefore claims a tested profile, not ISO conformance beyond the matrix.

## Conformance corpus

The corpus is data-driven so the matrix can require coverage without a bespoke test harness. It
lives in `tests/conformance/cases.json`, is executed by `hatch test tests/test_conformance.py`,
and is checked against this page by `tests/test_gql_profile.py`. Each case has this shape:

```text
name       unique kebab-case identifier
feature    matrix feature id
fixture    name of a fixture declared in the same document
query      statement text
params     optional parameter mapping
expect     projected rows, or an error type and message fragment
tags       optional: canonical, alias, compatibility, extension, gated
budget     optional: per-case query-budget overrides, such as {"max_rows": 2}
```

The feature id is derived from the first matrix column: lower-case it and replace every run of
non-alphanumeric characters with a hyphen. Four rows carry an explicit id because the derived one
would be ambiguous: `edge-direction-aliases`, `label-conjunction-alias`, `quantifier`, and
`legacy-quantifier`. A case tagged `gated` must name a gated row.

Fixtures are small named graphs declared in the same file, not the example datasets, so a corpus
run stays fast and the language contract never depends on `examples/`. Example case:

```json
{
  "name": "walk-reuses-a-relationship",
  "feature": "walk-path-mode",
  "fixture": "tron-cycle",
  "query": "MATCH WALK (a {designation: 'Kevin Flynn'})-[:TRUSTS*4]->(b) RETURN b.designation AS name",
  "expect": {"rows": [{"name": "Quorra"}]},
  "tags": ["canonical"]
}
```

A feature is marked `supported` only after at least one case covers it. A regression fails CI with
the case name and feature id. The coverage rules are enforced in both directions: every
`supported` row needs a case, every case needs a matrix row, and deferred or out-of-profile rows
carry none. Gated rows carry no corpus case in this change; their cases land with the follow-up
change.

## 1.0 release gate

The 1.0 profile is a release gate. The gate blocks 1.0 until every item is checked:

1. **No gated or deferred rows.** Every matrix row is `supported` or `out of profile`. Checked by
   reading the matrix and, after `complete-gql-profile`, by the automated consistency check.
2. **Every supported row has a corpus case.** Checked by
   `hatch test tests/test_gql_profile.py` and the data-driven corpus.
3. **Every out-of-profile row and rejected form has an explicit rejection test.** Checked by the
   profile audit and the focused tests named in the rejected-forms table; `complete-gql-profile`
   adds any missing test.
4. **Matrix, inventory, prose, grammar summary, query-language reference, and tours agree.**
   Checked by review and the `complete-gql-profile` consistency check.
5. **Quality checks pass.** `hatch check --fix`, `hatch test`, and `hatch run docs:build` pass;
   coverage is at least 80%.
6. **The 1.0 hardening checklist is complete.** Owned by `harden-for-1.0`.
7. **Package smoke tests pass.** The built wheel installs in a clean environment, and `py.typed`
   and `LICENSE.txt` are packaged; checked by the package CI job.
8. **Release notes are ready.** The 1.0 changelog section, migration notes, and out-of-profile list
   exist.
9. **The version is set with `hatch version 1.0.0`.** Never edit the version file directly.

This change documents the gate. The later `complete-gql-profile` change owns the automated
consistency checks that enforce it; implementation changes own their feature cases and status
updates.

## Profile freeze policy

The 1.0 profile is frozen at release.

- After 1.0, a construct may be added in a minor release only when it does not change the meaning
  of an existing supported construct. The same change updates the profile, matrix, inventory,
  query-language reference, tours, and corpus.
- A change that alters the meaning of a supported construct requires a major version and a
  migration section.
- Promoting an out-of-profile construct requires a separate proposal. It is not a deferred
  backlog item.
- `deferred` remains available for post-1.0 direction, but a deferred construct is not a 1.0
  promise.

## Migration guidance

The profile is a pre-1.0 target. The current dialect remains accepted through the compatibility
surface, so migration can be incremental.

| Transitional form | Target form | Migration note |
| --- | --- | --- |
| `CREATE (n:Program)` | `INSERT (n:Program)` | `CREATE` remains an alias for data patterns. |
| `UNWIND list AS value` | `FOR value IN list` | `UNWIND` remains an alias. |
| `WHERE` after `WITH` | `FILTER` | Stage `WHERE` remains an alias. |
| `WITH` | `LET`, `NEXT`, `GROUP BY` | `WITH` remains an extension. |
| Implicit grouping | `GROUP BY` | Implicit grouping remains an extension. |
| `RETURN NO BINDINGS` | `FINISH` | `RETURN NO BINDINGS` remains a zero-column extension. |
| `*1..3` | `{1,3}` | The legacy form keeps `TRAIL`; the canonical form uses `WALK`. |
| `-->`, `<--`, `--` | `->`, `<-`, `-` | `-->` and `<--` remain aliases; `--` is a comment. |
| No path mode | `WALK` default | Use `MATCH TRAIL` for the old trail behavior. |
| `type(r)` | `LABELS(r)` | `type()` remains an extension. |
| `MERGE` | No GQL equivalent | `MERGE` remains an extension. |
| Unquoted `when`, `then`, `else`, `end`, `union`, `intersect`, `except` identifiers | Backtick-quoted names | These words are now reserved keywords; quote existing variables or aliases that use them. |

To keep the old relationship-unique behavior after the path-semantics change:

```text
MATCH TRAIL (a)-[:ALLIES_WITH{1,3}]->(b) RETURN b

// or keep the legacy quantifier:
MATCH (a)-[:ALLIES_WITH*1..3]->(b) RETURN b
```

The Python `paths()` API remains a relationship-unique trail enumerator regardless of the query
language default. It does not follow `WALK`.

## Change control

A change that adds, removes, or changes a query construct updates this page, the conformance
matrix, the construct inventory, the query-language reference, the tours, and the conformance
corpus in the same change. A construct added without a profile entry or a corpus case is not
complete. A feature is marked `supported` only after its corpus case exists and passes in CI. A
gated row without a follow-up owner is a profile defect.

The project does not claim ISO conformance beyond this matrix. Use "GQL profile" or
"GQL-first profile" in documentation and release notes, not "GQL compliant".
