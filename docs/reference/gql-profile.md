# GQL profile

This page is the target language profile for `pygrafito`. It defines the canonical GQL surface,
the compatibility aliases and constructs, the pygrafito extensions, the path-mode and query-budget
policy, and how conformance is claimed. It is the contract for the query-language changes that
follow.

:::{note}
This page is both the language profile and its conformance status board. Canonical spellings are
executable except the rows marked **deferred**; a deferred construct raises a positioned error that
names the follow-up change. The [query-language reference](query-language.md) describes the
executable dialect.
:::

## Current status

Path semantics, the query budget, and the composition surface are implemented. The remaining
language gap is the expression vocabulary, which follows in a separate change.

| Area | Implemented | Target |
| --- | --- | --- |
| Data modification | `INSERT`, `SET`, `REMOVE`, `DELETE`, `DETACH DELETE`, `NODETACH DELETE`; `CREATE` alias; `MERGE` extension | `INSERT` canonical, `CREATE` alias, `MERGE` extension |
| Iteration | `FOR`; `UNWIND` alias; `WITH ORDINALITY` and `WITH OFFSET` | `FOR` canonical, `UNWIND` alias |
| Filtering | `FILTER`, stage `WHERE` alias, `MATCH ... WHERE` | `FILTER` canonical, stage `WHERE` alias, `MATCH ... WHERE` canonical |
| Binding and composition | `LET`, `NEXT` with `YIELD`, `FINISH`; `WITH` extension | `LET`, `NEXT`, and `FINISH` canonical, `WITH` extension |
| Grouping | `GROUP BY`, including `GROUP BY ()`; implicit grouping extension | `GROUP BY` canonical, implicit grouping extension |
| Quantifiers | Closed `{n}`, `{m,n}`, `{,n}`; legacy `*n..m` with `TRAIL`; open bounds deferred | `{n,m}` canonical, legacy `*n..m` compatibility construct |
| Edge directions | `->`, `<-`, `-`, `~`, `<->`, `<~`, `~>`; `-->` and `<--` aliases; `--` is a comment | GQL directions canonical, double-dash forms aliases |
| Comments | `//`, `--`, and `/* ... */` | `//`, `--`, and `/* ... */` |
| Path modes | `WALK` default; `TRAIL`, `SIMPLE`, `ACYCLIC` explicit | `WALK` default, `TRAIL`, `SIMPLE`, `ACYCLIC` in scope |
| Query budget | Expansion, row, and optional time counters with per-query override | Expansion and intermediate-row counters, gating `WALK` |

The runnable examples in `README.md`, the quickstart, and the guides use the canonical spellings
where the release supports them; compatibility aliases appear only in the migration guidance.

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
| Composition | `NEXT [YIELD column [AS alias] [, ...]]` | Starts the next segment from the preceding `RETURN`; without `YIELD` every column passes. |
| Grouping | `GROUP BY key [, ...]`, `GROUP BY ()` | Explicit grouping; implicit grouping is an extension. Expression keys are an extension. |
| Projection | `RETURN`, `RETURN DISTINCT`, `RETURN ALL`, `FINISH` | `RETURN *` is canonical; `RETURN NO BINDINGS` is a pygrafito extension. |
| Ordering and pagination | `ORDER BY`, `OFFSET`, `SKIP`, `LIMIT` | `ASC`/`ASCENDING`, `DESC`/`DESCENDING`, and `NULLS FIRST`/`NULLS LAST` are in scope. |
| Quantifiers | `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, `+` | Placement follows the GQL path-pattern grammar. |
| Labels | Conjunction, disjunction, negation, wildcard | Node and edge label expressions; `IS` is accepted in place of `:`. |
| Edge directions | `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | `-` is any direction; `~` is undirected only. |
| Comments | `//`, `--`, `/* ... */` | `--` is a GQL line comment; legacy double-dash arrows are an alias. |
| Path variables | `p = <path pattern>` | Paths expose their nodes and relationships in traversal order. |
| Parameters | `$name` | Bound as data, never as identifiers or SQL text. |
| Path modes | `WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC` | `WALK` is the canonical default, bounded by the query budget. |

Label expressions use `&` for conjunction, `|` for disjunction, `!` for negation, and `%` for the
wildcard. For example, `(:Program&:ISO)` matches a node carrying both labels, and
`(:Program|:Agent)` matches either one.

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
MATCH (a)-[:ALLIES_WITH{1,3}]->(b)          -- canonical: WALK
MATCH WALK (a)-[:ALLIES_WITH*1..3]->(b)     -- explicit WALK wins
MATCH TRAIL (a)-[:ALLIES_WITH{1,3}]->(b)    -- explicit TRAIL wins
```

The canonical closed forms require an explicit upper bound. An open upper bound (`*`, `+`, `*n..`,
and `{m,}`) is deferred and names its follow-up change.

## Path modes

| Mode | Rule | Profile status |
| --- | --- | --- |
| `WALK` | Repeated nodes and relationships are allowed. | Canonical default; supported while the query budget is enforced. |
| `TRAIL` | A relationship may not repeat within one path; nodes may repeat. | Supported; also the default for the legacy quantifier. |
| `SIMPLE` | Nodes may not repeat, except that the start and end may be the same. | Supported. |
| `ACYCLIC` | No node may repeat. | Supported. |
| Match modes | `DIFFERENT EDGES` and `REPEATABLE ELEMENTS`. | Deferred until their interaction with path modes is defined. |
| Grouped quantified paths | Repetition of a parenthesized path pattern. | Deferred. |
| Path search | `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`. | Deferred. |
| Open-ended quantifiers | `*`, `+`, `*n..`, and `{m,}` in any mode. | Deferred until lazy traversal lands. |

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

These features are supported by `pygrafito` but have no GQL equivalent in the 2024 standard. They
are never claimed as GQL.

| Extension | Why it stays | Canonical alternative |
| --- | --- | --- |
| `MERGE` with `ON CREATE SET` and `ON MATCH SET` | Upsert is essential for imports and sync. | None in GQL 2024. |
| `WITH` projection, aggregation, and pagination | A compact scope-reset stage. | `LET` + `NEXT` + `GROUP BY`. |
| Implicit grouping | Compatibility with the transitional dialect and concise queries. | `GROUP BY`. |
| `RETURN NO BINDINGS` | Zero-column debugging and internal result shape. | `FINISH`, or `RETURN` with the columns you need. |
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
| Open-ended quantifiers (`*`, `+`, `*n..`, `{m,}`) | Requires lazy traversal or frontier expansion; the budget already protects bounded walks. |

## Conformance matrix

The matrix is the profile's honest status board. The `status` column uses exactly four values:

- **supported**: in the profile, implemented, and covered by at least one conformance corpus case.
- **gated**: in the profile, but implementation or corpus coverage is still pending.
- **deferred**: in the long-term direction but not in the initial profile.
- **out of profile**: rejected.

The `current` column records what the release does today. A `gated` row may already
be implemented in the current dialect; it becomes `supported` only when the canonical form and its
corpus case land. The corpus column is `pending` until the case exists.

| Feature | Tier | Status | Current | Deviation | Corpus |
| --- | --- | --- | --- | --- | --- |
| `MATCH` and `OPTIONAL MATCH` | Canonical GQL | supported | implemented | None | match-program-designations |
| `INSERT` | Canonical GQL | supported | implemented | None | insert-creates-a-node |
| `SET` | Canonical GQL | supported | implemented | None | set-assigns-a-property |
| `REMOVE` | Canonical GQL | supported | implemented | None | remove-removes-a-property |
| `DELETE`, `DETACH DELETE`, `NODETACH DELETE` | Canonical GQL | supported | implemented | None | nodetach-delete-removes-a-disconnected-node |
| `FOR` with ordinality/offset | Canonical GQL | supported | implemented | None | for-ordinality-binds-one-based-position |
| `FILTER` | Canonical GQL | supported | implemented | None | filter-stage-alias |
| `LET` | Canonical GQL | supported | implemented | None | let-adds-a-binding |
| `NEXT` | Canonical GQL | supported | implemented | `YIELD` supported; no-`YIELD` and write-only segments accepted for Cypher compatibility | next-carries-an-intermediate-return |
| `FINISH` | Canonical GQL | supported | implemented | None | finish-ends-a-read-without-a-result |
| `GROUP BY` | Canonical GQL | supported | implemented | Expression keys are a pygrafito extension; `RETURN DISTINCT` is accepted | group-by-groups-and-counts |
| `RETURN` with `DISTINCT`/`ALL` or `*` | Canonical GQL | supported | implemented | `RETURN NO BINDINGS` is a pygrafito extension | return-all-is-the-default |
| `RETURN NO BINDINGS` | pygrafito extension | supported | implemented | Zero columns, one empty row per input binding; final-only | return-no-bindings-projects-empty-rows |
| `ORDER BY` with null ordering | Canonical GQL | supported | implemented | None | nulls-first-explicit |
| `OFFSET` and `SKIP` | Canonical GQL | supported | implemented | None | offset-paginates |
| `LIMIT` | Canonical GQL | supported | implemented | None | limit-bounds-the-result |
| `{n,m}` quantifier | Canonical GQL | supported | implemented | Open upper bounds deferred | quantifier-bounded-range |
| Label expressions (and, or, not, wildcard) | Canonical GQL | supported | implemented | None | label-conjunction |
| Edge directions `->`, `<-`, `-`, `~`, `<~`, `~>`, `<->` | Canonical GQL | supported | implemented | None | arrow-outgoing |
| Comments `//`, `--`, `/* ... */` | Canonical GQL | supported | implemented | None | dash-comment |
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
| `-->`, `<--`, `--` for `->`, `<-`, `-` | Synthetic alias | supported | implemented | `--` is a comment, not an alias | arrow-double-dash-alias |
| `:A:B` for `:A&B` | Synthetic alias | supported | implemented | None | label-colon-conjunction-alias |
| Legacy `*n..m` quantifier | Compatibility construct | supported | implemented | Default `TRAIL` | legacy-quantifier-trails |
| `MERGE` with conditional updates | pygrafito extension | supported | implemented | No GQL equivalent | merge-conditional-updates |
| `WITH` projection and aggregation | pygrafito extension | supported | implemented | No GQL equivalent | with-aggregation |
| Implicit grouping | pygrafito extension | supported | implemented | `GROUP BY` alternative | implicit-grouping |
| `type()` | pygrafito extension | supported | implemented | `LABELS()` alternative | type-extension |
| Query budget | pygrafito extension | supported | implemented | No GQL equivalent; expansion, row, and optional time counters | budget-row-limit |
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
carry none.

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
