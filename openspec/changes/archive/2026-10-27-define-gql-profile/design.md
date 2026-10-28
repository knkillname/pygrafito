# Design

## Context

See `proposal.md` for motivation and `specs/gql-profile/spec.md` for the contract. This design
explains how the profile is layered, why the classifications are split as they are, and what the
follow-up changes must preserve.

The current state that shapes the approach:

- The element model is already GQL: schema version 2, edge label sets, directed and undirected
  edges, stable ids, snapshot and views version 2.
- The query surface is the transitional Cypher-flavored dialect described by
  `graph-query-language`. It still uses `CREATE`, `UNWIND`, `WITH`, `MERGE`, implicit grouping,
  `*n..m` quantifiers, and double-dash arrows.
- The Python traversal API (`paths()`) is a relationship-unique, bounded trail enumerator. The
  query language is about to diverge from it by adopting ISO `WALK` as the default.
- The parser is a hand-written recursive descent parser over a compact AST. The fixed-length
  compiler emits SQL; quantified patterns run through `PatternEngine`.
- `PatternEngine._capture()` materializes a bounded adjacency region, and `_depth()` treats an
  absent `max_hops` as one hop. The semantic analyzer rejects unbounded quantifiers before
  execution, so the bounded assumption is currently safe.
- The executor materializes each read stage. `LIMIT` is applied after the match stage, so it
  bounds the result, not the traversal work.
- `PatternCreator` creates directed relationships with the pattern's label set. The storage
  repository already supports undirected and multi-label edges, so the limitation is in the query
  mutation layer.
- `Direction` currently has `OUTGOING`, `INCOMING`, and `BOTH`. That enum conflates traversal
  direction with the stored directed flag; the GQL edge-direction matrix needs a richer type in
  the frontend change.

Constraints from the project:

- Python 3.14, runtime standard library only.
- Durable specs live in `openspec/specs/`; this change adds a new capability rather than editing
  `graph-query-language`.
- Every apply run updates the Sphinx documentation and passes `hatch run docs:build`.
- The project is pre-1.0, so a documented breaking change is acceptable if it is deliberate.

## Goals / Non-Goals

**Goals:**

- Publish a profile that is precise enough to settle the language identity before the frontend
  rewrite starts.
- Keep current engine behavior unchanged in this change; the profile distinguishes target from
  current.
- Make the compatibility policy durable: canonical, synthetic alias, compatibility construct,
  extension, out of profile.
- Record the decisions that would otherwise be renegotiated in every follow-up: `WALK` default,
  legacy `TRAIL`, extensions, deferred features, budget policy.
- Define how conformance is claimed and verified so the project never overstates GQL support.

**Non-Goals:**

- Implementing `INSERT`, `FILTER`, `WALK`, the query budget, label expressions, or the direction
  matrix.
- Rewriting `graph-query-language` requirements; the follow-up behavior changes do that.
- Claiming ISO conformance, even for the canonical subset.
- Implementing catalog, graph types, sessions, procedures, in-language transactions, `SELECT`, or
  temporal storage.
- Changing the Python `paths()` API.
- Releasing a version on its own; this is a documentation/spec change that can ship with the next
  release.

## Decisions

### A new `gql-profile` capability owns the policy

`gql-profile` owns the classification, conformance claims, and migration policy.
`graph-query-language` continues to describe what the engine currently does. The frontend, budget,
and path-semantics changes will modify `graph-query-language` and update the profile matrix in the
same change.

Alternatives considered:

- **Fold the profile into `graph-query-language`.** Rejected: the durable spec would claim
  behavior that is not implemented, and every follow-up would have to edit a large existing spec
  just to record policy.
- **Use `skip_specs: true` and keep the profile only in `docs/`.** Rejected: the profile is a
  compatibility contract, not a tutorial. It needs a durable, reviewable spec home.
- **Create a separate capability per tier or per follow-up.** Rejected: too fragmented; the tiers
  only make sense together.

The layering is:

```text
+----------------------+
| gql-profile          |  policy: what is canonical, alias, compat, extension, out
+----------------------+
| graph-query-language |  behavior: what the engine actually does, change by change
+----------------------+
| graph-traversal      |  behavior: the Python paths()/traverse()/shortest_path() API
+----------------------+
```

### Five tiers, not two

A two-bucket model (GQL / non-GQL) cannot express the difference between a spelling alias and a
legacy construct that carries its own default. The tiers are:

| Tier | Contract |
| --- | --- |
| Canonical GQL | Documented first; new examples use it where supported. |
| Synthetic alias | Same semantics as its canonical form; compatibility only. |
| Compatibility construct | Legacy spelling with a legacy default; documented as such. |
| pygrafito extension | No GQL equivalent; supported but never claimed as GQL. |
| Out of profile | Explicitly rejected; no silent fallback. |

The tier rules are normative in `specs/gql-profile/spec.md`. The profile page is the reader-facing
view.

### Canonical surface and alias mapping

Canonical spellings follow ISO GQL: `INSERT`, `FOR`, `FILTER`, `LET`, `NEXT`, `GROUP BY`,
`OFFSET` and `SKIP`, `{n,m}`, label expressions (`&`, `|`, `!`, `%`), the GQL edge-direction forms,
and `//` / `--` line comments.

Synthetic aliases are chosen only where the semantics are identical:

| Canonical | Alias | Scope |
| --- | --- | --- |
| `INSERT` | `CREATE` | Data statements only; `CREATE GRAPH` remains out of profile. |
| `FOR x IN list` | `UNWIND list AS x` | Row expansion. |
| `FILTER` | `WHERE` | A stage-level filter; `WHERE` inside `MATCH` and element patterns stays canonical. |
| `{n,m}` | `*n..m` | Syntax only; the legacy form is a compatibility construct, so its default differs. |
| `->`, `<-`, `-` | `-->`, `<--`, `--` | Pattern arrows. |
| `:A&B` | `:A:B` | Node label conjunction. |
| `OFFSET` | `SKIP` | Both are canonical ISO synonyms, so neither is an alias. |

The legacy double-dash arrows collide with the GQL `--` line comment. The lexer disambiguation is
a frontend-change decision, not a profile decision. The profile only states that both forms are
supported and that a `--` comment cannot be silently reinterpreted as an edge.

`CREATE` is an alias only when it introduces a data pattern. A `CREATE GRAPH` or other catalog
statement is out of profile and must produce an explicit error.

Alternatives considered:

- **Canonical only.** Rejected: it discards the compatibility surface and makes migration harder
  than necessary.
- **A `dialect="cypher"` mode.** Rejected for now: two grammars, two semantics, two test suites,
  and the standard is already close enough to Cypher. Revisit only if adoption data shows a real
  need.

### Legacy quantifier is a compatibility construct

`*n`, `*n..m`, and `*0..m` keep the Cypher relationship-unique default: `TRAIL`. Canonical
`{n,m}` uses the path-mode default, which is `WALK`. An explicit path mode overrides both. Mixing
the two forms in one path without an explicit mode is a semantic error.

The resolution rule is:

```text
mode(path) =
    explicit per-path mode
  | explicit clause-level mode
  | TRAIL    if the path contains a legacy *n..m quantifier
  | WALK     otherwise
```

Why this shape:

- It preserves the behavior of existing Cypher-flavored queries and aligns the legacy form with
  the Python `paths()` API.
- It keeps canonical GQL honest: `{n,m}` follows ISO `WALK`.
- It makes the asymmetry explicit instead of hiding it in a pure alias.

Alternatives considered:

- **Pure alias, both forms use `WALK`.** Rejected by the project decision: it would silently
  change existing trail queries.
- **Deprecate the legacy form.** Rejected: it is the least lenient option and removes a familiar
  migration path.

The cost is one permanent asymmetry. Mitigations: a side-by-side table in the profile, a
migration example, and a conformance case for the resolution rule. The frontend change must parse
both forms; the path-semantics change implements the mode resolution and the mode engine.

### WALK default, budget gate, and unbounded deferral

The profile adopts ISO `WALK` as the canonical default but gates it on the query budget. The
budget change lands before the path-semantics change, so the governor is tested against the
current trail engine before the default changes.

Budget shape:

```text
QueryBudget
  max_expansions  int      each relationship expansion in a walk
  max_rows        int      each intermediate binding produced by a stage
  max_seconds     float?   optional wall-clock check between steps
```

- A per-query override wins over the graph or default budget.
- Exceeding either counter raises a query execution error that names the counter and the limit.
- A write statement that exceeds the budget rolls back entirely.
- The executor materializes stages, so `LIMIT` does not currently stop traversal work. The budget
  is the safety valve; pushing `LIMIT` into the pattern engine is a follow-up optimization.
- Defaults are tuned with the existing benchmark; a starting point is 1,000,000 expansions and
  100,000 intermediate rows.

Unbounded `WALK` needs a new traversal strategy. The current `_capture()` assumes a finite depth,
and `_depth()` treats an absent maximum as one hop. The path-semantics change can choose lazy
adjacency lookups or frontier-by-frontier snapshot expansion; capturing the whole connected
component is rejected because it violates the proportional-traversal contract. Until that work
lands, unbounded `WALK` is deferred and gated in the matrix.

GQL match modes (`DIFFERENT EDGES`, `REPEATABLE ELEMENTS`) are also deferred. Their interaction
with path modes needs a precise rule and a conformance corpus; guessing now would create a second
semantic trap.

Alternatives considered:

- **Keep `TRAIL` as the default.** Rejected by the project decision: it does not follow ISO.
- **`WALK` without a budget.** Rejected: unbounded walks on a cycle are infinite.
- **Capture the whole reachable component for unbounded walks.** Rejected: it can read the whole
  graph for a small query and breaks the current performance contract.

### Extensions stay, clearly labeled

`MERGE`, `WITH` aggregation and scope, implicit grouping, and `type()` are pygrafito extensions.
They are useful and have no GQL 2024 equivalent. `GROUP BY` is the canonical alternative to
implicit grouping; `LET`/`NEXT` are the canonical alternatives to `WITH`; `LABELS()` is the
canonical metadata function where it overlaps.

Dropping them would make the product less capable for the sake of a conformance claim the project
is not making. Keeping them unlabeled would blur the language identity. The profile labels them
and never presents them as GQL.

### Out of profile and deferred are different

Out of profile means the construct is rejected: catalog statements, graph types, sessions,
procedures, in-language transactions, `SELECT`, and full temporal values. These are server-shaped
or require a storage/value-format change.

Deferred means the construct is in the long-term GQL direction but not in the initial profile:
match modes, grouped quantified path patterns, path search prefixes, and unbounded `WALK`. These
are marked gated in the matrix rather than rejected forever.

The distinction matters for the frontend: an out-of-profile construct gets an explicit error; a
deferred construct gets an error that says it is not in the current profile and is tracked in the
matrix.

### Conformance matrix and corpus

The profile page carries a feature matrix with columns for feature, GQL reference, tier, status
(supported, gated, deferred, out of profile), deviation, and corpus case. Supported requires a
corpus case; a feature without coverage cannot be marked supported.

The corpus contract is data-driven, not a bespoke test harness:

```text
case
  name       unique kebab-case id
  feature    profile feature id
  fixture    seed statements or a named TRON-themed fixture
  query      statement text
  params     optional parameter mapping
  expect     rows, or an error type and message fragment
  tags       optional: canonical, alias, compatibility, extension, deviation
```

The runner belongs in the follow-up frontend change. This change defines the contract and adds
the profile page; it does not ship a corpus of unsupported queries.

Alternatives considered:

- **Hand-written documentation only.** Rejected: the profile would drift from behavior.
- **A full ISO test suite.** Rejected: too large and not aligned with a documented profile.

### Documentation strategy: current status first

The current release still uses the transitional dialect. The profile page therefore opens with a
current-status section:

- The current dialect remains the runnable surface until the frontend change.
- Canonical examples in the profile are marked target until the frontend change.
- README and quickstart examples stay runnable; they are not rewritten to `INSERT` or `FILTER`
  before the engine supports them.
- `docs/reference/query-language.md` gets a banner pointing to the profile as the target.

This avoids the worst failure mode of a spec-first change: documentation that looks like it
describes working behavior when it does not.

### Sequencing

```text
0.9.0 element-model release (separate)
  -> define-gql-profile                 this change, docs/spec only
  -> adopt-gql-query-frontend           canonical spellings, aliases, both quantifier forms
  -> add-query-budget                   governor; trail stays
  -> add-gql-path-semantics             WALK default, legacy TRAIL, modes, labels, directions
  -> add-gql-composition                FILTER, LET, FOR, NEXT, GROUP BY, OFFSET, set operations
  -> add-gql-values                     temporal, records, casts; storage format v3 if needed
  -> harden-for-1.0                     corpus, fuzzing, crash tests, format freeze
```

Why this order:

- The profile must exist before the frontend, or aliases and path defaults will be invented in
  code review.
- The frontend can land without changing semantics, which gives users GQL spellings early.
- The budget must land before `WALK`, so the safety valve is proven independently.
- The path semantics change owns the hard part: mode engine, direction matrix, label expressions,
  unbounded traversal.
- Composition and values are separable and can follow.

Each follow-up updates the profile page and matrix in the same change, as required by the
change-control requirement.

## Risks / Trade-offs

- **[`WALK` default changes existing results]** -> Ship the budget first, add explicit `TRAIL` and
  the legacy `*n..m` default, provide a migration table, and add conformance cases for both modes.
- **[The legacy quantifier asymmetry is confusing]** -> Show `*1..3` and `{1,3}` side by side with
  their defaults, reject mixed quantifiers without an explicit mode, and make the compatibility
  page, not the canonical reference, the place where the legacy form is introduced.
- **[The budget rejects legitimate large queries]** -> Tune defaults with the benchmark, expose a
  per-query override, name the counter and limit in the error, and document how to raise it.
- **[Unbounded `WALK` is deferred longer than expected]** -> Keep it gated in the matrix, do not
  claim it, and implement lazy traversal before enabling it.
- **[The profile drifts from the engine]** -> Keep the current-status section, mark supported only
  with corpus coverage, and require the profile/matrix/corpus update in every query change.
- **[Alias sprawl]** -> Five tiers with a strict rule: a synthetic alias must be a pure spelling;
  anything with a different default becomes a compatibility construct or an extension.
- **[The query language and `paths()` diverge]** -> Document that `paths()` remains a trail
  enumerator and that the query language follows GQL path modes. Do not silently change the
  Python API.
- **[A docs-only change is ignored]** -> Add the profile to the reference navigation, link it from
  the query reference and README, and point `AGENTS.md` at it.
- **[ISO GQL evolves]** -> Version the profile and revisit the matrix after a new ISO edition; do
  not promise conformance to a future edition.

## Migration Plan

1. **This change:** publish the profile and matrix, add the current-status banner, and keep every
   runnable example on the transitional dialect. No behavior change, no database or snapshot
   change, no version bump required.
2. **Frontend change:** add canonical spellings and aliases. The old dialect remains accepted;
   the profile matrix flips syntax features from gated to supported as they land.
3. **Budget change:** add the expansion and row counters with the current trail semantics. The
   matrix records the budget defaults; no query results change.
4. **Path-semantics change:** enable `WALK` as the default, keep the legacy `*n..m` form on
   `TRAIL`, add the mode engine and direction matrix. This is the breaking semantic release;
   update `CHANGELOG.md`, the query reference, the migration table, and the README examples.
   Users who want the old behavior write `MATCH TRAIL` or keep `*n..m`.
5. **Composition and values:** add `FILTER`, `LET`, `FOR`, `NEXT`, `GROUP BY`, `OFFSET`, set
   operations, temporal types, records, and casts. The profile matrix expands with each change.
6. **1.0 hardening:** make the conformance corpus a release gate, freeze the profile and file
   format, and require a migration path for any post-1.0 format change.

Rollback: this change is documentation and spec only, so reverting it has no data impact. The
follow-up behavior changes are pre-1.0 and can be rolled back by installing the previous release;
no storage format change is introduced by this profile.

## Open Questions

- **Budget defaults.** The starting point is 1,000,000 expansions and 100,000 intermediate rows.
  Measure with `benchmarks/run.py` in the budget change and document the final numbers.
- **Match modes.** Decide in the path-semantics change whether `DIFFERENT EDGES` and
  `REPEATABLE ELEMENTS` are in the first mode implementation or a follow-up. The profile currently
  lists them as deferred.
- **Unbounded `WALK`.** Decide whether the path-semantics change includes lazy traversal or
  whether unbounded walks stay deferred for one more release. The profile gates them either way.
- **`SIMPLE` path mode.** It is in scope but may follow `WALK`, `TRAIL`, and `ACYCLIC` if the
  implementation needs to be staged.
- **Temporal values.** The profile lists full temporal values as out of profile for 1.0. Revisit
  after the composition change; adding them requires a value-format and snapshot decision.
- **Path search.** `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST k` are deferred. Decide their
  scope after the shortest-path API is reviewed against the new path modes.
- **A `dialect="cypher"` mode.** Not planned. Revisit only if adoption data shows that the
  compatibility surface is insufficient.
