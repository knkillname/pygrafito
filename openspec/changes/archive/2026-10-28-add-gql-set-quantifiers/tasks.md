# Tasks

## 1. Frontend and execution

- [x] 1.1 Add `INTERSECT_ALL` and `EXCEPT_ALL` to `SetOperation` in
  `src/pygrafito/engine/query/ast.py`, and make `Parser._set_operator` accept `ALL` and `DISTINCT`
  after `UNION`, `INTERSECT`, and `EXCEPT`. Verify parser tests assert the new enum values and that
  a second quantifier such as `INTERSECT ALL DISTINCT` is rejected.
- [x] 1.2 Implement multiset combination in `Executor._combine_rows`: one counter over the right
  operand's canonical row keys, `min` copies for `INTERSECT ALL`, and `max(left - right, 0)` for
  `EXCEPT ALL`. Verify focused executor tests cover duplicates, empty counts, `36` versus `36.0`,
  left-associativity, and first-seen output order.
- [x] 1.3 Confirm `CompoundPlan.operators` and explain output render `INTERSECT ALL` and
  `EXCEPT ALL` through `SetOperation.value`. Verify `hatch test tests/test_explain.py` passes and
  add a plan assertion if no existing test covers compound operators.
- [x] 1.4 Run `hatch check --fix` and the focused query tests
  (`hatch test tests/engine/query`) and fix every failure before moving on.

## 2. Conformance and profile

- [x] 2.1 Add corpus cases to `tests/conformance/cases.json` for `INTERSECT ALL`, `EXCEPT ALL`,
  explicit `DISTINCT`, canonical `36`/`36.0` equality, an empty right operand, and a left-to-right
  chain. Use `UNWIND` row sources rather than new fixtures. Verify
  `hatch test tests/test_conformance.py`.
- [x] 2.2 Add `INTERSECT ALL` and `EXCEPT ALL` matrix rows and construct-inventory rows to
  `docs/reference/gql-profile.md`, and update the set-operation rows in the current-status and
  canonical-surface tables. Verify `hatch test tests/test_gql_profile.py` reports no missing
  corpus coverage.
- [x] 2.3 Document the quantifier grammar and duplicate-count semantics in
  `docs/reference/query-language.md`, including the grammar summary and a worked example for each
  form. Verify `hatch run docs:build` passes with warnings treated as errors.

## 3. Release hygiene

- [x] 3.1 Add an end-user `Added` entry under `## [Unreleased]` in `CHANGELOG.md` for the new set
  quantifiers, without internal names or file paths. Verify the wording says what users can now
  write and that the entry is in the right category.
- [x] 3.2 Run `openspec validate add-gql-set-quantifiers --strict` and fix any artifact issue.
- [x] 3.3 Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; confirm coverage is at
  least 80% and all three commands pass before marking the change complete.

## Workflow follow-up

- Sync `graph-query-language` into the main specs and archive the change after review.
- Tick `add-gql-set-quantifiers` in `tmp/planning.md` once the change is implemented, synced, and
  archived.
