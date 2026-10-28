# Design: GQL path-semantics matrix

## Context

The engine already implements path modes (`WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC`), the closed
quantifiers `{n}`, `{m,n}`, and `{,n}`, all canonical edge directions, and a query budget with
expansion, row, and optional time counters. The remaining path rows are gated:

- Match modes `DIFFERENT EDGES` and `REPEATABLE ELEMENTS`.
- Open-ended quantifiers `*`, `+`, `*n..`, and `{m,}`.
- Path search prefixes `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST k`.
- Grouped quantified path patterns.

The implementation facts that constrain this design:

- Fixed patterns compile to SQL, including path-mode uniqueness predicates. Quantified patterns
  use `PatternEngine` over a bounded `AdjacencySnapshot` captured per start node.
- Path modes are resolved in static analysis: per-path mode, clause mode, `TRAIL` for a legacy
  quantifier, then `WALK`.
- Rows are materialized stage by stage, and `LIMIT` is applied after projection.
- One budget tracker, one transaction, and one snapshot govern a statement.
- The profile consistency test requires every `supported` row to have a corpus case and every
  gated row to name its follow-up change.

This change records the decisions that the four implementing changes must follow. It changes no
runtime behavior and flips no profile row.

## Goals / Non-Goals

**Goals:**

- Give every path-engine construct one unambiguous rule and one owner.
- Keep the current defaults working: `WALK` paths and repeatable elements stay the default, so
  existing queries keep their results.
- Make termination explicit: a query either completes, stops at demand, or fails on the budget.
  It never returns a silently truncated path set.
- Define deterministic output where path search would otherwise be arbitrary.
- Keep the later changes independently implementable in dependency order.

**Non-Goals:**

- No parser, AST, semantic-analysis, compiler, executor, storage, CLI, or public API change.
- No new path mode, match mode, search prefix, or quantifier beyond the profile's rows.
- No `ALL` search prefix, path-pattern union, questioned paths, path predicates, or graph
  algorithms API.
- No weighted path search. Search counts relationships, not properties.
- No change to the Python `Graph.paths` contract, which stays a bounded relationship-unique trail
  enumerator.

## Terminology

- **Path**: one match of a path pattern: an ordered node sequence and an ordered relationship
  sequence.
- **Path mode**: the repetition rule *inside one path*.
- **Match mode**: the sharing rule *across the paths of one `MATCH` clause*.
- **Quantifier**: the repetition count on a relationship or a grouped path pattern.
- **Search prefix**: the selection rule applied to all paths of one path pattern.
- **Partition**: the pair of boundary nodes (first and last node) of a path pattern within one
  input row. Path search selects paths per partition.

## Decision: path modes and match modes are orthogonal

Path modes constrain one path. Match modes constrain the whole clause. Both apply at the same time;
neither overrides the other.

| Path mode | Constraint inside one path |
| --- | --- |
| `WALK` | None. Nodes and relationships may repeat. |
| `TRAIL` | No relationship may occur twice. Nodes may repeat. |
| `SIMPLE` | No node may repeat, except that the first and last node may be the same. |
| `ACYCLIC` | No node may repeat, including the first and last. |

| Match mode | Constraint across all paths of one `MATCH` clause |
| --- | --- |
| `REPEATABLE ELEMENTS` | None. This is the default. |
| `DIFFERENT EDGES` | Each relationship binds at most once in the clause, including repetitions inside one path. |

Combined rule: a relationship use is accepted only when both the path mode and the match mode
accept it. `TRAIL` and `DIFFERENT EDGES` therefore agree inside a path, while `WALK` and
`DIFFERENT EDGES` together mean "a walk path, but every edge used once in the clause". The default
match mode is `REPEATABLE ELEMENTS` because it preserves existing results; the profile publishes
that choice instead of silently claiming another default.

Resolution order for the effective path mode is unchanged: explicit per-path mode, explicit clause
mode, `TRAIL` when the path contains a legacy quantifier, then `WALK`. The match mode is resolved
independently at clause level. `MATCH DIFFERENT EDGES TRAIL (a)-[:R]->{1,3}(b)` applies both.

Match modes apply to `MATCH` and `OPTIONAL MATCH`. `INSERT`, `CREATE`, and `MERGE` patterns have no
match mode and keep their current behavior. `DIFFERENT EDGES` is scoped to the clause: an edge
bound by an earlier `MATCH` stage may be bound again in a later stage.

## Decision: quantifier vocabulary

| Form | Lower | Upper | Canonical? | Default mode |
| --- | --- | --- | --- | --- |
| `{n}` | `n` | `n` | yes | `WALK` |
| `{m,n}` | `m` | `n` | yes | `WALK` |
| `{,n}` | 0 | `n` | yes | `WALK` |
| `{m,}` | `m` | unbounded | yes | `WALK` |
| `*` | 0 | unbounded | yes | `WALK` |
| `+` | 1 | unbounded | yes | `WALK` |
| `*n` | `n` | `n` | no | `TRAIL` |
| `*n..m` | `n` | `m` | no | `TRAIL` |
| `*0..m` | 0 | `m` | no | `TRAIL` |
| `*n..` | `n` | unbounded | no | `TRAIL` |
| group `{...}` | as written | as written | yes | `WALK` |

- The bare `*` and `+` are canonical GQL forms; they are not the legacy Cypher spellings. `*` is
  zero or more and `+` is one or more. Cypher queries that want "one or more" use `+`.
- Mixing a legacy and a canonical quantifier in one path without an explicit mode remains a
  semantic error, exactly as today.
- A lower bound of zero is legal on a relationship segment. A path pattern that consists only of a
  zero-lower-bound group is rejected because it could match no element.
- Bounds are non-negative integer literals. Parameters and expressions are rejected.

## Decision: zero-length and zero-hop bindings

| Situation | Node bindings | Relationship binding | Path binding |
| --- | --- | --- | --- |
| A quantified segment matches zero hops | Both end nodes bind to the same node | The relationship variable binds `[]` | The path contains one node and no relationship for that segment |
| A path pattern has no relationships | Its single node variable binds that node | None | The path contains one node and no relationships; `length(p)` is 0 |
| A group matches zero iterations | Boundary nodes coincide; group-local node variables bind `[]` | Group-local relationship variables bind `[]` | A group path variable is not allowed when zero iterations are possible |

A zero-hop segment still evaluates its label, property, and inline `WHERE` constraints only when it
matches at least one hop; at zero hops there is no relationship to test. Node constraints on the
end node always apply. Path modes apply across the whole path, including zero-hop segments.

## Decision: path search partitions and selection

A search prefix applies to one path pattern. It first partitions the matches of that pattern by
their first and last node within each input row, then selects from each partition:

| Prefix | Selection |
| --- | --- |
| none | Every path. This is the default. |
| `ANY` | One path per partition. |
| `ANY SHORTEST` | One path of minimum length per partition. |
| `ALL SHORTEST` | Every path of minimum length per partition. |
| `SHORTEST k` | Up to `k` paths per partition, in increasing length; ties count toward `k`. `k` is a non-negative integer literal and `k = 0` selects no path. |

Duplicate rule: two paths are the same when their node sequence and their orientation-aware
relationship sequence are identical. Parallel relationships produce different paths because their
relationship identifiers differ. `ALL SHORTEST` returns distinct paths, not distinct endpoint
pairs.

Tie-breaking rule, used whenever a prefix must choose among paths of the same length:

1. Shorter path first.
2. Then the lexicographically smaller relationship sequence, comparing each traversed
   relationship's identifier and traversal orientation.
3. Then the lexicographically smaller node sequence.

The evaluator must enumerate relationships in ascending identifier order and target nodes in
ascending identifier order, so the rule is deterministic and testable. Output rows for a path
pattern follow this order unless the statement has its own `ORDER BY`.

A path search prefix is written after the optional path variable and before the path mode:
`MATCH p = ANY SHORTEST WALK (a)-[:TRUSTS]->{1,}(b) RETURN p`. A prefix inside a group is a
semantic error; search applies to the whole path.

## Decision: termination, demand, and the budget

| Query shape | Termination |
| --- | --- |
| Open-ended quantifier under `TRAIL`, `SIMPLE`, or `ACYCLIC` | Finite: the repetition rule bounds the path length. |
| Open-ended quantifier under `WALK` without a search prefix | Infinite in general. Completes only when execution is demand-bounded. |
| Open-ended quantifier with any search prefix | Finite: search selects a finite number of paths per partition and the set of partitions is finite. |
| Closed quantifier, any mode | Finite. |

Demand-bounded means a final `LIMIT` (with or without `OFFSET`) on a read-only statement whose
result does not need all rows first: no `ORDER BY`, `DISTINCT`, aggregation, `GROUP BY`, set
operation, write clause, `NEXT` boundary, or `FINISH`. `EXISTS { ... }` also stops after its first
inner row. A `LIMIT` under `ORDER BY`, `DISTINCT`, aggregation, or a write requires full evaluation
and is documented as such.

When an open `WALK` has no demand bound and no search prefix, evaluation continues until the
budget stops it. The call then raises `QueryBudgetExceededError` naming the counter and limit and
returns no partial result; it never returns a truncated path set. This is the only supported
outcome for an unbounded, non-selective walk, and the documentation must recommend `LIMIT`, a
search prefix, or a repetition-restricting path mode.

Budget accounting:

- Each candidate relationship expansion counts once against the expansion counter, whether it is
  later accepted or rejected.
- Each produced binding counts once against the row counter.
- Path search counts exploration expansions; selecting or deduplicating a path does not add
  expansions.
- A group iteration adds no counter of its own because every group must consume at least one
  relationship per iteration (see the progress rule).
- A wall-clock limit remains opt-in and is checked at the existing intervals.

## Decision: grouped quantified path patterns

Syntax: a path pattern is a juxtaposition of path terms. A path term is a node pattern followed by
zero or more relationship-node pairs, or a parenthesized path pattern followed by a quantifier.
Adjacent terms share their boundary node: the last node of one term is the first node of the next.
This is the GQL and Cypher spelling, for example:

```text
MATCH p = (kevin:User)-[:TRUSTS]->((a:Program)-[r:TRUSTS]->(b:Program)){1,3} RETURN p
```

Rules:

- A group SHALL contain at least one relationship position, directly or through a nested group.
- A group quantifier is `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, or `+`. The legacy `*n..m` spelling is
  not allowed on a group.
- The overall path pattern SHALL contain at least one element that consumes a relationship, so a
  path is never empty and a lone zero-lower-bound group is rejected.
- A group MAY name an inner path mode after its opening parenthesis. Inner and outer path modes
  both apply; the stricter constraint wins. A group MAY NOT name a search prefix.
- Variables first introduced inside a group are **group variables**. Outside the group they bind
  ordered lists: a node variable binds the node per iteration, a relationship variable binds the
  relationship per iteration, and nesting flattens lists in traversal order.
- A group variable SHALL occur at most once in its group. The implicit boundary equality between
  iterations is not expressed through a variable.
- A variable bound before the group MAY be referenced inside it and acts as an equality
  constraint, not as a group variable.
- A path variable on a group binds one `Path` for the concatenated iterations. It is rejected when
  the quantifier admits zero iterations, because a `Path` must contain at least one node.
- Zero iterations are allowed only when the rest of the path pattern contributes at least one
  relationship; group variables then bind empty lists.
- Progress rule: every group SHALL contain at least one relationship position whose effective
  minimum hop count is at least one. This guarantees that each iteration charges the expansion
  counter, so an open group cannot loop without consuming budget.
- Path modes, match modes, path search, path variables, and path functions see the group as part of
  the whole path. A grouped path is not a separate result.

Nested groups follow the same rules. A group inside a group may not rebind an outer group variable;
the semantic analyzer rejects the name conflict.

## Matrix: allowed combinations

| Quantifier | Path mode | Match mode | Search | Outcome |
| --- | --- | --- | --- | --- |
| fixed / closed | any | either | none or any prefix | Supported |
| open | `TRAIL`, `SIMPLE`, `ACYCLIC` | either | none or any prefix | Supported |
| open | `WALK` | either | search prefix | Supported |
| open | `WALK` | either | none, demand-bounded | Supported and stops early |
| open | `WALK` | either | none, not demand-bounded | Runs until the budget error |
| grouped | any | either | none or any prefix | Supported once grouped paths land |
| grouped | `WALK` + open group | either | none, not demand-bounded | Runs until the budget error |

Rejected combinations:

- Mixing legacy and canonical quantifiers in one path without an explicit mode.
- A search prefix inside a group.
- A group with no relationship position, a group that cannot progress, or a lone zero-lower-bound
  group.
- A group path variable on a quantifier that admits zero iterations.
- A variable introduced twice inside one group, or a group variable that shadows an outer variable.
- `SHORTEST k` with a non-literal, negative, or non-integer `k`.
- More than one search prefix on one path pattern.

## Worked examples

Fixtures are the existing conformance fixtures: `tron-cycle` (directed three-node cycle),
`tron-diamond`, `tron-parallel`, and `tron-self-loop`.

| Example | Result |
| --- | --- |
| `MATCH p = (a:User {designation: 'Kevin Flynn'})-[:TRUSTS{3}]->(a) RETURN p` | `WALK` default; the three-relationship cycle matches. |
| The same query with `TRAIL` | Matches: three distinct relationships. |
| The same query with `SIMPLE` | Matches: only the first and last node repeat. |
| The same query with `ACYCLIC` | No match. |
| `MATCH p = (a:Program)-[:TRUSTS*2]->(b) RETURN p` | Legacy quantifier, `TRAIL`. |
| `MATCH (a)-[:TRUSTS{0,2}]->(b) RETURN a, b` on a self-loop | Includes the zero-hop row where `a` and `b` are the same node. |
| `MATCH DIFFERENT EDGES (a)-[r]->(b), (c)-[s]->(d)` | `r` and `s` bind different relationships. |
| `MATCH REPEATABLE ELEMENTS ...` or no match mode | `r` and `s` may bind the same relationship. |
| `MATCH p = ALL SHORTEST (a:User {designation: 'Kevin Flynn'})-[:PARENT_OF*]->(b) RETURN p` on the diamond | Two two-hop paths, one per route. |
| The same query with `ANY SHORTEST` | One two-hop path, chosen by the tie-break order. |
| The same query with `SHORTEST 2` | Both two-hop paths. |
| `MATCH p = ANY (a)-[:TRUSTS]->{1,}(b) RETURN p` | One path per endpoint pair; finite. |
| `MATCH p = (a)-[:TRUSTS]->{1,}(b) RETURN p LIMIT 5` | Stops after five rows, not after enumerating every walk. |
| `MATCH p = (a)-[:TRUSTS]->{1,}(b) RETURN p` on a cyclic graph | Raises `QueryBudgetExceededError`; no partial rows. |
| `MATCH p = (a)-[:TRUSTS]->((b)-[r:TRUSTS]->(c)){2} RETURN r` | `r` binds a list of two relationships. |

## Profile and corpus plan

Each implementing change flips its own matrix rows and adds cases. Planned feature identifiers and
cases:

| Change | Profile rows | Corpus cases |
| --- | --- | --- |
| `add-gql-unbounded-traversal` | `Open-ended quantifiers`, `*`, `+`, `{m,}`, legacy `*n..` | `open-star`, `open-plus`, `open-canonical-tail`, `open-legacy-tail`, `unbounded-walk-limit`, `unbounded-trail-cycle`, `unbounded-zero-hop` |
| `add-gql-match-modes` | `DIFFERENT EDGES`, `REPEATABLE ELEMENTS` | `different-edges-shared-edge`, `repeatable-elements-shared-edge`, `different-edges-quantified`, `different-edges-two-patterns` |
| `add-gql-path-search` | `Path search prefixes`, `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k` | `any-per-partition`, `any-shortest-diamond`, `all-shortest-diamond`, `shortest-k-parallel`, `shortest-k-zero`, `shortest-self-loop` |
| `add-gql-grouped-quantified-paths` | `Grouped quantified paths` | `grouped-fixed-repetition`, `grouped-bounded-diamond`, `grouped-list-bindings`, `grouped-zero-iterations`, `grouped-nested`, `grouped-inner-mode` |

Every case uses a TRON-themed fixture and tags `canonical` or `compatibility` as appropriate. A
gated row keeps its follow-up change name until its implementing change lands.

## Migration notes

- `WALK` stays the default path mode and `REPEATABLE ELEMENTS` becomes the explicit default match
  mode, so existing queries keep their results.
- `DIFFERENT EDGES` is opt-in. Queries with several patterns that relied on sharing a relationship
  only change when they add that keyword.
- Open quantifiers were rejected before this work. Accepting them adds behavior; it removes none.
  The one surprise is that bare `*` includes zero-hop matches. Users who want at least one hop
  write `+` or `{1,}`.
- `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`, `DIFFERENT EDGES`, `REPEATABLE ELEMENTS`,
  `EDGES`, `ELEMENTS`, `SHORTEST`, and `ANY` become reserved keywords when their change lands.
  Variables and aliases using those spellings must be backtick-quoted.
- An open `WALK` without `LIMIT` or a search prefix now runs to the budget error instead of failing
  as a deferred construct. The documentation must present `LIMIT`, a search prefix, or `TRAIL` as
  the intended shapes.

## Alternatives considered

- Make `DIFFERENT EDGES` the default. Rejected: it would change results for multi-pattern queries
  and turn the default `WALK` into an edge-unique walk, which is a breaking change unrelated to the
  remaining 1.0 work. `REPEATABLE ELEMENTS` preserves current results.
- Treat `DIFFERENT EDGES` as a path mode. Rejected: a path mode resets per path and cannot express a
  clause-wide rule.
- Select one global shortest path instead of one per endpoint pair. Rejected: a pattern with free
  endpoints would return a single row, which is not useful, and the documented GQL model partitions
  by endpoints.
- Cap an unbounded `WALK` at a hard-coded depth. Rejected: silent truncation is worse than a
  budget error.
- Allow zero-relationship group iterations and add a separate iteration counter. Rejected: the
  progress rule is simpler and keeps the budget vocabulary stable.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Path-mode and match-mode constraints drift between the SQL compiler and `PatternEngine` | One shared predicate helper and matrix tests that run both paths on the same fixtures. |
| Lazy execution changes snapshot or rollback behavior | Statement-level read transaction for open patterns; drain read stages before writes; crash and rollback tests. |
| Unbounded `WALK` still hangs | Demand-driven pipeline first, budget second, and a test that asserts the budget error. |
| Path-search tie-breaking is unstable across machines | Compare only integer node and relationship identifiers; no hashing or dictionary order. |
| Group variables bind ambiguous values | One occurrence per group, flat lists, and explicit semantic errors. |
| Profile and corpus drift | Each implementing change updates the matrix row, prose, grammar, and corpus in the same task group. |
| Too much surface in one change | Four separately shippable changes in the roadmap's dependency order. |
