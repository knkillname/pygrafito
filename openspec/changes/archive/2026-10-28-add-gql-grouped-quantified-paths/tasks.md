# Tasks: add GQL grouped quantified paths

## 1. AST and parser

- [x] 1.1 Add `SimplePathTerm`, `GroupedPathTerm`, and `PathPattern.terms` with a `flatten()`
      helper. Parse existing simple and quantified patterns into one simple term. Verify every
      existing parser, semantic, compiler, and engine test passes unchanged. Run
      `hatch check --fix` and `hatch test`.
- [x] 1.2 Implement group detection with the documented lookahead: `((`, a path-mode keyword, or an
      identifier followed by `=` after the opening `(`. Verify a node pattern, a property map, a
      nested group, and a group path variable each parse in the intended form.
- [x] 1.3 Parse the group head (`[identifier "="] [path-mode] path-pattern`), the closing `)`, and
      the quantifier `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, or `+`. Verify each form, a missing
      quantifier, a malformed bound, and the legacy `*n..m` rejection with positions.
- [x] 1.4 Parse juxtaposed terms and build the term sequence, including groups before and after a
      simple path and nested groups. Verify the boundary-sharing shape reaches the walker as
      adjacent terms.
- [x] 1.5 Reject a path-search prefix inside a group and a parenthesized path without a quantifier
      with positioned errors. Run parser tests.

## 2. Semantic analysis

- [x] 2.1 Walk terms in `_bind_pattern`; register group node variables as lists, group relationship
      variables as lists, and group path variables as paths. Verify result kinds with semantic
      tests.
- [x] 2.2 Enforce group scopes: first introduction, one occurrence per group, no shadowing of an
      outer variable, and no reference to an enclosing group's local variables from a nested group.
      Verify each rejection with a positioned error.
- [x] 2.3 Enforce the structural rules: every group contains a relationship position, every group
      has a progress-making relationship with a minimum of at least one, a lone zero-lower group is
      rejected, and a group path variable requires a positive lower bound. Verify each error before
      execution.
- [x] 2.4 Verify the outer/inner mode resolution, the clause match mode, and the path-search prefix
      are carried into the plan. Add regression tests for simple and quantified patterns.

## 3. Walker and bindings

- [x] 3.1 Add `GroupFrame` and the frame stack to `WalkState`; walk simple terms exactly as today.
      Verify all existing pattern-engine tests still pass.
- [x] 3.2 Implement bounded group iteration: push, iterate, accumulate, close, and continue. Verify
      `{2}` matches the unrolled two-copy form on the TRUSTS cycle and diamond fixtures, with TRON
      names.
- [x] 3.3 Implement group variable list bindings for node and relationship variables, nested
      flattening, and the group path variable. Verify the lists, their order, and the concatenated
      path nodes and relationships.
- [x] 3.4 Implement zero iterations with empty lists and a shared boundary node, and enforce the
      progress rule at runtime as a defensive check. Verify zero-iteration and boundary cases on
      the self-loop and parallel-relationship fixtures.
- [x] 3.5 Apply the inner and outer path modes and the clause match mode to every iteration.
      Verify `WALK` outer with `ACYCLIC` inner, `TRAIL` inner, `DIFFERENT EDGES` across iterations,
      and a repeated boundary node.
- [x] 3.6 Verify `OPTIONAL MATCH` null-extension, path functions (`length`, `nodes`,
      `relationships`), and list comprehensions over group variables.

## 4. Open groups, search, and execution

- [x] 4.1 Support open group quantifiers (`{m,}`, `*`, `+`) through the live frontier and demand
      pipeline. Verify an open `TRAIL` group terminates, an open `WALK` group with `LIMIT` stops
      early, and an open `WALK` group without demand raises `QueryBudgetExceededError` with no
      partial result.
- [x] 4.2 Extend the path-search state key with the frame stack and evaluate `ANY SHORTEST`,
      `ALL SHORTEST`, and `SHORTEST k` over grouped paths. Verify the selected paths and the
      deterministic order on the diamond, cycle, parallel, and self-loop fixtures.
- [x] 4.3 Route any grouped pattern to the pattern engine instead of the SQL compiler and add
      `GROUP {m,n}` / `GROUP OPEN` to explain. Verify `hatch test tests/test_explain.py` and the
      grouped fixed-pattern rows.
- [x] 4.4 Verify budget accounting: every relationship expansion counts once, a group iteration
      with a non-progressing body is rejected before execution, and a write statement rolls back
      on a budget failure. Run `hatch test tests/test_query_budget.py`.

## 5. Corpus and profile

- [x] 5.1 Add conformance cases `grouped-fixed-repetition`, `grouped-bounded-diamond`,
      `grouped-list-bindings`, `grouped-zero-iterations`, `grouped-nested`, and
      `grouped-inner-mode` to `tests/conformance/cases.json` using TRON fixtures. Verify
      `hatch test tests/test_conformance.py`.
- [x] 5.2 Flip the `Grouped quantified paths` profile row to `supported`, link it to its cases, and
      remove the grouped entry from the gated follow-up table. Verify
      `hatch test tests/test_gql_profile.py`.

## 6. Documentation

- [x] 6.1 Add a "Grouped path patterns" section to `docs/reference/query-language.md` with
      juxtaposition, the group syntax, quantifiers, inner modes, group variable lists, zero
      iterations, progress, and errors. Update the grammar summary with the path-term and group
      productions. Run `hatch run docs:build`.
- [x] 6.2 Update `docs/reference/gql-profile.md` with the supported status, the group-variable
      model, and the inner/outer mode rule. Update the path-semantics matrix and the
      interaction table.
- [x] 6.3 Update `docs/guides/querying.md`, `examples/tours/04-paths.gql`, and any runnable
      `README.md` examples with a two-hop group over the TRUSTS cycle and a group-variable list
      projection. Run `hatch test tests/test_readme.py tests/test_docs_examples.py`.
- [x] 6.4 Update `docs/reference/performance.md` with the grouped-pattern cost and the absence of
      SQL pushdown for groups.
- [x] 6.5 Add an end-user `CHANGELOG.md` entry under `## [Unreleased]`.

## 7. Verification

- [x] 7.1 Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; verify all pass and
      coverage is at least 80%.
- [x] 7.2 Run `openspec validate add-gql-grouped-quantified-paths --strict` and verify the change
      validates.
- [x] 7.3 Run the grouped fixtures on `:memory:` and a `tmp_path` file database and verify the
      same rows, bindings, and order.
- [x] 7.4 Audit imports for the one-way rule and confirm no new runtime dependency.

## Workflow follow-up

- Archive the change after review.
- With this change archived, every path-engine row is supported; `complete-gql-profile` owns the
  final matrix, corpus, and prose audit.
