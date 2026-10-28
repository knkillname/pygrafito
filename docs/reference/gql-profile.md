# GQL profile

This page is the target language profile for `pygrafito`. It defines the canonical GQL surface,
the compatibility aliases and constructs, the pygrafito extensions, the path-mode and query-budget
policy, and how conformance is claimed. It is the contract for the query-language changes that
follow.

:::{warning}
The current release still uses the transitional Cypher-flavored dialect described in the
[query-language reference](query-language.md). This page is the target profile, not a description
of what the current release executes. Canonical forms are marked **target** or **gated** until the
frontend, budget, and path-semantics changes land.
:::

## Current status

The profile is deliberately ahead of the implementation. The current release remains the
transitional dialect so existing examples keep working while the language is rewritten in small
changes.

| Area | Current release | Target profile |
| --- | --- | --- |
| Data modification | `CREATE`, `MERGE`, `SET`, `REMOVE`, `DELETE` | `INSERT` canonical, `CREATE` alias, `MERGE` extension |
| Iteration | `UNWIND` | `FOR` canonical, `UNWIND` alias |
| Filtering | `WHERE` after `MATCH` or `WITH` | `FILTER` canonical, stage `WHERE` alias, `MATCH ... WHERE` canonical |
| Binding and composition | `WITH` | `LET` and `NEXT` canonical, `WITH` extension |
| Grouping | Implicit grouping | `GROUP BY` canonical, implicit grouping extension |
| Quantifiers | Bounded `*n..m`, trail semantics | `{n,m}` canonical, legacy `*n..m` compatibility construct |
| Edge directions | `-->`, `<--`, `--` | GQL directions canonical, double-dash forms aliases |
| Comments | `//` and `/* ... */` | `//`, `--`, and `/* ... */` |
| Path modes | Trail only | `WALK` default, `TRAIL`, `SIMPLE`, and `ACYCLIC` in scope |
| Query budget | None | Expansion and intermediate-row counters, gating `WALK` |

The runnable examples in `README.md` and the quickstart stay on the current dialect until the
frontend change lands. The profile does not claim that the current release executes the canonical
forms below.

## The five tiers

Every supported query construct belongs to exactly one tier.

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
| Composition | `NEXT` | Starts the next statement from the previous binding table. |
| Grouping | `GROUP BY` | Explicit grouping; implicit grouping is an extension. |
| Projection | `RETURN`, `RETURN DISTINCT`, `RETURN ALL` | `RETURN *` and `RETURN NO BINDINGS` are in scope. |
| Ordering and pagination | `ORDER BY`, `OFFSET`, `SKIP`, `LIMIT` | `ASC`/`ASCENDING`, `DESC`/`DESCENDING`, and `NULLS FIRST`/`NULLS LAST` are in scope. |
| Quantifiers | `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, `+` | Placement follows the GQL path-pattern grammar. |
| Labels | Conjunction, disjunction, negation, wildcard | Node and edge label expressions; `IS` is accepted in place of `:`. |
| Edge directions | `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | `-` is any direction; `~` is undirected only. |
| Comments | `//`, `--`, `/* ... */` | `--` is a GQL line comment; legacy double-dash arrows are an alias. |
| Path variables | `p = <path pattern>` | Paths expose their nodes and relationships in traversal order. |
| Parameters | `$name` | Bound as data, never as identifiers or SQL text. |
| Path modes | `WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC` | `WALK` is the canonical default, gated on the query budget. |

Label expressions use `&` for conjunction, `|` for disjunction, `!` for negation, and `%` for the
wildcard. For example, `(:Program&:ISO)` matches a node carrying both labels, and
`(:Program|:Agent)` matches either one.

Target GQL example:

```text
// Target GQL, not yet executable in the current release.
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
| `-->`, `<--`, `--` | `->`, `<-`, `-` | Pattern arrows. `--` as a comment is disambiguated by the frontend grammar. |
| `:A:B` | `:A&B` | Node label conjunction. |

`SKIP` is not an alias: GQL defines both `SKIP` and `OFFSET` as canonical synonyms.

The legacy double-dash arrows collide with the GQL `--` line comment. The frontend change must
define the disambiguation so a `--` comment is never silently reinterpreted as an edge, and a
legacy `-->` or `<--` arrow is never truncated into a comment.

## Compatibility construct: the legacy quantifier

The legacy Cypher quantifier is a compatibility construct. It keeps its Cypher default of
relationship-unique trails.

| Form | Default path mode | Notes |
| --- | --- | --- |
| `*n`, `*n..m`, `*0..m` | `TRAIL` | Cypher-compatible. The current profile requires a finite upper bound. |
| `{n}`, `{m,n}`, `{,n}`, `{m,}` | `WALK` (target) | GQL canonical. `*` and `+` are unbounded GQL forms and are deferred. |
| Explicit `WALK`, `TRAIL`, `SIMPLE`, or `ACYCLIC` | The explicit mode | Overrides both defaults. |

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
MATCH (a)-[:ALLIES_WITH{1,3}]->(b)          -- canonical: WALK (target)
MATCH WALK (a)-[:ALLIES_WITH*1..3]->(b)     -- explicit WALK wins
MATCH TRAIL (a)-[:ALLIES_WITH{1,3}]->(b)    -- explicit TRAIL wins
```

The current release is trail-only and requires an upper bound. The canonical and explicit-mode
forms above are target behavior until the path-semantics change lands.

## Path modes

| Mode | Rule | Profile status |
| --- | --- | --- |
| `WALK` | Repeated nodes and relationships are allowed. | Canonical default; gated on the query budget. |
| `TRAIL` | A relationship may not repeat within one path; nodes may repeat. | In scope; matches the current engine and the Python `paths()` API. |
| `SIMPLE` | Nodes may not repeat, except that the start and end may be the same. | In scope; gated. |
| `ACYCLIC` | No node may repeat. | In scope; gated. |
| Match modes | `DIFFERENT EDGES` and `REPEATABLE ELEMENTS`. | Deferred until their interaction with path modes is defined. |
| Grouped quantified paths | Repetition of a parenthesized path pattern. | Deferred. |
| Path search | `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`. | Deferred. |
| Unbounded `WALK` | `*`, `+`, `{m,}` in `WALK` mode. | Deferred until lazy traversal and the budget land. |

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

The current release has no query budget. The `WALK` row in the matrix is therefore gated.

## Extensions

These features are supported by `pygrafito` but have no GQL equivalent in the 2024 standard. They
are never claimed as GQL.

| Extension | Why it stays | Canonical alternative |
| --- | --- | --- |
| `MERGE` with `ON CREATE SET` and `ON MATCH SET` | Upsert is essential for imports and sync. | None in GQL 2024. |
| `WITH` projection, aggregation, and pagination | A compact scope-reset stage. | `LET` + `NEXT` + `GROUP BY`. |
| Implicit grouping | Compatibility with the transitional dialect and concise queries. | `GROUP BY`. |
| `type()` | Returns the first sorted relationship label. | `LABELS()` returns the full sorted label list. |

Extensions remain part of the supported compatibility surface. They are documented on this page
and labeled pygrafito-only wherever they appear.

## Out of profile and deferred

Out of profile means the construct is rejected with an explicit query error. Deferred means the
construct is in the long-term GQL direction but not in the initial profile; it is gated in the
matrix rather than rejected forever.

### Out of profile

| Construct | Why it is out |
| --- | --- |
| Catalog statements (`CREATE GRAPH`, `DROP GRAPH`, schemas) | `pygrafito` is a single embedded graph, not a catalog. |
| Graph types | There is no schema or type layer. |
| Sessions | There is no server or session state. |
| Procedures | There is no catalog or procedure registry. |
| In-language transactions | The Python `Graph` and `Transaction` APIs own transaction boundaries. |
| `SELECT` | The query surface is pattern-based, not the SQL/PGQ-style `SELECT` surface. |
| Full temporal values (`DATE`, `TIME`, `TIMESTAMP`, `DURATION`) | The stored value format does not have temporal types yet. |

### Deferred

| Construct | Gate |
| --- | --- |
| Match modes (`DIFFERENT EDGES`, `REPEATABLE ELEMENTS`) | The path-semantics change must define their interaction with path modes. |
| Grouped quantified path patterns | The path-semantics change needs a nested path-pattern representation. |
| Path search prefixes (`ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`) | Review after the shortest-path API and path modes settle. |
| Unbounded `WALK` | Requires lazy traversal or frontier expansion plus the query budget. |

## Conformance matrix

The matrix is the profile's honest status board. The `status` column uses exactly four values:

- **supported**: in the profile, implemented, and covered by at least one conformance corpus case.
- **gated**: in the profile, but implementation or corpus coverage is still pending.
- **deferred**: in the long-term direction but not in the initial profile.
- **out of profile**: rejected.

The `current` column records what the transitional dialect does today. A `gated` row may already
be implemented in the current dialect; it becomes `supported` only when the canonical form and its
corpus case land. The corpus column is `pending` until the case exists.

| Feature | Tier | Status | Current | Deviation | Corpus |
| --- | --- | --- | --- | --- | --- |
| `MATCH` and `OPTIONAL MATCH` | Canonical GQL | gated | implemented | None | pending |
| `INSERT` | Canonical GQL | gated | not implemented (`CREATE` alias) | None | pending |
| `SET` | Canonical GQL | gated | implemented | None | pending |
| `REMOVE` | Canonical GQL | gated | implemented | None | pending |
| `DELETE`, `DETACH DELETE`, `NODETACH DELETE` | Canonical GQL | gated | implemented; explicit `NODETACH` pending | `NODETACH` keyword pending | pending |
| `FOR` with ordinality/offset | Canonical GQL | gated | not implemented (`UNWIND` alias) | Ordinality not implemented | pending |
| `FILTER` | Canonical GQL | gated | not implemented (stage `WHERE` alias) | None | pending |
| `LET` | Canonical GQL | gated | not implemented | None | pending |
| `NEXT` | Canonical GQL | gated | not implemented | One result per call; final `RETURN` only | pending |
| `GROUP BY` | Canonical GQL | gated | implicit grouping only | Explicit grouping target | pending |
| `RETURN` with `DISTINCT`/`ALL` or `*` | Canonical GQL | gated | `DISTINCT` implemented; `ALL` and `*` pending | `ALL` and `*` pending | pending |
| `ORDER BY` with null ordering | Canonical GQL | gated | implemented; `NULLS FIRST/LAST` pending | Null ordering pending | pending |
| `OFFSET` and `SKIP` | Canonical GQL | gated | `SKIP` implemented; `OFFSET` pending | `OFFSET` spelling pending | pending |
| `LIMIT` | Canonical GQL | gated | implemented | None | pending |
| `{n,m}` quantifier | Canonical GQL | gated | not implemented (legacy `*n..m`) | Canonical quantifier pending | pending |
| Label expressions (and, or, not, wildcard) | Canonical GQL | gated | conjunction and edge alternatives only | Full expressions pending | pending |
| Edge directions `->`, `<-`, `-`, `~` | Canonical GQL | gated | `-->`, `<--`, `--` only | Single-dash and `~` pending | pending |
| Comments `//`, `--`, `/* ... */` | Canonical GQL | gated | `//` and `/* ... */` only | `--` comments pending | pending |
| Inline element `WHERE` | Canonical GQL | gated | not implemented | None | pending |
| `IS` label syntax | Canonical GQL | gated | `:` only | `IS` pending | pending |
| Path variables | Canonical GQL | gated | implemented | None | pending |
| Parameters | Canonical GQL | gated | implemented | None | pending |
| `WALK` path mode | Canonical GQL | gated | not implemented | Gated on the query budget | pending |
| `TRAIL` path mode | Canonical GQL | gated | implicit trail only | Explicit keyword pending | pending |
| `SIMPLE` path mode | Canonical GQL | gated | not implemented | None | pending |
| `ACYCLIC` path mode | Canonical GQL | gated | not implemented | None | pending |
| `CREATE` for `INSERT` | Synthetic alias | gated | implemented | Data statements only | pending |
| `UNWIND` for `FOR` | Synthetic alias | gated | implemented | None | pending |
| Stage `WHERE` for `FILTER` | Synthetic alias | gated | implemented | `MATCH ... WHERE` stays canonical | pending |
| `-->`, `<--`, `--` for `->`, `<-`, `-` | Synthetic alias | gated | implemented | `--` comment disambiguation pending | pending |
| `:A:B` for `:A&B` | Synthetic alias | gated | implemented | Nodes only | pending |
| Legacy `*n..m` quantifier | Compatibility construct | gated | implemented, bounded trail | Default `TRAIL` | pending |
| `MERGE` with conditional updates | pygrafito extension | gated | implemented | No GQL equivalent | pending |
| `WITH` projection and aggregation | pygrafito extension | gated | implemented | No GQL equivalent | pending |
| Implicit grouping | pygrafito extension | gated | implemented | `GROUP BY` alternative | pending |
| `type()` | pygrafito extension | gated | implemented | `LABELS()` alternative | pending |
| Match modes | Deferred | deferred | not implemented | `DIFFERENT EDGES` / `REPEATABLE ELEMENTS` | n/a |
| Grouped quantified paths | Deferred | deferred | not implemented | Parenthesized path repetition | n/a |
| Path search prefixes | Deferred | deferred | not implemented | `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k` | n/a |
| Unbounded `WALK` | Deferred | deferred | not implemented | Lazy traversal plus budget | n/a |
| Catalog statements | Out of profile | out of profile | rejected | Embedded single graph | n/a |
| Graph types | Out of profile | out of profile | rejected | No schema layer | n/a |
| Sessions | Out of profile | out of profile | rejected | No server state | n/a |
| Procedures | Out of profile | out of profile | rejected | No catalog | n/a |
| In-language transactions | Out of profile | out of profile | rejected | Python API owns transactions | n/a |
| `SELECT` | Out of profile | out of profile | rejected | Pattern query surface only | n/a |
| Full temporal values | Out of profile | out of profile | rejected | No temporal storage | n/a |

No feature is `supported` yet because the conformance corpus is a follow-up. This page therefore
claims a profile, not ISO conformance.

## Conformance corpus

The corpus is data-driven so the matrix can require coverage without a bespoke test harness. Each
case has this shape:

```text
name       unique kebab-case identifier
feature    matrix feature id
fixture    seed statements or a named TRON-themed fixture
query      statement text
params     optional parameter mapping
expect     projected rows, or an error type and message fragment
tags       optional: canonical, alias, compatibility, extension, deviation
```

Example case:

```yaml
name: gql-walk-reuses-an-edge
feature: walk-path-mode
fixture: tron-cycle
query: MATCH (a)-[:ALLIES_WITH{1,3}]->(b) RETURN b
expect:
  rows:
    - b: {designation: Quorra}
tags: [canonical, path-mode]
```

The runner belongs to the frontend change and runs in CI. A feature is marked `supported` only
after at least one case covers it. A regression fails CI with the case name and feature id.

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
| `*1..3` | `{1,3}` | The legacy form keeps `TRAIL`; the canonical form uses `WALK`. |
| `-->`, `<--`, `--` | `->`, `<-`, `-` | Double-dash forms remain aliases. |
| No path mode | `WALK` default | Use `MATCH TRAIL` for the old trail behavior. |
| `type(r)` | `LABELS(r)` | `type()` remains an extension. |
| `MERGE` | No GQL equivalent | `MERGE` remains an extension. |

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
matrix, and the conformance corpus in the same change. A construct added without a profile entry
or a corpus case is not complete. A feature is marked `supported` only after its corpus case
exists and passes in CI.

The project does not claim ISO conformance beyond this matrix. Use "GQL profile" or
"GQL-first profile" in documentation and release notes, not "GQL compliant".
