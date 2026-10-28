# Tasks: add GQL match modes

## 1. Lexer, AST, and parser

- [x] 1.1 Add `DIFFERENT`, `EDGES`, `REPEATABLE`, and `ELEMENTS` to `Keyword` and update the
      keyword tests. Verify each is case-insensitive, that each is rejected as a plain variable
      without backticks, and that a backtick-quoted spelling still works. Run
      `hatch test tests/engine/query/test_lexer.py`.
- [x] 1.2 Add the `MatchMode` enum and `Match.match_mode` with a `REPEATABLE ELEMENTS` default;
      carry it on `MatchStage` and `OptionalMatchStage`. Verify imports and type checks with
      `hatch check --fix`.
- [x] 1.3 Parse the optional match mode after `MATCH`/`OPTIONAL MATCH` and before the path mode.
      Verify both spellings, both orders with a path mode, multiple comma-separated patterns, and
      a missing `EDGES`/`ELEMENTS` position. Verify `INSERT DIFFERENT EDGES ...` is rejected before
      execution. Run parser tests.
- [x] 1.4 Verify path-mode resolution is untouched: legacy and canonical quantifier defaults,
      explicit per-path and clause modes, and the mixed-quantifier error all still pass.

## 2. Semantic analysis and planning

- [x] 2.1 Propagate the clause match mode to the analysis stages and verify an explicitly
      repeatable clause and a default clause produce the same plan. Verify plan details distinguish
      `DIFFERENT EDGES`.
- [x] 2.2 Verify match-mode scope: an earlier stage's bound relationship can be rebound, a later
      clause cannot constrain an earlier one, and the mode never applies to `INSERT`, `CREATE`, or
      `MERGE`. Run semantic tests.
- [x] 2.3 Add regression tests that the default match mode does not change any existing row count
      or binding order. Run `hatch test tests/engine/query`.

## 3. Fixed-pattern enforcement

- [x] 3.1 Record relationship aliases across all patterns of a clause in `Compiler` and add the
      `DIFFERENT EDGES` cross-pattern inequality predicates. Verify the generated SQL for two
      patterns, a repeated variable, a parallel-relationship fixture, and an undirected fixture.
      Run compiler tests.
- [x] 3.2 Verify result behavior on the TRON fixtures: shared edge rejected under
      `DIFFERENT EDGES`, allowed under `REPEATABLE ELEMENTS` and the default, parallel edges
      allowed, self-loop consumed once, and repeated nodes allowed. Run query integration tests.
- [x] 3.3 Verify the rule interacts correctly with path modes: `WALK` plus `DIFFERENT EDGES` rejects
      edge reuse, `TRAIL` plus `DIFFERENT EDGES` behaves the same as `TRAIL`, and `SIMPLE`/`ACYCLIC`
      keep their node restrictions.

## 4. Quantified and mixed-pattern enforcement

- [x] 4.1 Add the usage-aware matcher (`_match_pattern_with_usage`) and keep `match` as a list
      wrapper. Verify the wrapper returns identical bindings for existing quantified tests.
- [x] 4.2 Enforce the clause-wide used-edge set in `_extend_memory` and completion paths. Verify a
      quantified `DIFFERENT EDGES` clause cannot reuse an edge across segments or across comma-
      separated patterns, and that a parallel-relationship route remains a distinct match.
- [x] 4.3 Verify a mixed clause (one fixed and one quantified pattern) routes through one matcher
      and enforces the same rule. Run the fixed-versus-quantified equivalence fixtures and assert
      equal row counts and bindings.
- [x] 4.4 Verify `OPTIONAL MATCH DIFFERENT EDGES` null-extends a row when no edge-disjoint match
      exists, and that budget counting includes rejected candidates. Run
      `hatch test tests/test_query_budget.py`.

## 5. Explain and user-facing behavior

- [x] 5.1 Add `MATCH DIFFERENT EDGES` to the explain output for the affected stage and omit the
      default mode. Verify with `hatch test tests/test_explain.py`.
- [x] 5.2 Add conformance cases `different-edges-shared-edge`, `repeatable-elements-shared-edge`,
      `different-edges-quantified`, `different-edges-two-patterns`, and
      `different-edges-parallel` to `tests/conformance/cases.json` using TRON fixtures. Verify with
      `hatch test tests/test_conformance.py`.

## 6. Profile and documentation

- [x] 6.1 Flip the `DIFFERENT EDGES` and `REPEATABLE ELEMENTS` profile rows to `supported`, state
      the default, and link each row to its corpus case. Verify `hatch test tests/test_gql_profile.py`.
- [x] 6.2 Add a "Match modes" section to `docs/reference/query-language.md`, update the path-mode
      section to point at it, and update the grammar summary with `match-mode` and the clause
      position. Document the reserved words and the backtick migration. Run
      `hatch run docs:build`.
- [x] 6.3 Update `docs/reference/gql-profile.md` with the match-mode default, scope, and
      intersection rule, and update the path-semantics summary table.
- [x] 6.4 Update `docs/guides/querying.md` and `examples/tours/04-paths.gql` with a worked
      `DIFFERENT EDGES` example on the cycle and parallel fixtures. Update runnable `README.md`
      examples only if they mention match modes. Run
      `hatch test tests/test_readme.py tests/test_docs_examples.py`.
- [x] 6.5 Add an end-user `CHANGELOG.md` entry under `## [Unreleased]`, including the reserved-word
      migration note. Verify it names outcomes and the backtick step.

## 7. Verification

- [x] 7.1 Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; verify all pass and
      coverage is at least 80%.
- [x] 7.2 Run `openspec validate add-gql-match-modes --strict` and verify the change validates.
- [x] 7.3 Confirm no query result changes without the explicit keyword by running the full
      conformance corpus against the previous expected rows.
- [x] 7.4 Audit imports for the one-way rule and confirm no new runtime dependency.

## Workflow follow-up

- Archive the change after review.
- `add-gql-path-search` and `add-gql-grouped-quantified-paths` apply this clause-level rule to
  their path sets; reuse the usage-aware matcher instead of adding a second implementation.
