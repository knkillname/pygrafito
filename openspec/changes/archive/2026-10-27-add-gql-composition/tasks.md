# Tasks

## 1. Ordered operation pipeline

- [x] 1.1 Add a `WriteStage` wrapper, a segment-result stage, a `YieldStage`, and an ordered `Analysis.operations` tuple that preserves source order, keeping `stages` and `write_clauses` as derived views; verify analysis tests show a `WriteStage` between two read stages, a segment-result projection, and a `YieldStage`
- [x] 1.2 Make `PlanBuilder` and `QueryExecutor` consume `operations` in order, applying one write clause per `MutationExecutor.apply` call and projecting each non-final `RETURN` into the next segment; verify a `SET` then `REMOVE` parity test and a `CREATE` then `SET` parity test match the batch behavior, and an explain test shows the interleaved operator order with `NEXT` and `YIELD` boundaries
- [x] 1.3 Count rows and expansions per operation in the pipeline and preserve one `BudgetTracker` for the whole statement; verify a hand-built interleaved analysis rolls back an earlier write when a later stage exceeds the row limit and leaves the graph handle usable

## 2. LET clause

- [x] 2.1 Add the `Let` and `LetAssignment` AST nodes and parse `LET name = expression [, ...]`, including the per-segment position guard and the read-statement row-source rule; verify parser tests cover one and several assignments, a leading `LET`, a `LET` after `RETURN`, and a `LET` after a write in the same segment
- [x] 2.2 Bind `LET` in `SemanticAnalyzer` with left-to-right validation, no shadowing, no duplicate names, no aggregates, and kind preservation for a direct variable, matching the additive Cypher 25 form; verify semantic tests cover each rule and that `LET element = n` keeps the node kind for a later pattern
- [x] 2.3 Add a `LetStage` executor that evaluates assignments left to right per input row and counts emitted rows against the budget; verify executor tests cover a leading `LET`, a preserved scope, a computed binding, and a budget failure
- [x] 2.4 Remove the `LET` composition gate and its gated test, add conformance cases for the accepted and rejected forms, and flip the `LET` matrix row and status-board entry to supported; verify `hatch test tests/test_conformance.py tests/test_gql_profile.py tests/engine/query/test_gated.py` passes
- [x] 2.5 Document `LET` in the query-language reference and grammar, add a querying-guide example, and add the `[Unreleased]` changelog bullet; verify `hatch run docs:build` and `hatch test tests/test_docs_examples.py` pass

## 3. FOR ordinality and offset

- [x] 3.1 Add the ordinality fields and `OrdinalityKind` to `Unwind`/`UnwindStage`, and parse `WITH ORDINALITY name` and `WITH OFFSET name` after both `FOR ... IN ...` and `UNWIND ... AS ...`, rejecting a reused element name and the two forms together; verify parser tests cover both spellings, both bases, the UNWIND alias, and the error cases
- [x] 3.2 Bind the element and index names in `SemanticAnalyzer`, require a fresh index name, and reject a duplicate; verify semantic tests cover the accepted forms and each error
- [x] 3.3 Enumerate with the correct base in the executor, bind both names, keep null and empty lists rowless, and count each emitted row against the budget; verify executor tests assert 1-based ordinality, 0-based offset, list order, and the empty/null cases
- [x] 3.4 Remove the `ORDINALITY` composition gate and its gated test, add conformance cases for both forms and the errors, and flip the `FOR` ordinality/offset matrix row and status-board entry to supported; verify `hatch test tests/test_conformance.py tests/test_gql_profile.py tests/engine/query/test_gated.py` passes
- [x] 3.5 Document ordinality and offset in the FOR reference and grammar, add querying-guide examples, and add the changelog bullet; verify `hatch run docs:build` and `hatch test tests/test_docs_examples.py` pass

## 4. Explicit GROUP BY

- [x] 4.1 Add `group_by` to the `Return` AST and parse `RETURN ... GROUP BY key [, key] | ()` before ordering and pagination, accepting `RETURN DISTINCT ... GROUP BY ...` and rejecting `RETURN *` and `RETURN NO BINDINGS` with grouping; verify parser tests cover variable keys, expression keys, a key not returned, the empty key list, and each rejection
- [x] 4.2 Resolve explicit grouping in `SemanticAnalyzer` so it overrides implicit grouping, require every non-aggregate return item to be a key, allow a key that is a direct in-scope variable without returning it, accept expression keys as the labeled extension, and enforce the `GROUP BY ()` aggregate-only rule; verify semantic tests cover explicit keys, implicit fallback, non-key errors, duplicate keys, `DISTINCT` with grouping, and `RETURN *`/no-bindings conflicts
- [x] 4.3 Execute explicit grouping through the existing aggregate projection, including the no-aggregate deduplication path, empty keys, null keys, empty input, `DISTINCT` after grouping, and `GROUP BY ()`; verify executor tests cover one row per group, no rows for empty input, one row for empty keys, null grouping, a `LET`-defined key, and a distinct grouped result
- [x] 4.4 Remove the `GROUP_BY` composition gate and its gated test, add conformance cases for grouping, `DISTINCT`, deduplication, expression keys, empty keys, and the error forms, and flip the `GROUP BY` matrix row and status-board entry to supported with the expression-key deviation recorded; verify `hatch test tests/test_conformance.py tests/test_gql_profile.py tests/engine/query/test_gated.py` passes
- [x] 4.5 Document explicit grouping, the implicit-grouping extension, the expression-key extension, and `DISTINCT` support in the aggregation reference and grammar, add querying-guide examples, and add the changelog bullet; verify `hatch run docs:build` and `hatch test tests/test_docs_examples.py` pass

## 5. FINISH and the RETURN NO BINDINGS extension

- [x] 5.1 Add the `Finish` AST node and the `FINISH` keyword, parse it as a final-only clause that cannot be followed by `RETURN`, `NEXT`, or another clause, reject a statement whose only clause is `FINISH`, and keep `RETURN NO BINDINGS` final-only with its modifier rejections; verify parser tests cover a read `FINISH`, a write `FINISH`, `FINISH` alone, `FINISH` followed by another clause, `FINISH` followed by `NEXT`, and the no-bindings forms
- [x] 5.2 Analyse `FINISH` as a no-result final clause with empty columns, items, grouping, and sorts, and analyse `RETURN NO BINDINGS` as a labeled extension with the same empty projection; verify semantic tests cover a read `FINISH`, a write `FINISH`, a write-only statement, and a no-bindings read and write
- [x] 5.3 Execute `FINISH` as an empty result after applying every preceding operation, project one zero-column `Row` per surviving binding for the extension form, allow `QueryResult.columns == ()`, and preserve the mutation summary; verify executor and result-model tests cover no rows for `FINISH`, row cardinality for the extension, empty input, and a write
- [x] 5.4 Remove the `NO_BINDINGS` composition gate and its gated test, add conformance cases for `FINISH` and the extension, and update the profile matrix with a canonical `FINISH` row and a pygrafito-extension `RETURN NO BINDINGS` row plus the status board; verify `hatch test tests/test_conformance.py tests/test_gql_profile.py tests/engine/query/test_gated.py` passes
- [x] 5.5 Document `FINISH` as the canonical no-result clause and `RETURN NO BINDINGS` as the zero-column extension, update the grammar and the querying guide, and add the changelog bullets; verify `hatch run docs:build` and `hatch test tests/test_docs_examples.py` pass

## 6. NEXT composition with RETURN and YIELD

- [x] 6.1 Add the `Next` and `Yield` AST nodes and the `YIELD` keyword, parse each segment against its own clause list, allow a per-segment `RETURN` or `FINISH`, accept a write-only segment, and reject a leading, trailing, consecutive, or post-`FINISH` `NEXT`, a read segment with no result, a `YIELD` outside `NEXT`, and a `YIELD` after a write-only segment; verify parser tests cover an intermediate `RETURN`, a final `RETURN`, `YIELD` selection and renaming, a write-only segment, and each rejection
- [x] 6.2 Analyse segments so a non-final `RETURN` becomes a projection and scope reset, `YIELD` resets the scope to its selected columns, write-only segments preserve their bindings, and only the final `RETURN`/`FINISH` produces the result; verify semantic tests cover carried bindings, intermediate grouping, `YIELD` unknown/duplicate columns, a write-only segment, and a read segment without a result
- [x] 6.3 Wire segments into the ordered pipeline and explain output, including a later match after an earlier write, an intermediate `RETURN ... GROUP BY`, a no-`YIELD` pass-through, a final `FINISH`, and one transaction; verify executor/plan tests cover read-after-write visibility, mid-query grouping, `YIELD` scope, the final result source, and a budget failure that rolls back an earlier segment
- [x] 6.4 Remove the `NEXT` composition gate and its gated test, add conformance cases for intermediate and final `RETURN`, `YIELD` and no-`YIELD`, mid-query grouping, write-only segments, `FINISH` after `NEXT`, and the placement errors, and flip the `NEXT` matrix row to supported with `YIELD` implemented and no-`YIELD` accepted; verify `hatch test tests/test_conformance.py tests/test_gql_profile.py tests/engine/query/test_gated.py` passes
- [x] 6.5 Document `NEXT`, `YIELD`, segment results, write-only segments, and `FINISH` in the query-language reference and grammar, add querying-guide examples, remove the composition rows from the gated-constructs table, and add the changelog bullet; verify `hatch run docs:build` and `hatch test tests/test_docs_examples.py` pass
- [x] 6.6 Rewrite `examples/tours/03-compose.gql` to use `LET`, an intermediate `RETURN ... GROUP BY`, `NEXT`, `YIELD`, and `FINISH`, update the tour catalog and `docs/guides/examples.md`, and re-aim the tour guard test to the remaining target-only forms; verify `hatch test tests/test_examples.py tests/test_docs_examples.py` passes

## 7. Integration and release readiness

- [x] 7.1 Confirm only the open-bound gate remains in `gated.py` and the gated-construct tests, remove the now-unused composition constants and docs rows, and verify `hatch test tests/engine/query/test_gated.py` and `openspec validate add-gql-composition --strict` pass
- [x] 7.2 Add a composition scenario to `benchmarks/run.py` that exercises `LET`, an intermediate `RETURN ... GROUP BY`, and a `NEXT` chain, run `python -m benchmarks.run --nodes 20000 --relationships 60000`, and record the result and the pipeline-overhead conclusion in `docs/reference/performance.md`; verify the recorded command reproduces the published numbers
- [x] 7.3 Update the README composition bullet and any composition wording in the querying guide index, and verify `hatch test tests/test_readme.py` passes
- [x] 7.4 Review the profile matrix, status board, extension table, and deferred tables as a whole for stale gated wording, and verify `hatch test tests/test_gql_profile.py` and `openspec validate --specs` pass; note any pre-existing `--strict` long-requirement warnings separately
- [x] 7.5 Run the full gate: `hatch check --fix`, `hatch test` with coverage at least 80%, `hatch run docs:build`, and `openspec validate add-gql-composition --strict`; verify all four pass before reporting the change ready

## Workflow follow-up

- Archive `add-gql-composition` after review and before starting the expression-vocabulary change.
- Sync the delta specs into `openspec/specs/graph-query-language/spec.md` and verify the removed diagnostics requirement is gone.
