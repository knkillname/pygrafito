# Tasks: define the GQL path-semantics matrix

## 1. Publish the target path semantics

- [x] 1.1 Add a "Path semantics" section to `docs/reference/gql-profile.md` covering the
      path-mode/match-mode split, the combined-constraint rule, and the `REPEATABLE ELEMENTS`
      default. Verify every row of the design's path-mode and match-mode tables appears and that
      the page states the current status of each construct. Run `hatch run docs:build` and fix
      warnings.
- [x] 1.2 Add the quantifier table (closed, open, legacy, grouped), the zero-hop binding table, and
      the termination table to the same page. Verify each form names its lower and upper bound,
      canonical tier, default path mode, and follow-up change.
- [x] 1.3 Add the path-search section: partition definition, per-prefix selection, duplicate rule,
      tie-break order, `SHORTEST k` literal rule, and the grammar position of the prefix. Verify
      the examples use the published TRON fixtures and remain runnable once the implementing
      change lands; mark them as target examples, not current behavior.
- [x] 1.4 Add the grouped-path section: juxtaposition, inner modes, group variables, zero
      iterations, progress rule, and rejected combinations. Verify the profile classifies grouped
      paths as one row with one follow-up change.
- [x] 1.5 Add the rejected-combination list and the migration notes to the profile page and to
      `CHANGELOG.md` under `## [Unreleased]`. Verify the changelog entry is end-user focused and
      names no internal classes or SQL.

## 2. Corpus and consistency plan

- [x] 2.1 Add the planned feature identifiers and case names from `design.md` to the corpus plan
      in the change, and verify each gated profile row still names exactly one follow-up change
      and each planned case maps to one row.
- [x] 2.2 Verify `tests/test_gql_profile.py` still passes unchanged: no status has flipped and no
      supported row lost its corpus case. Run `hatch test tests/test_gql_profile.py`.
- [x] 2.3 Verify the query-language reference still describes current behavior only: the gated
      table links to the profile target, and no gated construct is presented as executable. Run
      `hatch test tests/test_docs_examples.py` and `hatch run docs:build`.

## 3. Verification

- [x] 3.1 Run `openspec validate define-gql-path-semantics --strict` and verify the change
      validates with the declared `skip_specs` opt-out.
- [x] 3.2 Run `git diff --stat` and verify the change touches only `docs/`, `CHANGELOG.md`, and
      this change's artifacts, with no parser, engine, schema, CLI, dependency, or public API
      changes.
- [x] 3.3 Confirm every later path-engine proposal cites the decision it implements and records
      any deviation as a change to this matrix, not as silent implementation drift.

## Workflow follow-up

- Archive the change after review.
- Keep this design as the reference for `add-gql-unbounded-traversal`, `add-gql-match-modes`,
  `add-gql-path-search`, and `add-gql-grouped-quantified-paths`.
- If an implementing change must revise a decision, update this matrix and the profile page in the
  same change instead of leaving two sources of truth.
