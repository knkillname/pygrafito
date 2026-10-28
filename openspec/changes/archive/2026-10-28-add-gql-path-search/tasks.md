# Tasks: add GQL path search

## 1. Lexer, AST, and parser

- [x] 1.1 Add `ANY` and `SHORTEST` to `Keyword` and update lexer tests, including backtick
      migration for variables named `any` and `shortest`. Run
      `hatch test tests/engine/query/test_lexer.py`.
- [x] 1.2 Add `PathSearchKind`, `PathSearch`, and `PathPattern.search` to `ast.py`. Verify type
      checks with `hatch check --fix`.
- [x] 1.3 Parse `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST <integer>` after the optional
      path variable and before the path mode, for clause modes and per-path modes. Verify all four
      prefixes, the two orders with a path mode, a missing integer, a parameter, and an expression.
      Run parser tests.
- [x] 1.4 Verify a prefix inside a grouped pattern is rejected with a positioned error once grouped
      syntax exists; for this change, reject a prefix after an opening parenthesis if the parser
      recognizes it. Verify no prefix is accepted on `INSERT`, `CREATE`, or `MERGE`.

## 2. Semantic analysis and planning

- [x] 2.1 Validate one prefix per path, an integer literal `k`, and `k >= 0`; reject a parameter,
      an expression, a float, and a negative value before execution. Verify semantic tests.
- [x] 2.2 Validate path-variable interaction: `p = ANY SHORTEST ...` binds the selected path, and a
      prefix without a path variable still binds node and relationship variables. Verify with
      semantic tests.
- [x] 2.3 Carry the search selection in the analysis stage and plan, and add `PATH SEARCH <prefix>`
      to explain. Verify `hatch test tests/test_explain.py`.
- [x] 2.4 Add regression tests that a pattern without a prefix produces the same plan and rows as
      before. Run `hatch test tests/engine/query`.

## 3. Search evaluator

- [x] 3.1 Add `PathSearchEvaluator` in `pattern.py` and reuse the existing selection, predicate,
      binding, path-mode, and match-mode helpers. Verify a fixed two-hop pattern evaluates through
      the same helpers and produces the same node and relationship bindings as the regular matcher.
- [x] 3.2 Implement partition keys, layer ordering, the per-prefix selection limits, and the
      tie-break sequence. Verify `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST k` on the
      diamond, directed-cycle, parallel-relationship, self-loop, and unreachable fixtures using
      TRON names.
- [x] 3.3 Implement duplicate detection by node and orientation-aware relationship sequence and
      verify parallel relationships remain distinct. Verify `ALL SHORTEST` returns two paths on the
      diamond and one path when only one minimum route exists.
- [x] 3.4 Implement the frontier pruning rules and verify termination on an open `WALK` cycle for
      `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST k`. Verify the state key keeps at most the
      selection limit plus one arrival.
- [x] 3.5 Verify path variables and path functions for selected paths, plus `SHORTEST 0` producing
      no rows and charging no expansion. Run `hatch test tests/engine/query`.

## 4. Execution integration

- [x] 4.1 Route search stages through the demand pipeline so a final `LIMIT` stops partition
      discovery and expansion early. Verify with a counter-bearing test that fewer expansions occur
      with `LIMIT` than without.
- [x] 4.2 Verify `OPTIONAL MATCH` null-extends when a search selection is empty, and that
      `EXISTS { ... }` stops after the first selected row while `COUNT { ... }` consumes all of
      them.
- [x] 4.3 Verify search with `DIFFERENT EDGES`, with each path mode, and with a per-path mode that
      overrides a clause mode. Verify rejected candidates never appear and the budget counts the
      expansions that examined them.
- [x] 4.4 Verify a search statement uses the statement read snapshot and a concurrent write does
      not change selected paths. Verify a search-plus-write statement rolls back on a budget
      failure. Run `hatch test tests/test_query_budget.py`.
- [x] 4.5 Add the search marker to explain and verify the stage output names the prefix and, for an
      open pattern, the open marker.

## 5. Corpus and profile

- [x] 5.1 Add conformance cases `any-per-partition`, `any-shortest-diamond`,
      `all-shortest-diamond`, `shortest-k-parallel`, `shortest-k-zero`, and `shortest-self-loop` to
      `tests/conformance/cases.json` with TRON fixtures. Verify
      `hatch test tests/test_conformance.py`.
- [x] 5.2 Flip the `Path search prefixes`, `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST k`
      profile rows to `supported`, link each to its case, and state the partitioning and tie-break
      rules. Verify `hatch test tests/test_gql_profile.py`.

## 6. Documentation

- [x] 6.1 Add a "Path search" section to `docs/reference/query-language.md` with prefix syntax,
      partition semantics, the selection table, duplicate and tie-break rules, and examples for
      each prefix. Update the grammar summary with the path-search production and reserved words.
      Run `hatch run docs:build`.
- [x] 6.2 Update `docs/reference/gql-profile.md` with the supported status, the deterministic
      `ANY` choice, and the `ALL` non-goal. Update `docs/reference/performance.md` with the
      expansion behavior and the memory bound per partition.
- [x] 6.3 Update `docs/guides/querying.md`, `examples/tours/04-paths.gql`, and any runnable
      `README.md` examples with an `ANY SHORTEST` walk and a `SHORTEST k` example on the diamond.
      Run `hatch test tests/test_readme.py tests/test_docs_examples.py`.
- [x] 6.4 Add an end-user `CHANGELOG.md` entry under `## [Unreleased]`, including the reserved-word
      migration note.

## 7. Verification

- [x] 7.1 Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; verify all pass and
      coverage is at least 80%.
- [x] 7.2 Run `openspec validate add-gql-path-search --strict` and verify the change validates.
- [x] 7.3 Run the same search queries on `:memory:` and a `tmp_path` file database and verify
      identical selected paths and row order.
- [x] 7.4 Audit imports for the one-way rule and confirm no new runtime dependency.

## Workflow follow-up

- Archive the change after review.
- `add-gql-grouped-quantified-paths` reuses this evaluator for whole-path search and must reject a
  prefix inside a group.
