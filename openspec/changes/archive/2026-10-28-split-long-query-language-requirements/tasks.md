# Tasks

## 1. Delta Correctness

- [x] 1.1 Verify each of the five `MODIFIED` blocks has a description of 500 characters or fewer and
      retains every scenario from its current main-spec requirement. Use `openspec show
      split-long-query-language-requirements --json --deltas-only` and compare the scenario lists
      with `openspec/specs/graph-query-language/spec.md`.
- [x] 1.2 Verify all 67 affected original scenarios remain present under their `MODIFIED`
      requirements, and every `ADDED` requirement has at least one scenario with a distinct name.
      A local comparison script over the current spec and the delta must report no missing original
      scenarios and no added requirement without scenarios.
- [x] 1.3 Review the eight new requirement boundaries against `design.md` and confirm that no
      normative rule was dropped or changed. The review must cover statement structure, `NEXT`,
      row sources, `UNWIND` ordinality/scope, create validation, relationship constraints,
      `RETURN NO BINDINGS`, and grouping keys.

## 2. Validation and Scope

- [x] 2.1 Run `openspec validate split-long-query-language-requirements --strict` and confirm it
      reports the change as valid.
- [x] 2.2 Run `git diff --check` and inspect `git status --short`; confirm the change contains only
      `openspec/changes/split-long-query-language-requirements/` and no `src/`, `tests/`, `docs/`,
      or `CHANGELOG.md` edits.
- [x] 2.3 Confirm that no Sphinx page or changelog entry is required because the change only
      reorganizes requirement text and does not alter observable behavior, the public API,
      dependencies, packaging, or query semantics. Record that rationale in the implementation
      summary.

## 3. Repository Checks

- [x] 3.1 Run `hatch check --fix` and confirm Ruff and Pyrefly pass without modifying project files.
- [x] 3.2 Run `hatch test` and confirm the suite passes with coverage at or above the configured
      80% gate.

## Workflow follow-up

- Archive the change after review.
- During archive sync, place each added requirement immediately after the requirement it was split
  from, preserving the order in the delta.
- After archive, run `openspec validate graph-query-language --type spec --strict` and
  `openspec validate --specs --strict`; confirm the five long-requirement warnings are gone.
- Confirm the archived change is the only result of this work and no active changes remain.
