# Proposal: define the profile-complete GQL 1.0 scope

## Why

The 0.9 profile is honest about the current release, but it is not exhaustive. Unsupported
constructs are scattered across prose, the matrix uses `deferred` for work that is now a 1.0
target, and the release gate is not frozen. The project needs one authoritative profile before
the expression, subquery, set-operation, and path-engine changes begin.

## What Changes

- Define v1.0 as profile-complete against the published `pygrafito` GQL profile, not ISO-complete.
- Make the profile exhaustive: every in-scope construct, alias, extension, and rejected form has
  an explicit tier and status.
- Adopt four statuses: `supported`, `gated`, `deferred`, and `out of profile`. Use `gated` for
  in-scope 1.0 work that is not implemented yet, and reserve `deferred` for post-1.0 direction.
  The 1.0 release gate requires zero `gated` and zero `deferred` rows.
- Put `UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT` in scope as 1.0 work.
- Put the expression surface in scope: `CASE`, map literals, list indexing and slicing, list
  comprehensions, canonical `||` concatenation with `+` as a compatibility alias, path functions,
  the agreed scalar function set, and `WITH *` as part of the `WITH` extension.
- Put read-only `EXISTS { ... }` and `COUNT { ... }` query expressions in scope.
- Put match modes, grouped quantified paths, path search prefixes, open-ended quantifiers, and
  unbounded traversal in scope.
- Keep Cypher-only convenience syntax out of profile: `CALL { ... }`, whole-map assignment,
  `exists(n.prop)`, regex predicates, and `shortestPath()`.
- Keep the non-language surface out of profile: catalog, graph types, sessions, procedures,
  in-language transactions, `SELECT`, temporal values, servers and drivers, multi-graph storage,
  graph-algorithm APIs, full Cypher, vector search, and full-text search.
- Add a feature-level conformance matrix, an exhaustive construct inventory, and a rejected-forms
  list instead of relying on prose alone.
- Define the 1.0 release gate, profile freeze policy, and consistency requirements between the
  matrix, prose, grammar, query reference, tours, and corpus.
- Update the published profile and the `gql-profile` specification. This change defines scope; it
  does not implement the parser, engine, or public API changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `gql-profile`: make the profile exhaustive, add the `gated` status distinction, freeze the 1.0
  target scope and out-of-profile boundary, and define the release gate and freeze policy.

## Impact

- Documentation: rewrite `docs/reference/gql-profile.md`, update the query-language reference's
  gated and unsupported cross-references, and add the 1.0 profile contract to the changelog.
- Specification: change the requirements in `openspec/specs/gql-profile/spec.md` through a delta
  spec.
- No runtime code, parser, engine, schema, CLI, package dependency, or public API changes.
- Downstream work: expression surface, subqueries, set operations, path semantics, unbounded
  traversal, match modes, path search, grouped quantified paths, profile completion, hardening,
  and the 1.0 release.
