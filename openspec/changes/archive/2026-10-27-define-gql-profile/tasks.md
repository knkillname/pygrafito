# Tasks

This change is documentation and specification only. It publishes the GQL profile and adds the
`gql-profile` capability; it does not change the parser, engine, storage, public API, or CLI.

## 1. Profile contract

- [x] 1.1 Write `docs/reference/gql-profile.md` with the profile's purpose and scope, a
      current-status section, the five-tier classification table, the canonical/alias/
      compatibility/extension/out-of-profile tables, the path-mode resolution rule, the
      query-budget policy, the conformance matrix, the corpus contract, and the migration
      guidance. Verify every requirement in `specs/gql-profile/spec.md` maps to a section or table
      and `hatch run docs:build` passes.
- [x] 1.2 Add the current-status section: the current release remains the transitional
      Cypher-flavored dialect, canonical forms are target or gated, and README/quickstart examples
      remain runnable. Verify no page claims `INSERT`, `FILTER`, or `WALK` is implemented now, and
      `tests/test_readme.py` still passes.
- [x] 1.3 Add the feature matrix with the `supported`, `gated`, `deferred`, and `out of profile`
      statuses, a deviation column, and a corpus-case column. Verify every canonical, alias,
      compatibility, and extension row and every out-of-profile/deferred item from the profile
      tables appears in the matrix.
- [x] 1.4 Add the query-budget section with the relationship-expansion and intermediate-row
      counters, the documented default, the per-query override, the execution-error contract, and
      the write rollback rule. Verify the page states that `WALK` is gated on the budget and marks
      it gated in the matrix.
- [x] 1.5 Add the migration section: legacy `*n..m` to `TRAIL`, canonical `{n,m}` under `WALK`,
      explicit-mode precedence, the mixed-quantifier error, the alias mapping, the extension set,
      and the `paths()` trail note. Verify the examples are TRON-themed and match `design.md`.

## 2. Documentation integration

- [x] 2.1 Add `reference/gql-profile` to the reference toctree in `docs/index.md` and to the
      reference card. Verify the built navigation lists the page and `hatch run docs:build` passes.
- [x] 2.2 Add a top-of-page banner to `docs/reference/query-language.md` pointing to the profile
      as the target contract and labeling the current page as the transitional dialect. Verify the
      link resolves and the page's runnable examples are unchanged.
- [x] 2.3 Add a one-line profile link to `README.md` near the query-language feature and keep the
      current examples runnable. Verify `tests/test_readme.py` passes.
- [x] 2.4 Add the profile rule to `AGENTS.md`: canonical GQL follows
      `docs/reference/gql-profile.md`, and a query change must update the profile, matrix, and
      corpus. Verify the wording does not contradict the existing architecture, data, or
      documentation rules.
- [x] 2.5 Add `tests/test_gql_profile.py` to assert that the profile page exists, is in the
      reference toctree, contains the five tier headings, and uses only the four matrix statuses.
      Verify `hatch test tests/test_gql_profile.py --no-cov` passes and `hatch check --fix` reports
      no lint or type errors.
- [x] 2.6 Update `CHANGELOG.md` under `## [Unreleased]` with an `Added` entry for the published
      GQL profile and a `Changed` entry for the five-tier compatibility policy, the `WALK` budget
      gate, and the legacy `TRAIL` default. Verify the entry follows Keep a Changelog and does not
      claim current execution of unimplemented GQL forms.

## 3. Validation and release hygiene

- [x] 3.1 Run `openspec validate define-gql-profile --strict` and verify the new capability and
      all deltas pass with no warnings.
- [x] 3.2 Run `hatch run docs:build` and verify there are no warnings and the profile page is
      reachable from the reference navigation.
- [x] 3.3 Run `hatch test` and verify the full suite passes and coverage remains at least 80%.
- [x] 3.4 Run `hatch check --fix` and verify Ruff and Pyrefly pass for the documentation test.
- [x] 3.5 Run `git diff --check` and verify there are no whitespace errors.
- [x] 3.6 Verify the diff scope touches only `docs/`, `tests/test_gql_profile.py`, `AGENTS.md`,
      `CHANGELOG.md`, and `openspec/changes/define-gql-profile/`; confirm there are no `src/`
      changes.
- [x] 3.7 Record the pre-existing `openspec validate --specs --strict` warnings for the two long
      `graph-query-language` requirements as a release-hygiene follow-up. Do not edit
      `graph-query-language` in this change.

## Workflow follow-up

- Archive the change after review and after the profile page, documentation test, and change
  validation pass.
- Fix the two pre-existing `graph-query-language` long-requirement warnings (`Relationship
  patterns` and `CREATE clause`) in a separate release-hygiene change before running
  repository-wide strict validation.
- Confirm the new `gql-profile` capability is added to the main specs at archive and still
  validates.
- Confirm this change introduced no runtime code, parser, engine, storage, or public API changes.
- Start `adopt-gql-query-frontend` only after this change is reviewed; do not implement it here.
