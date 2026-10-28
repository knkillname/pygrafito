# Proposal

## Why

The set-operation surface is almost complete, but it rejects `INTERSECT ALL`, `EXCEPT ALL`, and
explicit `DISTINCT`. Those are standard GQL set quantifiers, and their absence is the only
remaining language gap before the 1.0 profile audit. Keeping `UNION ALL` while rejecting the other
`ALL` forms is an arbitrary boundary that `complete-gql-profile` would otherwise have to defend.
Add them now, before the profile is frozen, so the audit checks a complete surface instead of also
changing it.

## What Changes

- Support `INTERSECT ALL` and `EXCEPT ALL` with multiset semantics: keep
  `min(left_count, right_count)` and `max(left_count - right_count, 0)` copies of each row.
- Support explicit `DISTINCT` on `UNION`, `INTERSECT`, and `EXCEPT` as the explicit default; the
  bare operator keeps the same meaning.
- Keep operators left-associative and keep every existing column, row-equality, ordering,
  pagination, read-only, transaction, and budget rule unchanged.
- Add conformance cases, profile matrix and inventory rows, the query-language reference and
  grammar summary, and a changelog entry.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-query-language`: the set-operation requirement gains the `ALL` variants, explicit
  `DISTINCT`, and their duplicate-count semantics.

## Impact

- Query frontend: `src/pygrafito/engine/query/ast.py`, `parser.py`, and `executor.py`.
- Tests: `tests/conformance/cases.json` and the focused query tests.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md`, and
  `CHANGELOG.md`.
- No public API, storage schema, snapshot format, CLI, dependency, or reserved-keyword changes.
