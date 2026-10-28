# Tasks: add GQL unbounded traversal

## 1. Frontend accepts open quantifiers

- [x] 1.1 Extend `_legacy_quantifier` and `_canonical_quantifier` in
      `src/pygrafito/engine/query/parser.py` to return an unbounded upper bound for `*`, `+`,
      `{m,}`, and `*n..`, keeping `*` at a lower bound of zero and `+` at one. Verify parser tests
      for every form, for `{,n}`, and for a malformed bound. Run `hatch test tests/engine/query`.
- [x] 1.2 Update `SemanticAnalyzer._validate_quantifier` to accept a missing upper bound while
      still rejecting negative bounds and a lower bound above a present upper bound. Verify
      semantic tests for valid and invalid open forms and for the legacy/canonical mix rule.
- [x] 1.3 Preserve the resolved-mode rule: `*`, `+`, and `{m,}` default to `WALK`, `*n..` defaults
      to `TRAIL`, and an explicit mode wins. Verify with one test per form, including a legacy open
      form under an explicit `WALK`. Update the parser docstrings and AST comments that still say an
      upper bound is required.
- [x] 1.4 Remove the open-bound use of the `Gated` diagnostic and keep the error class available
      only if another change still needs it. Verify that `*`, `+`, `*1..`, and `{1,}` no longer
      raise a deferred-construct error. Run `hatch check --fix` and `hatch test`.

## 2. Live frontier and open walker

- [x] 2.1 Add `edges(node_id, direction, labels)` to `TraversalSource`; implement it for
      `AdjacencySnapshot` and `DatabaseNeighborhood`. Verify with traversal unit tests for
      direction, label filtering, undirected edges, self-loops, and missing nodes.
- [x] 2.2 Select the live neighborhood in `PatternEngine._capture` when any relationship position
      is open, and keep `TraversalCapture` for bounded patterns. Verify that a bounded query still
      captures one region and that an open query reads levels on demand with a counting repository
      stub.
- [x] 2.3 Make quantified walking handle an absent maximum. Verify open `TRAIL`, `SIMPLE`, and
      `ACYCLIC` walks terminate on the directed-cycle fixture, that open `WALK` can repeat an edge,
      and that zero-hop bindings produce the same node on both ends with `[]` as the relationship
      variable. Use TRON-themed fixtures.
- [x] 2.4 Verify the path variable and path functions for open matches: node order, relationship
      order, `length`, `nodes`, and `relationships`. Verify the relationship variable binds a list,
      and that single-relationship use is still rejected.
- [x] 2.5 Add tests for dense, diamond, parallel-relationship, self-loop, and unreachable cases,
      including `OPTIONAL MATCH` with an open pattern. Run `hatch test tests/engine`.

## 3. Demand-driven execution and snapshot

- [x] 3.1 Add `iter_match` to `PatternEngine` and make `match` a list wrapper so write stages and
      null detection keep the same results. Verify list and generator callers agree on the same
      fixtures and that closing the generator stops expansion.
- [x] 3.2 Add the internal `RowStream`, `Demand`, and `PlanShape` types and route streamable
      statements through a pull pipeline in `QueryExecutor`. Verify with executor tests for a final
      `LIMIT`, `LIMIT 0`, `OFFSET`, a filter before the limit, `OPTIONAL MATCH`, and a stage-level
      `LIMIT` that must materialize. Run `hatch test tests/test_query_integration.py`.
- [x] 3.3 Verify that `ORDER BY`, `DISTINCT`, aggregation, `GROUP BY`, set operations, `NEXT`,
      `FINISH`, and any write clause keep full evaluation and the current result order. Add one
      test per shape.
- [x] 3.4 Open a consistent read transaction for statements with an open pattern, drain read
      prefixes before writes, and release the snapshot on success, budget failure, and arbitrary
      exceptions. Verify snapshot isolation with a second connection writing during iteration,
      a read-then-write statement, and a reopen after a failed statement.
- [x] 3.5 Verify budget accounting and cancellation: expansions stop when demand is met; a
      no-demand open `WALK` raises `QueryBudgetExceededError` with no rows; a write statement that
      exceeds the budget rolls back completely and the handle stays usable. Run
      `hatch test tests/test_query_budget.py` plus the new rollback tests.
- [x] 3.6 Add the open-position marker to explain output and verify `EXPLAIN` shows
      `MATCH QUANTIFIED OPEN <mode>` for open patterns while bounded patterns keep their current
      lines. Run `hatch test tests/test_explain.py`.

## 4. User-facing behavior, corpus, and documentation

- [x] 4.1 Add conformance cases `open-star`, `open-plus`, `open-canonical-tail`,
      `open-legacy-tail`, `unbounded-walk-limit`, `unbounded-trail-cycle`, and
      `unbounded-zero-hop` to `tests/conformance/cases.json`, using TRON-themed fixtures and
      stable feature ids. Verify with `hatch test tests/test_conformance.py`.
- [x] 4.2 Flip the `Open-ended quantifiers`, `*`, `+`, `{m,}`, and `*n..` profile rows to
      `supported`, update the current-status prose, and link each row to its corpus case. Verify
      `hatch test tests/test_gql_profile.py` and that no path row is left `gated` by this change.
- [x] 4.3 Update `docs/reference/query-language.md` and its grammar summary: open forms, the
      legacy open form, zero-hop bindings, demand-driven limits, and full-evaluation shapes.
      Verify `hatch run docs:build` with warnings as errors.
- [x] 4.4 Update `docs/guides/querying.md`, `examples/tours/04-paths.gql`, and the runnable
      `README.md` examples to show a bounded open query, a `LIMIT`-bounded open query, and the
      budget-error shape. Run `hatch test tests/test_readme.py tests/test_docs_examples.py`.
- [x] 4.5 Record measured open-walk behavior in `docs/reference/performance.md`: in-memory and
      file-backed expansion rates, the effect of `LIMIT`, and the cost of `ORDER BY` and
      aggregation. Verify the numbers come from a checked-in benchmark or a documented measurement
      command, and that `hatch test tests/test_benchmarks.py` passes.
- [x] 4.6 Add an end-user `CHANGELOG.md` entry under `## [Unreleased]` describing open-ended
      traversal and early-stopping limits. Verify it names outcomes, not internal classes, SQL, or
      test names.

## 5. Verification

- [x] 5.1 Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; verify all pass with
      warnings treated as errors and coverage at least 80%.
- [x] 5.2 Run `openspec validate add-gql-unbounded-traversal --strict` and verify the change
      validates.
- [x] 5.3 Audit the diff for one-way imports (`model <- storage <- engine <- __init__`) and for
      standard-library-only runtime dependencies. Verify no public signature changed.
- [x] 5.4 Re-run the open-walk benchmarks on a file-backed database and confirm the performance
      page matches the recorded values.

## Workflow follow-up

- Archive the change after review.
- `add-gql-match-modes` and `add-gql-path-search` build on the live frontier and streaming
  pipeline; keep the `TraversalSource`, `RowStream`, and `Demand` contracts stable or document the
  change in their designs.
