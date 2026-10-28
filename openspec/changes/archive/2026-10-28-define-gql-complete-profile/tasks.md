# Tasks: define the profile-complete GQL 1.0 scope

## 1. Profile contract

- [x] 1.1 Update the status legend and current-status prose in `docs/reference/gql-profile.md` so
  it defines `supported`, `gated`, `deferred`, and `out of profile` exactly as the design does,
  and distinguishes current behavior from the 1.0 target. Verify the page states that `gated`
  means in the 1.0 profile and `deferred` means post-1.0.
- [x] 1.2 Reclassify the existing path rows from `deferred` to `gated` and keep supported row
  labels and corpus feature ids stable. Clarify the existing deviations for `NEXT`, `GROUP BY`,
  `RETURN`, quantifiers, aliases, and extensions without changing supported feature ids. Verify
  no in-scope path row remains `deferred`.
- [x] 1.3 Add gated matrix rows and inventory entries for the expression surface: `CASE`, map
  literals, list indexing and slicing, list comprehensions, canonical `||`, `+` string
  concatenation as a compatibility alias, `nodes`, `relationships`, `length`, the extended scalar
  functions, and `WITH *`. Verify each row and inventory entry is `gated` and names
  `add-gql-expression-surface`.
- [x] 1.4 Add gated matrix rows and inventory entries for `EXISTS { ... }`, `COUNT { ... }`,
  `UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT`. Verify the subquery rows name
  `add-gql-subqueries` and the set-operation rows name `add-gql-set-operations`.
- [x] 1.5 Add gated matrix rows and inventory entries for `DIFFERENT EDGES`, `REPEATABLE
  ELEMENTS`, grouped quantified paths, `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`, and
  open-ended quantifiers. Resolve the current overlap between open-ended quantifiers and
  `Unbounded WALK` so each construct has one row and one status. Verify every path row is `gated`
  and names the correct follow-up change.
- [x] 1.6 Add the expanded out-of-profile table and the rejected-forms table. Include the
  Cypher-only forms, non-language capabilities, `MERGE` invalid combinations, and catalog
  operations from the design. Verify every entry has a reason and an error contract.
- [x] 1.7 Add the construct inventory table. Verify every matrix row has at least one inventory
  entry and every canonical spelling, alias, compatibility form, extension, and out-of-profile
  construct from `docs/reference/query-language.md` is classified.
- [x] 1.8 Add the 1.0 release gate and profile freeze policy to the profile page. Verify every gate
  item from `design.md` is present and states how it is checked.
- [x] 1.9 Update the gated and unsupported sections of `docs/reference/query-language.md` to link
  to the profile target without claiming that gated constructs execute. Verify the reference still
  describes only current 0.9 behavior.
- [x] 1.10 Add an end-user changelog entry under `## [Unreleased]` for the new 1.0 profile contract.
  Verify the entry follows the project's changelog style and names the outcome rather than the
  internal matrix mechanics.

## 2. Verification

- [x] 2.1 Run `openspec validate define-gql-complete-profile --strict` and verify the proposal,
  delta spec, design, and tasks validate.
- [x] 2.2 Run `hatch test tests/test_gql_profile.py` and verify the profile consistency tests pass
  with the supported rows and existing corpus feature ids unchanged.
- [x] 2.3 Audit the construct inventory against the matrix, the query-language gated and
  unsupported sections, and the parser's unsupported-construct tests. Verify no recognized
  construct is missing and no inventory entry lacks a matrix row or rejected form.
- [x] 2.4 Run `hatch run docs:build` and verify it exits successfully with warnings treated as
  errors.
- [x] 2.5 Run `git diff --check` and `git diff --name-only`; verify the change touches only
  documentation, the changelog, and this change's artifacts, with no parser, engine, schema, CLI,
  dependency, or public API changes.

## Workflow follow-up

- Archive the change after review.
- Use the gated rows to drive the expression, subquery, set-operation, path-semantics, path-engine,
  and profile-completion changes.
- `complete-gql-profile` owns the automated release-gate consistency checks.
