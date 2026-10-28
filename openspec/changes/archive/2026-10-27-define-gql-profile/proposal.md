# Proposal

## Why

The element model is already GQL, but the query surface is a transitional Cypher-flavored dialect
with no published definition of what is canonical GQL, what is a compatibility alias, and what is
a pygrafito extension. The next change replaces that surface with GQL. Without a profile fixed
first, aliases, path defaults, and conformance claims will drift, and every later change will
renegotiate them. The element model is settled and the frontend rewrite has not started, so this
is the moment to fix the contract.

## What Changes

- Add a published GQL profile that is the authoritative contract for the query language's
  canonical surface, compatibility aliases, compatibility constructs, extensions, path-mode
  policy, query budget, conformance claims, and migration guidance.
- Classify every supported construct into exactly one of five tiers: canonical GQL, synthetic
  alias, compatibility construct, pygrafito extension, or out of profile.
- Make GQL the canonical spelling: `INSERT`, `FOR`, `FILTER`, `LET`, `NEXT`, `GROUP BY`,
  `OFFSET`/`SKIP`, `{n,m}`, label expressions, the GQL edge-direction forms, and both GQL comment
  forms.
- Keep the transitional spellings as synthetic aliases where semantics are identical: `CREATE`
  for `INSERT` in data statements, `UNWIND` for `FOR`, a stage-level `WHERE` for `FILTER`, the
  double-dash arrow forms, and `:A:B` node labels for `:A&B`.
- Treat the legacy quantifier `*n`/`*n..m`/`*0..m` as a compatibility construct whose default path
  mode is `TRAIL`. Canonical `{n,m}` uses the profile's path-mode default. An explicit path mode
  wins, and mixing both quantifier forms in one path without an explicit mode is a semantic
  error.
- **Planned BREAKING (delivered by the path-semantics change):** canonical GQL path patterns
  default to ISO `WALK` instead of the current relationship-unique trail. Existing trail queries
  must use `MATCH TRAIL` or the legacy `*n..m` form after migration.
- Gate `WALK` on a query budget. The profile defines expansion and intermediate-row counters, a
  query execution error when a budget is exceeded, full rollback for writes, a documented default,
  and a per-query override.
- Keep `MERGE`, `WITH` aggregation and scope, implicit grouping, and `type()` as pygrafito
  extensions with no GQL equivalent, clearly labeled and not claimed as GQL.
- List catalog statements, graph types, sessions, procedures, in-language transactions, `SELECT`,
  full temporal values, GQL match modes, grouped quantified path patterns, path search prefixes,
  and unbounded `WALK` as out of profile or deferred for the initial profile.
- Publish a conformance matrix and define a conformance corpus contract so a feature is supported
  only when a corpus case covers it and the project never claims ISO conformance beyond the
  matrix.
- Document the pre-1.0 migration from the transitional dialect, including the legacy `TRAIL`
  behavior and the fact that the Python `paths()` API remains a relationship-unique trail
  enumerator.
- This change adds the profile, the `gql-profile` capability, documentation, a documentation
  contract test, and a changelog entry. It does not change the parser, engine, storage, public
  Python API, or CLI. Those changes follow in separate changes.

## Capabilities

### New Capabilities

- `gql-profile`: the published GQL language profile, its five-tier construct classification,
  canonical/alias/compatibility/extension policy, path-mode and budget policy, conformance
  matrix and corpus contract, and migration guidance.

### Modified Capabilities

None. The profile is a new contract; the engine behavior is changed by follow-up changes that
modify `graph-query-language`.

## Impact

- Documentation: add `docs/reference/gql-profile.md`, add it to the reference navigation, add a
  transitional-dialect banner to `docs/reference/query-language.md`, and link the profile from
  `README.md`.
- Tests: add a small documentation contract test for the profile page; the runtime suite is
  otherwise unchanged.
- Project rules: point `AGENTS.md` at the profile for canonical query-language decisions and
  require future query changes to update the profile, matrix, and corpus.
- Changelog: add an `Unreleased` entry for the published profile and the compatibility policy.
- Compatibility: the profile commits the project to ISO `WALK` as the target default and to
  `TRAIL` for the legacy quantifier. The current release keeps the transitional dialect until the
  frontend, budget, and path-semantics changes land.
- Follow-up changes: `adopt-gql-query-frontend`, `add-query-budget`, `add-gql-path-semantics`,
  `add-gql-composition`, `add-gql-values`, and `harden-for-1.0`.
- No runtime dependencies, storage layout changes, API changes, or CLI changes.
