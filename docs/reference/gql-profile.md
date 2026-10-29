# GQL profile

:::{admonition} tl;dr
:class: tldr

The language contract for `pygrafito`: canonical GQL spellings, compatibility aliases and
constructs, extensions, path and budget policy, and the conformance matrix. Use it to decide
whether a spelling is portable GQL or a `pygrafito` extension.
:::

This page is the language profile for `pygrafito`. It defines the canonical GQL surface, the
compatibility aliases and constructs, the pygrafito extensions, the path-mode and query-budget
policy, the 1.0 release gate, and how conformance is claimed.

:::{admonition} Remember
:class: important

This page is both the language profile and its conformance status board. Status describes target
membership and implementation state separately:

- **supported** — implemented in the current release and covered by at least one conformance corpus case.
- **gated** — vocabulary for an in-scope construct that is not implemented yet. No row in this release uses it.
- **deferred** — vocabulary for post-1.0 language direction. No row in this release uses it.
- **out of profile** — a rejected non-goal.

The current release contains only `supported` and `out of profile` rows. The `gated` and `deferred`
statuses stay in the vocabulary so a future proposal cannot silently reintroduce an unimplemented
target. The [query-language reference](query-language.md) describes the executable dialect only.
:::

## Current status

The current release implements every supported row below, including open-ended quantifiers, match
modes, path search, and grouped quantified paths. Every path-engine row is supported. Constructs
outside the profile are rejected with a positioned query error, and the matrix records their
status.

| Area | Supported surface |
| --- | --- |
| Pattern matching | `MATCH`, `OPTIONAL MATCH`, multiple patterns, repeated variables, inline `WHERE`, path variables |
| Data modification | `INSERT`, `SET`, `REMOVE`, `DELETE`, `DETACH DELETE`, `NODETACH DELETE`; `CREATE` alias; `MERGE` extension |
| Iteration and filtering | `FOR`, `UNWIND` alias, `FILTER`, stage `WHERE` alias, `MATCH ... WHERE` |
| Binding, composition, and grouping | `LET`, `NEXT` with `YIELD`, `FINISH`, `GROUP BY`, `WITH` extension, implicit grouping |
| Projection, ordering, and pagination | `RETURN`, `RETURN DISTINCT`, `RETURN ALL`, `RETURN *`, `RETURN NO BINDINGS`; `ORDER BY`, `OFFSET`, `SKIP`, `LIMIT` |
| Quantifiers | Closed `{n}`, `{m,n}`, `{,n}`; open `{m,}`, `*`, `+`; legacy `*n`, `*n..m`, `*0..m`, `*n..` |
| Path modes | `WALK` default; `TRAIL`, `SIMPLE`, `ACYCLIC` explicit; match modes `REPEATABLE ELEMENTS` and `DIFFERENT EDGES`; path search `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`; grouped quantified paths |
| Expressions | Operators, property access, list literals, `CASE`, map literals, list indexing and slicing, list comprehensions, string concatenation, path functions, core and extended scalar functions, aggregates |
| Subqueries | Read-only `EXISTS { ... }` and `COUNT { ... }` |
| Set operations | `UNION`, `INTERSECT`, `EXCEPT`, each with optional `ALL` or `DISTINCT` |
| Query budget | Expansion, row, and optional time counters with per-query override |
| Out of profile | Rejected with an explicit query error |

The runnable examples in `README.md`, the quickstart, and the guides use the canonical spellings
where the release supports them; compatibility aliases appear only in the migration guidance.

## The five tiers

Every supported construct belongs to exactly one tier. Rejected forms are invalid
combinations, not separate tiers.

```{mermaid}
:alt: A decision tree that classifies a construct as canonical GQL, a synthetic alias, a compatibility construct, a pygrafito extension, or out of profile.

flowchart TD
  Q["Construct"] --> C{"Canonical GQL?"}
  C -->|yes| C1["Canonical GQL"]
  C -->|no| A{"Identical alias?"}
  A -->|yes| A1["Synthetic alias"]
  A -->|no| K{"Legacy construct?"}
  K -->|yes| K1["Compatibility construct"]
  K -->|no| E{"pygrafito extension?"}
  E -->|yes| E1["pygrafito extension"]
  E -->|no| O["Out of profile<br/>rejected"]
  accTitle: The five GQL profile tiers
  accDescr: A construct is canonical GQL, a synthetic alias with identical semantics, a compatibility construct with a legacy default, a pygrafito extension, or out of profile and rejected.
```

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
| Quantifiers | `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, `+` | Placement follows the GQL path-pattern grammar. A missing upper bound means unbounded. |
| Labels | Conjunction, disjunction, negation, wildcard | Node and edge label expressions; `IS` is accepted in place of `:`. |
| Edge directions | `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | `-` is any direction; `~` is undirected only. |
| Comments | `//`, `--`, `/* ... */` | `--` is a GQL line comment; legacy double-dash arrows are an alias. |
| Path variables | `p = <path pattern>` | Paths expose their nodes and relationships in traversal order. |
| Parameters | `$name` | Bound as data, never as identifiers or SQL text. |
| Path modes | `WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC` | `WALK` is the canonical default, bounded by the query budget. |
| Expressions | `CASE`, map literals, list indexing and slicing, list comprehensions, string concatenation, function calls | Supported. |
| Path functions | `nodes(path)`, `relationships(path)`, `length(path)` | Supported. |
| Subqueries | `EXISTS { ... }`, `COUNT { ... }` | Read-only, correlated or uncorrelated. |
| Set operations | `UNION`, `INTERSECT`, `EXCEPT`, each with optional `ALL` or `DISTINCT` | Read-only compound queries; `ALL` keeps duplicate copies and `DISTINCT` is the explicit default. |
| Path search | `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k` | Supported; whole-path selection per endpoint pair. |
| Match modes | `DIFFERENT EDGES`, `REPEATABLE ELEMENTS` | Supported; `REPEATABLE ELEMENTS` is the default. |
| Grouped quantified paths | Repetition of a grouped path pattern, with list bindings and inner modes | Supported. |
| Open-ended quantifiers | `{m,}`, `*`, `+`; legacy `*n..` | Supported, with demand-driven limits and the query budget. |

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
| `DISTINCT` after a set operator | The bare set operator | Explicit set quantifier; same as omitting it. |

The canonical string concatenation operator is `||`. The `+` alias applies only to string operands;
numeric operands keep arithmetic `+` and mixed operands are rejected.

`SKIP` is not an alias: GQL defines both `SKIP` and `OFFSET` as canonical synonyms.

The legacy double-dash arrows collide with the GQL `--` line comment. The frontend change must
define the disambiguation so a `--` comment is never silently reinterpreted as an edge, and a
legacy `-->` or `<--` arrow is never truncated into a comment.

## Compatibility construct: the legacy quantifier

The legacy Cypher quantifier is a compatibility construct. It keeps its Cypher default of
relationship-unique trails. The canonical closed and open forms are supported.

| Form | Default path mode | Status | Notes |
| --- | --- | --- | --- |
| `*n`, `*n..m`, `*0..m` | `TRAIL` | supported | Cypher-compatible. The upper bound is finite. |
| `*n..` | `TRAIL` | supported | Legacy open upper bound. |
| `{n}`, `{m,n}`, `{,n}` | `WALK` (target) | supported | GQL canonical closed quantifiers. |
| `{m,}`, `*`, `+` | `WALK` | supported | GQL canonical open forms. |
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

A missing upper bound means the quantifier is unbounded. The open forms are `{m,}`, `*`
(zero or more), `+` (one or more), and the legacy `*n..` spelling. An open walk stops when the
result demand is met or when the query budget stops it; it never returns a truncated path set.

## Path modes

| Mode | Rule | Profile status |
| --- | --- | --- |
| `WALK` | Repeated nodes and relationships are allowed. | Canonical default; supported while the query budget is enforced. |
| `TRAIL` | A relationship may not repeat within one path; nodes may repeat. | Supported; also the default for the legacy quantifier. |
| `SIMPLE` | Nodes may not repeat, except that the start and end may be the same. | Supported. |
| `ACYCLIC` | No node may repeat. | Supported. |

Match modes, quantifiers with an open upper bound, path search, and grouped quantified paths are
separate constructs with their own matrix rows. Their interaction with these four modes is defined
in [Path semantics](#path-semantics).

The path changes depend on `define-gql-path-semantics`, which owns the interaction between path
modes, match modes, quantifiers, and search prefixes.

The Python `paths()` API remains a relationship-unique, bounded trail enumerator. It does not
follow the query language's `WALK` default. Use `paths()` when you want a trail, and `MATCH TRAIL`
when you want a trail in the query language.

## Path semantics

This section publishes how path modes, match modes, quantifiers, and path search
combine. `define-gql-path-semantics` owns these decisions. `add-gql-unbounded-traversal`,
`add-gql-match-modes`, `add-gql-path-search`, and `add-gql-grouped-quantified-paths` have landed.
Each construct keeps a
[conformance matrix](#conformance-matrix) row, and every table here repeats its current status.
Every example on this page is current behavior.

### Path modes and match modes

Path modes constrain one path. Match modes constrain the whole `MATCH` clause. Both apply at the
same time, and neither overrides the other.

| Path mode | Constraint inside one path | Status |
| --- | --- | --- |
| `WALK` | None. Nodes and relationships may repeat. | Canonical default; supported. |
| `TRAIL` | No relationship may occur twice. Nodes may repeat. | Supported; default for a legacy quantifier. |
| `SIMPLE` | No node may repeat, except that the first and last node may be the same. | Supported. |
| `ACYCLIC` | No node may repeat, including the first and last. | Supported. |

| Match mode | Constraint across all paths of one `MATCH` clause | Status |
| --- | --- | --- |
| `REPEATABLE ELEMENTS` | None. This is the default. | Supported. |
| `DIFFERENT EDGES` | Each relationship binds at most once in the clause, including repetitions inside one path. | Supported. |

A relationship use is accepted only when both the path mode and the match mode accept it. `TRAIL`
and `DIFFERENT EDGES` therefore agree inside a path, while `WALK` and `DIFFERENT EDGES` together
mean "a walk path, but every edge used once in the clause".

The match mode defaults to `REPEATABLE ELEMENTS` so existing query results do not change. The
profile publishes that choice instead of implying another default.

The effective path mode keeps the resolution order described under [Path modes](#path-modes):
explicit per-path mode, explicit clause mode, `TRAIL` for a path that contains a legacy quantifier,
then `WALK`. The match mode is resolved independently at clause level, so
`MATCH DIFFERENT EDGES TRAIL (a)-[:TRUSTS{1,3}]->(b)` applies both rules.

Match modes apply to `MATCH` and `OPTIONAL MATCH`. `INSERT`, `CREATE`, and `MERGE` patterns have no
match mode and keep their current behavior. `DIFFERENT EDGES` is scoped to the clause: an
relationship bound by an earlier `MATCH` stage may be bound again in a later stage.

### Quantifiers

| Form | Lower bound | Upper bound | Tier | Default path mode | Status |
| --- | --- | --- | --- | --- | --- |
| `{n}` | `n` | `n` | Canonical GQL | `WALK` | supported |
| `{m,n}` | `m` | `n` | Canonical GQL | `WALK` | supported |
| `{,n}` | `0` | `n` | Canonical GQL | `WALK` | supported |
| `{m,}` | `m` | unbounded | Canonical GQL | `WALK` | supported |
| `*` | `0` | unbounded | Canonical GQL | `WALK` | supported |
| `+` | `1` | unbounded | Canonical GQL | `WALK` | supported |
| `*n` | `n` | `n` | Compatibility construct | `TRAIL` | supported |
| `*n..m` | `n` | `m` | Compatibility construct | `TRAIL` | supported |
| `*0..m` | `0` | `m` | Compatibility construct | `TRAIL` | supported |
| `*n..` | `n` | unbounded | Compatibility construct | `TRAIL` | supported |
| Group `{...}` | as written | as written | Canonical GQL | `WALK` | supported |

The bare `*` and `+` are the canonical GQL forms, not legacy spellings. `*` is zero or more and
`+` is one or more, so a query that wants at least one hop writes `+` or `{1,}`. A missing upper
bound means unbounded; an open `WALK` stops at demand or at the query budget.

Mixing a legacy and a canonical quantifier in one path without an explicit path mode is a semantic
error, exactly as today. Bounds are non-negative integer literals; parameters and expressions are
rejected. A lower bound of zero is legal on a relationship segment.

### Zero-hop and zero-length bindings

| Situation | Node bindings | Relationship binding | Path binding |
| --- | --- | --- | --- |
| A quantified segment matches zero hops | Both end nodes bind to the same node | The relationship variable binds `[]` | The path contains one node and no relationship for that segment |
| A path pattern has no relationships | Its single node variable binds that node | None | The path contains one node and no relationships; `length(p)` is `0` |
| A group matches zero iterations | Boundary nodes coincide; group-local node variables bind `[]` | Group-local relationship variables bind `[]` | A group path variable is not allowed when zero iterations are possible |

A zero-hop segment evaluates its label, property, and inline `WHERE` constraints only when it
matches at least one hop; at zero hops there is no relationship to test. Node constraints on the
end node always apply. Path modes apply across the whole path, including zero-hop segments. The
closed forms with a zero lower bound execute today; the open and grouped rows follow their owners.

### Termination, demand, and the budget

| Query shape | Termination |
| --- | --- |
| Closed quantifier, any mode | Finite. |
| Open-ended quantifier under `TRAIL`, `SIMPLE`, or `ACYCLIC` | Finite: the path mode bounds the path length. |
| Open-ended quantifier with any search prefix | Finite: search selects a finite number of paths per partition, and the set of partitions is finite. |
| Open-ended quantifier under `WALK` without a search prefix | Infinite in general. Completes only when execution is demand-bounded. |

Demand-bounded means that a final `LIMIT`, with or without `OFFSET`, satisfies all of these: the
statement is read-only, no `ORDER BY`, `DISTINCT`, aggregation, `GROUP BY`, set operation, write
clause, `NEXT` boundary, or `FINISH` follows, and the result does not need all rows before the
first one. `EXISTS { ... }` also stops after its first inner row. A `LIMIT` under `ORDER BY`,
`DISTINCT`, aggregation, or a write clause requires full evaluation.

An open `WALK` with no demand bound and no search prefix runs until the budget stops it. Execution
then raises a budget error that names the counter and the limit, and returns no partial result; it
never returns a truncated path set. Use `LIMIT`, a search prefix, or a repetition-restricting path
mode such as `TRAIL` to make the shape finite.

Budget accounting:

- Each candidate relationship expansion counts once against the expansion counter, whether it is
  later accepted or rejected.
- Each produced binding counts once against the row counter.
- Path search counts exploration expansions; selecting or deduplicating a path adds none.
- A group iteration adds no counter of its own because each iteration consumes at least one
  relationship.
- A wall-clock limit remains opt-in and is checked at the existing intervals.

### Path search

A search prefix applies to one path pattern. It partitions the matches of that pattern by the
pair of boundary nodes of the path, its first node and its last node, within each input row. Each
input row is partitioned independently, so the same endpoint pair in two rows is two partitions.

| Prefix | Selection per partition | Status |
| --- | --- | --- |
| none | Every path. This is the default. | Supported. |
| `ANY` | One path. A deterministic shortest path is a valid choice. | Supported. |
| `ANY SHORTEST` | One path of minimum length. | Supported. |
| `ALL SHORTEST` | Every path of minimum length. | Supported. |
| `SHORTEST k` | Up to `k` paths in increasing length; ties count toward `k`. | Supported. |

`k` in `SHORTEST k` is a non-negative integer literal, so parameters, expressions, negative
values, and non-integers are rejected. `SHORTEST 0` selects no path.

Two paths are the same when their node sequence and their orientation-aware relationship sequence
are identical. Parallel relationships produce different paths because their relationship
identifiers differ, so `ALL SHORTEST` returns distinct paths rather than distinct endpoint pairs.

When a prefix chooses among paths of the same length, the tie-break order is:

1. Shorter path first.
2. Then the lexicographically smaller relationship sequence, comparing each traversed
   relationship's identifier and traversal orientation.
3. Then the lexicographically smaller node sequence.

The evaluator enumerates relationships in ascending identifier order and target nodes in ascending
identifier order, so the choice is deterministic. Output rows for a path pattern follow this order
unless the statement has its own `ORDER BY`.

A search prefix is written after the optional path variable and before a per-path mode. A
clause-level mode comes before the prefix:

```text
MATCH p = ANY SHORTEST WALK (a)-[:TRUSTS*1..3]->(b) RETURN p
MATCH TRAIL ANY (a)-[:TRUSTS*1..3]->(b) RETURN p
```

A prefix inside a group is a semantic error because search applies to the whole path. A path
pattern carries at most one search prefix.

These examples run on the published TRON fixtures:

| Example | Result |
| --- | --- |
| `MATCH p = ALL SHORTEST (a:User {designation: 'Kevin Flynn'})-[:PARENT_OF\|TRUSTS{1,2}]->(b {designation: 'Alan Bradley'}) RETURN p` on `tron-diamond` | Two two-hop paths, one through Sam Flynn and one through Quorra. |
| The same query with `ANY SHORTEST` | One two-hop path, chosen by the tie-break order. |
| `MATCH p = SHORTEST 2 (a:User {designation: 'Kevin Flynn'})-[:TRUSTS|ALLIES_WITH]->(b:Program {designation: 'Quorra'}) RETURN p` on `tron-parallel` | Both one-hop paths, because the parallel relationships are different paths. |
| The same query with `SHORTEST 0` | No rows. |
| `MATCH p = ANY (a:Program)-[:TRUSTS{1,3}]->(b:Program) RETURN p` on `tron-cycle` | One path per endpoint pair. |

### Grouped quantified paths

A path pattern is a juxtaposition of path terms. A path term is a node pattern followed by zero or
more relationship-node pairs, or a parenthesized path pattern followed by a quantifier. Adjacent
terms share their boundary node: the last node of one term is the first node of the next.

```text
MATCH p = (kevin:User)-[:TRUSTS]->((a:Program)-[r:TRUSTS]->(b:Program)){1,3} RETURN p
```

The conformance matrix classifies grouped quantified paths as one row, `Grouped quantified paths`.
The row is supported and carries its six corpus cases.

A group follows these rules:

- It contains at least one relationship position, directly or through a nested group.
- Its quantifier is `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, or `+`. The legacy `*n..m` spelling is not
  allowed on a group.
- The whole path pattern contains at least one element that consumes a relationship, so a path is
  never empty and a lone zero-lower-bound group is rejected.
- It may name an inner path mode after its opening parenthesis,
  `(TRAIL (a:Program)-[r:TRUSTS]->(b:Program)){1,3}`. Inner and outer modes both apply, and the
  stricter constraint wins. A group may not name a search prefix.
- A group variable occurs at most once in its group. The implicit boundary equality between
  iterations is not expressed through a variable.
- A variable bound before the group may be referenced inside it. It acts as an equality
  constraint, not as a group variable.
- Nested groups follow the same rules. A group inside a group may not rebind an outer group
  variable.

Variables first introduced inside a group are **group variables**. Outside the group they bind
ordered lists: a node variable binds the node per iteration, a relationship variable binds the
relationship per iteration, and nesting flattens the lists in traversal order.

A path variable on a group binds one path for the concatenated iterations. It is rejected when the
quantifier admits zero iterations, because a path contains at least one node. Zero iterations are
allowed only when the rest of the path pattern contributes at least one relationship; group
variables then bind empty lists.

Every group contains at least one relationship position whose effective minimum hop count is at
least one. This progress rule guarantees that each iteration consumes a relationship and charges
the expansion counter, so an open group cannot loop without consuming budget.

Path modes, match modes, path search, path variables, and path functions see the group as part of
the whole path. A grouped path is not a separate result.

A group is rejected when it has no relationship position, when it cannot progress, when it is the
only path term and admits zero iterations, when it names a path variable and admits zero
iterations, when it binds a variable twice or shadows an outer variable, or when it names a search
prefix. The consolidated list is under [Rejected path combinations](#rejected-path-combinations).

### Rejected path combinations

Each combination below is a semantic error. It is rejected with a positioned query error before
any statement text executes and has a focused test.

| Combination | Why it is rejected |
| --- | --- |
| Mixing a legacy and a canonical quantifier in one path without an explicit mode | The two forms have different defaults, and the profile refuses to guess which one the author intended. |
| A search prefix inside a group | Search applies to the whole path, not to one term. |
| A group with no relationship position, a group that cannot progress, or a lone zero-lower-bound group | A path must not be empty, and every iteration must consume a relationship. |
| A group path variable on a quantifier that admits zero iterations | A path contains at least one node, so it cannot represent an empty iteration. |
| A variable introduced twice inside one group, or a group variable that shadows an outer variable | Group variables bind one ordered list, and shadowing would make the binding ambiguous. |
| `SHORTEST k` with a non-literal, negative, or non-integer `k` | Selection counts have to be fixed before execution. |
| More than one search prefix on one path pattern | A partition has one selection rule. |

The mixed-quantifier rejection already has a focused test and is also listed under
[Rejected forms](#rejected-forms).

### Migration notes

- `WALK` stays the default path mode, and `REPEATABLE ELEMENTS` becomes the explicit default match
  mode, so existing queries keep their results.
- `DIFFERENT EDGES` is opt-in. A query with several patterns that relies on sharing a relationship
  changes only when it adds that keyword. It applies to the whole clause, not across `MATCH` stages.
- Open quantifiers were rejected before this release. Accepting them adds behavior and removes
  none. Bare `*` includes zero-hop matches, so write `+` or `{1,}` when you want at least one hop.
- `DIFFERENT`, `EDGES`, `REPEATABLE`, `ELEMENTS`, `ANY`, and `SHORTEST` are reserved keywords in
  this release. Backtick-quote existing variables and aliases that use those spellings.
- Grouped path syntax was a syntax error before this release. It now binds variables introduced
  inside the group as ordered lists, so write a list comprehension to project their elements.
- An open `WALK` without `LIMIT`, a search prefix, or a grouped repetition restriction runs to the
  budget error instead of failing as a deferred construct. Write `LIMIT`, a search prefix, or
  `TRAIL` for a finite result.
- The Python `paths()` API keeps its relationship-unique, bounded trail contract. The target path
  semantics do not change it.

## Stored numeric equality

Equality and `IN` compare a numeric property value by the exact JSON number text stored for it.
The result does not depend on how the SQLite JSON parser converts that text, so a very small or
very large real matches itself and its neighboring floats remain distinct. Integers and floats
stay one numeric family: `36` and `36.0` compare equal, and both signed-zero spellings represent
the same value. This rule covers `=` and `IN`; range operators keep SQLite's numeric conversion.

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

These features have no GQL equivalent in the 2024 standard. The table records the current status of
each extension. They are never claimed as GQL.

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

Supported extensions remain part of the compatibility surface. They are documented on this page
and labeled pygrafito-only wherever they appear.

## Out of profile and the reserved statuses

Out of profile means the construct is rejected and is not part of the 1.0 profile. `Gated` and
`deferred` remain in the vocabulary, but no row uses either status: every in-scope construct is
supported, and every other construct is rejected.

### Out of profile

Out of profile means the construct is rejected with an explicit query error. It is a non-goal for
the 1.x series, not a deferred backlog item. Promoting one requires a separate proposal.

| Construct | Why it is out | Error contract |
| --- | --- | --- |
| Catalog statements (`CREATE GRAPH`, `DROP GRAPH`, `INSERT GRAPH`, schemas) | `pygrafito` is a single embedded graph, not a catalog. | A positioned query error before execution; no statement text runs. |
| Graph types | There is no schema or type layer. | A positioned query error before execution. |
| Sessions | There is no server or session state. | A positioned query error before execution. |
| Procedures (`CALL name(...)`) | There is no catalog or procedure registry. | A positioned query error before execution. |
| In-language transactions (`START TRANSACTION`, `COMMIT`, `ROLLBACK`) | The Python `Graph` and `Transaction` APIs own transaction boundaries. | A positioned query error before execution. |
| `SELECT` | The query surface is pattern-based, not the SQL/PGQ-style `SELECT` surface. | A positioned query error before execution. |
| Full temporal values (`DATE`, `TIME`, `TIMESTAMP`, `DURATION`) | The stored value format does not have temporal types yet. | A positioned query error before execution. |
| `CALL { ... }` | Cypher-only subquery form. Use read-only `EXISTS { ... }`, `COUNT { ... }`, or separate statements. | A positioned query error before execution. |
| Whole-map assignment (`SET n = {...}`, `SET n += {...}`) | Cypher-only convenience form. Assign or remove properties individually. | A positioned query error before execution. |
| `exists(n.prop)` | Cypher-only function form. Use `n.prop IS NOT NULL`. | A positioned query error before execution. |
| Regex predicates | Cypher-only regular-expression matching. Use `STARTS WITH`, `ENDS WITH`, and `CONTAINS` for literal predicates. | A positioned query error before execution. |
| `shortestPath()`, `allShortestPaths()` | Cypher-only path functions. Use `Graph.shortest_path`, or the supported path-search prefixes. | A positioned query error before execution. |
| Servers and drivers | The library is embedded; there is no network protocol or driver layer. | No query API exists; query text that attempts it is rejected. |
| Clustering, authentication, and multi-tenancy | There is no server, account, or tenant layer. | No query API exists; query text that attempts it is rejected. |
| Multi-graph storage | One graph handle owns one database. | No query API exists; query text that attempts it is rejected. |
| Graph-algorithm APIs | Algorithms are Python helpers, not query constructs. | No query API exists; query text that attempts it is rejected. |
| Full Cypher compatibility | Cypher convenience forms are not the target language. | A positioned query error before execution. |
| Vector search | No vector index or distance function is in the profile. | A positioned query error before execution. |
| Full-text search | No full-text index or query syntax is in the profile. | A positioned query error before execution. |

### Gated and deferred

No matrix row is `gated` or `deferred` in this release. The [conformance matrix](#conformance-matrix)
records every row as supported or out of profile. The statuses remain in the vocabulary for a
future proposal; reintroducing one requires its own change.

## Rejected forms

Rejected forms are invalid combinations of supported features, or unsupported operations that are
not separate matrix features. Each is rejected with a positioned query error before any statement
text executes. The test owner column records the focused test or corpus case that covers the form.

| Form | Why it is rejected | Error contract | Test owner |
| --- | --- | --- | --- |
| `MERGE` over a quantified pattern | `MERGE` matches one fixed-length pattern as a whole. | `QuerySemanticError` naming the quantified pattern. | `TestUnwindAndMergeAnalysis::test_merge_rejects_a_quantified_relationship` |
| `MERGE` over a path variable | A merged pattern must name one path, not bind a path value. | `QuerySemanticError` naming the path variable. | `TestUnwindAndMergeAnalysis::test_merge_rejects_a_path_variable` |
| `MERGE` over more than one pattern | `MERGE` matches one pattern as a whole. | `QuerySemanticError` naming the multiple patterns. | `TestUnwindAndMerge::test_merge_rejects_multiple_patterns` |
| `MERGE` over a relationship without one explicit label and the `-->` direction | The merged pattern must be unambiguous and create only directed relationships. | `QuerySemanticError` naming the missing label or direction. | `TestUnwindAndMergeAnalysis::test_merge_rejects_a_missing_type` and `test_merge_rejects_an_undirected_relationship` |
| `MERGE` that rebinds a relationship variable or changes a bound node | `MERGE` reuses bound anchors but does not rewrite them. | `QuerySemanticError` naming the bound element. | `TestUnwindAndMergeAnalysis::test_merge_rejects_a_bound_relationship` and `test_merge_rejects_changing_a_bound_node` |
| Mixing a legacy and a canonical quantifier in one path without an explicit mode | The two forms have different legacy defaults, so the profile refuses to guess. | `QuerySemanticError` naming the mixed quantifiers. | `TestPathModeResolution::test_mixed_quantifiers_are_rejected` |
| Catalog operations such as `INSERT GRAPH` and `CREATE GRAPH` | The library has one embedded graph and no catalog. | `QuerySemanticError` naming the catalog operation; no statement text runs. | `catalog-insert-graph-is-rejected` corpus case |

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
| `UNION` | Canonical GQL | supported | `UNION` | Set operation; `DISTINCT` is the explicit default. |
| `UNION ALL` | Canonical GQL | supported | `UNION ALL` | Set operation preserving duplicates. |
| `INTERSECT` | Canonical GQL | supported | `INTERSECT` | Set operation; `DISTINCT` is the explicit default. |
| `INTERSECT ALL` | Canonical GQL | supported | `INTERSECT ALL` | Set operation keeping `min(left, right)` copies. |
| `EXCEPT` | Canonical GQL | supported | `EXCEPT` | Set operation; `DISTINCT` is the explicit default. |
| `EXCEPT ALL` | Canonical GQL | supported | `EXCEPT ALL` | Set operation keeping `max(left - right, 0)` copies. |
| `DIFFERENT EDGES` | Canonical GQL | supported | `DIFFERENT EDGES` | Clause-wide edge uniqueness. |
| `REPEATABLE ELEMENTS` | Canonical GQL | supported | `REPEATABLE ELEMENTS` | Default; no extra constraint. |
| Grouped quantified path pattern | Canonical GQL | supported | `Grouped quantified paths` | Repeated path terms with group variable lists and inner modes. |
| `ANY` | Canonical GQL | supported | `Path search prefixes` | One deterministic shortest path per partition. |
| `ANY SHORTEST` | Canonical GQL | supported | `Path search prefixes` | One minimum-length path. |
| `ALL SHORTEST` | Canonical GQL | supported | `Path search prefixes` | Every minimum-length path. |
| `SHORTEST k` | Canonical GQL | supported | `Path search prefixes` | Up to `k` paths in increasing length. |
| `*`, `+`, `{m,}` | Canonical GQL | supported | `Open-ended quantifiers` | Open upper bound. |
| `*n..` | Compatibility construct | supported | `Open-ended quantifiers` | Legacy open upper bound; default `TRAIL`. |
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

## Conformance matrix

The matrix is the profile's honest status board. The `status` column uses exactly four values:

- **supported**: in the 1.0 profile, implemented, and covered by at least one conformance corpus
  case.
- **gated**: reserved for an in-scope construct that is not implemented yet. No row uses it.
- **deferred**: reserved for post-1.0 language direction. No row uses it.
- **out of profile**: rejected.

The `current` column records what the release does today. The `evidence` column resolves coverage:
a supported row names its corpus cases, a recognized boundary names a `rejection:` case, a
capability without query syntax names a focused `test:`, and an umbrella row points at the
rejected-forms table.

| Feature | Tier | Status | Current | Deviation | Evidence |
| --- | --- | --- | --- | --- | --- |
| `MATCH` and `OPTIONAL MATCH` | Canonical GQL | supported | implemented | None | match-program-designations |
| `INSERT` | Canonical GQL | supported | implemented | None | insert-creates-a-node |
| `SET` | Canonical GQL | supported | implemented | None | set-assigns-a-property |
| `REMOVE` | Canonical GQL | supported | implemented | None | remove-removes-a-property |
| `DELETE`, `DETACH DELETE`, `NODETACH DELETE` | Canonical GQL | supported | implemented | None | nodetach-delete-removes-a-disconnected-node |
| `FOR` with ordinality/offset | Canonical GQL | supported | implemented | None | for-ordinality-binds-one-based-position |
| `FILTER` | Canonical GQL | supported | implemented | None | filter-stage-alias, filter-matches-tiny-real |
| `LET` | Canonical GQL | supported | implemented | None | let-adds-a-binding |
| `NEXT` | Canonical GQL | supported | implemented | `YIELD` supported; no-`YIELD` and write-only segments accepted for Cypher compatibility | next-carries-an-intermediate-return |
| `FINISH` | Canonical GQL | supported | implemented | None | finish-ends-a-read-without-a-result |
| `GROUP BY` | Canonical GQL | supported | implemented | Expression keys are a pygrafito extension; `RETURN DISTINCT` is accepted | group-by-groups-and-counts |
| `RETURN` with `DISTINCT`/`ALL` or `*` | Canonical GQL | supported | implemented | `RETURN NO BINDINGS` is a pygrafito extension | return-all-is-the-default |
| `RETURN NO BINDINGS` | pygrafito extension | supported | implemented | Zero columns, one empty row per input binding; final-only | return-no-bindings-projects-empty-rows |
| `ORDER BY` with null ordering | Canonical GQL | supported | implemented | None | nulls-first-explicit |
| `OFFSET` and `SKIP` | Canonical GQL | supported | implemented | Canonical synonyms, not aliases | offset-paginates |
| `LIMIT` | Canonical GQL | supported | implemented | None | limit-bounds-the-result |
| `{n,m}` quantifier | Canonical GQL | supported | implemented | Open upper bounds are covered by `Open-ended quantifiers` | quantifier-bounded-range |
| Label expressions (and, or, not, wildcard) | Canonical GQL | supported | implemented | None | label-conjunction |
| Edge directions `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | Canonical GQL | supported | implemented | None | arrow-outgoing |
| Comments `//`, `--`, `/* ... */` | Canonical GQL | supported | implemented | `--` is a comment, not an edge alias | dash-comment |
| Inline element `WHERE` | Canonical GQL | supported | implemented | None | inline-node-predicate |
| `IS` label syntax | Canonical GQL | supported | implemented | None | label-is-form |
| Path variables | Canonical GQL | supported | implemented | None | diamond-finds-two-trails |
| Parameters | Canonical GQL | supported | implemented | None | parameters-bind-data |
| `WALK` path mode | Canonical GQL | supported | implemented | Default; bounded by the query budget | walk-reuses-a-relationship |
| `TRAIL` path mode | Canonical GQL | supported | implemented | None | trail-rejects-a-reused-relationship |
| `SIMPLE` path mode | Canonical GQL | supported | implemented | None | simple-allows-a-closed-path |
| `ACYCLIC` path mode | Canonical GQL | supported | implemented | None | acyclic-rejects-a-closed-path |
| `CREATE` for `INSERT` | Synthetic alias | supported | implemented | Data statements only | create-alias-returns-a-node |
| `UNWIND` for `FOR` | Synthetic alias | supported | implemented | None | unwind-alias-iterates |
| Stage `WHERE` for `FILTER` | Synthetic alias | supported | implemented | `MATCH ... WHERE` stays canonical | stage-where-alias-filters |
| `-->`, `<--`, `--` for `->`, `<-`, `-` | Synthetic alias | supported | implemented | `-->` and `<--` are aliases; `--` is a comment, not an edge | arrow-double-dash-alias |
| `:A:B` for `:A&B` | Synthetic alias | supported | implemented | None | label-colon-conjunction-alias |
| Legacy `*n..m` quantifier | Compatibility construct | supported | implemented | Default `TRAIL` | legacy-quantifier-trails |
| `MERGE` with conditional updates | pygrafito extension | supported | implemented | No GQL equivalent; invalid forms are rejected | merge-conditional-updates |
| `WITH` projection and aggregation | pygrafito extension | supported | implemented | No GQL equivalent; `WITH *` is supported | with-aggregation |
| Implicit grouping | pygrafito extension | supported | implemented | `GROUP BY` alternative | implicit-grouping |
| `type()` | pygrafito extension | supported | implemented | `LABELS()` alternative | type-extension |
| Query budget | pygrafito extension | supported | implemented | No GQL equivalent; expansion, row, and optional time counters | budget-row-limit |
| `CASE` | Canonical GQL | supported | implemented | Simple and searched forms | case-searched-classifies-programs |
| Map literals | Canonical GQL | supported | implemented | `{key: expression}` | map-literal-projects-fields |
| List indexing and slicing | Canonical GQL | supported | implemented | Index and slice access | list-index-and-slice |
| List comprehensions | Canonical GQL | supported | implemented | List-producing expression | list-comprehension-filters-and-doubles |
| String concatenation | Canonical GQL | supported | implemented | Canonical double-pipe operator; `+` is a compatibility alias for string operands | string-concatenation-and-plus-alias |
| Path functions | Canonical GQL | supported | implemented | `nodes`, `relationships`, `length` | path-functions-expose-a-path |
| Extended scalar functions | Canonical GQL | supported | implemented | `range`, `head`, `last`, `tail`, `reverse`, `split`, `substring`, `replace`, `toBoolean`, `round`, `ceil`, `floor` | extended-scalar-functions |
| `WITH *` | pygrafito extension | supported | implemented | Part of the `WITH` extension | with-star-preserves-scope |
| `EXISTS { ... }` | Canonical GQL | supported | implemented | Read-only correlated and uncorrelated subquery | exists-correlated-programs |
| `COUNT { ... }` | Canonical GQL | supported | implemented | Read-only correlated and uncorrelated subquery | count-correlated-trusts |
| `UNION` | Canonical GQL | supported | implemented | Set operation; `DISTINCT` is the explicit default | union-deduplicates-program-and-user |
| `UNION ALL` | Canonical GQL | supported | implemented | Set operation with duplicates | union-all-preserves-duplicates |
| `INTERSECT` | Canonical GQL | supported | implemented | Set operation; `DISTINCT` is the explicit default | intersect-keeps-program-names |
| `INTERSECT ALL` | Canonical GQL | supported | implemented | Multiset intersection keeping `min(left, right)` copies | intersect-all-keeps-the-smaller-count, intersect-all-uses-canonical-equality |
| `EXCEPT` | Canonical GQL | supported | implemented | Set operation; `DISTINCT` is the explicit default | except-removes-program-names |
| `EXCEPT ALL` | Canonical GQL | supported | implemented | Multiset difference keeping `max(left - right, 0)` copies | except-all-subtracts-counts, except-all-returns-nothing-when-right-is-larger, except-all-keeps-unmatched-duplicates, set-quantifiers-chain-left-to-right |
| `DIFFERENT EDGES` | Canonical GQL | supported | implemented | Match mode; applies across every path of one clause | different-edges-shared-edge, different-edges-quantified, different-edges-two-patterns, different-edges-parallel |
| `REPEATABLE ELEMENTS` | Canonical GQL | supported | implemented | Match mode; default and no extra constraint | repeatable-elements-shared-edge |
| Grouped quantified paths | Canonical GQL | supported | implemented | Parenthesized path repetition with list bindings, nested flattening, zero iterations, and inner modes | grouped-fixed-repetition, grouped-bounded-diamond, grouped-list-bindings, grouped-zero-iterations, grouped-nested, grouped-inner-mode |
| Path search prefixes | Canonical GQL | supported | implemented | `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`; partitioned by first and last node with the documented tie-break | any-per-partition, any-shortest-diamond, all-shortest-diamond, shortest-k-parallel, shortest-k-zero, shortest-self-loop |
| Open-ended quantifiers | Canonical GQL | supported | implemented | Open forms `*`, `+`, `*n..`, `{m,}` with demand-driven limits; `Unbounded WALK` is not a separate row | open-star, open-plus, open-canonical-tail, open-legacy-tail, unbounded-walk-limit, unbounded-trail-cycle, unbounded-zero-hop |
| Catalog statements | Out of profile | out of profile | rejected | Embedded single graph | rejection:catalog-insert-graph-is-rejected, rejection:create-graph-is-rejected, rejection:drop-graph-is-rejected |
| Graph types | Out of profile | out of profile | rejected | No schema layer | test:TestOutOfProfileSurface::test_capability_is_absent |
| Sessions | Out of profile | out of profile | rejected | No server state | test:TestOutOfProfileSurface::test_capability_is_absent |
| Procedures | Out of profile | out of profile | rejected | No catalog | rejection:procedure-call-is-rejected |
| In-language transactions | Out of profile | out of profile | rejected | Python API owns transactions | rejection:start-transaction-is-rejected, rejection:commit-is-rejected |
| `SELECT` | Out of profile | out of profile | rejected | Pattern query surface only | rejection:select-statement-is-rejected |
| Full temporal values | Out of profile | out of profile | rejected | No temporal storage | rejection:date-literal-is-rejected |
| `CALL { ... }` | Out of profile | out of profile | rejected | Cypher-only subquery form | rejection:call-subquery-is-rejected |
| Whole-map assignment | Out of profile | out of profile | rejected | Cypher-only convenience form | rejection:whole-map-assignment-is-rejected, rejection:whole-map-addition-is-rejected |
| `exists(n.prop)` | Out of profile | out of profile | rejected | Use `n.prop IS NOT NULL` | rejection:exists-function-is-rejected |
| Regex predicates | Out of profile | out of profile | rejected | Cypher-only regular-expression matching | rejection:regex-predicate-is-rejected |
| `shortestPath()` | Out of profile | out of profile | rejected | Cypher-only path function | rejection:shortest-path-is-rejected, rejection:all-shortest-paths-is-rejected |
| Servers and drivers | Out of profile | out of profile | rejected | Embedded library only | test:TestOutOfProfileSurface::test_capability_is_absent |
| Clustering, authentication, and multi-tenancy | Out of profile | out of profile | rejected | No server or account layer | test:TestOutOfProfileSurface::test_capability_is_absent |
| Multi-graph storage | Out of profile | out of profile | rejected | One database per handle | test:TestOutOfProfileSurface::test_capability_is_absent |
| Graph-algorithm APIs | Out of profile | out of profile | rejected | Python helpers only | test:TestOutOfProfileSurface::test_capability_is_absent |
| Full Cypher compatibility | Out of profile | out of profile | rejected | GQL-first profile | rejected forms |
| Vector search | Out of profile | out of profile | rejected | No vector index or distance function | test:TestOutOfProfileSurface::test_capability_is_absent |
| Full-text search | Out of profile | out of profile | rejected | No full-text index or syntax | test:TestOutOfProfileSurface::test_capability_is_absent |

Evidence resolves to one of three owners. `rejection:<case>` is a recognized boundary with a
rejection corpus case; `test:<Class>::<method>` is a capability with no query syntax, covered by
a focused surface test; and `rejected forms` points at the rejected-forms table. A supported row
names its corpus cases instead.

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
tags       optional: canonical, alias, compatibility, extension, rejection
budget     optional: per-case query-budget overrides, such as {"max_rows": 2}
```

The feature id is derived from the first matrix column: lower-case it and replace every run of
non-alphanumeric characters with a hyphen. Four rows carry an explicit id because the derived one
would be ambiguous: `edge-direction-aliases`, `label-conjunction-alias`, `quantifier`, and
`legacy-quantifier`. A case tagged `rejection` must name an out-of-profile row, expect an error,
and assert a message fragment containing ` is not supported: `.

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
`supported` row needs a case, every case needs a matrix row, and every out-of-profile row needs a
rejection case or a focused surface test. A rejection case states the boundary in the same way:

```json
{
  "name": "select-statement-is-rejected",
  "feature": "select",
  "fixture": "tron-labels",
  "query": "SELECT 1",
  "expect": {
    "error": {
      "type": "QuerySemanticError",
      "contains": "SELECT is not supported: use MATCH ... RETURN"
    }
  },
  "tags": ["rejection"]
}
```

### Path corpus cases

Every path-engine row is supported and carries its corpus cases:

| Matrix row | Corpus cases |
| --- | --- |
| `Path search prefixes` | `any-per-partition`, `any-shortest-diamond`, `all-shortest-diamond`, `shortest-k-parallel`, `shortest-k-zero`, `shortest-self-loop` |
| `Grouped quantified paths` | `grouped-fixed-repetition`, `grouped-bounded-diamond`, `grouped-list-bindings`, `grouped-zero-iterations`, `grouped-nested`, `grouped-inner-mode` |

Every case uses a TRON-themed fixture and tags `canonical` or `compatibility` as appropriate.

## 1.0 release gate

The 1.0 release met this gate before publication. Tests in `tests/test_gql_profile.py` enforce the
profile-side items automatically:

1. **No gated or deferred rows.** Every matrix row is `supported` or `out of profile`. Checked by
   `TestGqlProfile::test_release_gate`, which fails on either status.
2. **Every supported row has a corpus case.** Checked by
   `TestGqlProfile::test_every_supported_row_has_a_case` and the data-driven corpus.
3. **Every out-of-profile row and rejected form has an explicit rejection test.** Checked by
   `TestGqlProfile::test_release_gate`, which resolves each evidence cell to a `rejection` corpus
   case, a focused surface test, or the rejected-forms table.
4. **Matrix, inventory, prose, grammar summary, query-language reference, and tours agree.**
   Checked by the inventory and prose checks in `TestGqlProfile::test_release_gate` plus review of
   the grammar summary and tours.
5. **Quality checks pass.** `hatch check --fix`, `hatch test`, and `hatch run docs:build` pass;
   coverage is at least 80%.
6. **The 1.0 hardening work is complete.** Fuzz and property tests, crash and recovery tests,
   cross-platform CI, the frozen formats, the migration policy, and the public API contract shipped
   with 1.0.
7. **Package smoke tests pass.** The built wheel installs in a clean environment, and `py.typed`
   and `LICENSE.txt` are packaged; checked by the package CI job.
8. **Release material exists.** The 1.0 changelog section exists, and the migration guidance and
   out-of-profile list on this page are current.
9. **The version is 1.0.0.**

The profile-side checks were implemented before 1.0. Later feature changes update their own cases
and status rows; the gate fails if they drift.

## Profile freeze policy

The 1.0 profile is frozen.

- After 1.0, a construct may be added in a minor release only when it does not change the meaning
  of an existing supported construct. The same change updates the profile, matrix, inventory,
  query-language reference, tours, and corpus.
- A change that alters the meaning of a supported construct requires a major version and a
  migration section.
- Promoting an out-of-profile construct requires a separate proposal. It is not a deferred
  backlog item.
- `deferred` remains available for post-1.0 direction, but a deferred construct is not part of the
  1.0 profile.

## Migration guidance

The profile is the 1.x contract. Earlier spellings remain accepted through the compatibility
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
| `*` when at least one hop is intended | `+` or `{1,}` | `*` includes zero-hop matches. |
| An open `WALK` without `LIMIT` | `LIMIT`, a search prefix, or `TRAIL` | An unbounded walk fails on the budget instead of returning a truncated result. |
| `-->`, `<--`, `--` | `->`, `<-`, `-` | `-->` and `<--` remain aliases; `--` is a comment. |
| No path mode | `WALK` default | Use `MATCH TRAIL` for the old trail behavior. |
| Unquoted `different`, `edges`, `repeatable`, `elements` identifiers | Backtick-quoted names | These words are now reserved keywords; quote existing variables or aliases that use them. |
| Unquoted `any`, `shortest` identifiers | Backtick-quoted names | These words are reserved keywords; quote existing variables or aliases that use them. |
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
complete. A feature is marked `supported` only after its corpus case exists and passes in CI. An
out-of-profile row without evidence is a profile defect.

The project does not claim ISO conformance beyond this matrix. Use "GQL profile" or
"GQL-first profile" in documentation and release notes, not "GQL compliant".
