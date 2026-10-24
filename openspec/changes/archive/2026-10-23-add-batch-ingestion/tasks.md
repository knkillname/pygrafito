# Tasks

## 1. Clause model and parser

- [x] 1.1 Add frozen, slotted `Unwind(expression, variable)` and `Merge(pattern, on_create, on_match)` nodes to `ast.py` and extend the `Clause` and `WriteClause` unions; verify `hatch test tests/engine/query/test_ast.py` covers frozen and slotted behavior for both nodes.
- [x] 1.2 Add `ON` to `Keyword`, remove `UNWIND` and `MERGE` from `Parser.UNSUPPORTED_CLAUSES`, and keep `CASE` rejected; verify `hatch test tests/engine/query/test_lexer.py tests/engine/query/test_parser.py` covers case-insensitive spellings and the remaining rejection.
- [x] 1.3 Parse `UNWIND <expression> AS <identifier>`, reject a missing `AS` or identifier, and reject an `UNWIND` that follows a write clause or `RETURN`; verify parser tests for each accepted position and each rejection with a line and column.
- [x] 1.4 Parse `MERGE <path pattern>` with an optional `ON CREATE SET` followed by an optional `ON MATCH SET`, reusing `_set_clause`; reject duplicate conditional clauses, reversed order, and multiple comma-separated patterns; verify one parser test per form.
- [x] 1.5 Update `_validate_clause_shape` so a read statement needs a row source (`MATCH` or `UNWIND`) plus `RETURN`, and `MERGE` counts as a write clause; verify `UNWIND [1] AS x RETURN x` and `MERGE (n:Program)` are accepted while `RETURN 1` is rejected.
- [x] 1.6 Extend the clause guards so `UNWIND` may precede or follow `MATCH` and `WITH` but never follows a write clause, and `MERGE` follows every read stage; verify parser tests for `UNWIND` after `CREATE` and `MERGE` before `MATCH`.
- [x] 1.7 Update the grammar summary and clause-order section of `docs/query-language.md` for `UNWIND`, `MERGE`, and the conditional clauses; verify every accepted form in the parser tests appears in the grammar and every rejection is named.

## 2. Semantic analysis and scope

- [x] 2.1 Add `UnwindStage` to `ReadStage` and allow `Merge` in `Analysis.write_clauses`; verify `hatch test tests/engine/query/test_semantic.py` asserts stage order and write classification.
- [x] 2.2 Validate `UNWIND`: reject a variable already in scope, reject a statically non-list literal, accept parameters and list-valued expressions, and register the variable as a scalar; verify one semantic test per rule.
- [x] 2.3 Validate `MERGE` pattern restrictions: one path, no path variable, no quantified relationship, exactly one relationship type, outgoing direction only, no bound relationship variable, and unbound node endpoints allowed; verify one semantic test per rejection.
- [x] 2.4 Bind the node and relationship variables introduced by `MERGE`, allow bound node variables as anchors, and reject a bound node used with labels or properties that would change it; verify tests for an anchor, a newly bound node, and a conflicting reuse.
- [x] 2.5 Validate `ON CREATE SET` and `ON MATCH SET` with the existing `SET` rules, including label targets and null removal; verify tests for an unbound target, a label on a relationship, and a null assignment.
- [x] 2.6 Validate pattern property expressions against a scope snapshot taken before the pattern, reject aggregates and forward references, and keep unbound references rejected; verify tests for `MATCH`, `CREATE`, and `MERGE` property maps.
- [x] 2.7 Keep `Analysis.is_write`, `columns`, and `variable_kinds` correct for the new clauses, and return empty columns for a `MERGE` without `RETURN`; verify prepared-column and analysis tests.
- [x] 2.8 Document `UNWIND` scope, `MERGE` restrictions, and conditional-update rules in `docs/query-language.md`; verify every rule has a matching semantic test and the reference names each rejection.

## 3. Dynamic pattern values

- [x] 3.1 Add a `PatternValueResolver` that evaluates one expression against a binding, the parameters, and the existing scalar functions; verify unit tests for literals, parameters, variables, property access, list values, and null.
- [x] 3.2 Thread the resolver through `Compiler.compile` and `_add_property_predicates` so `MATCH (n:Program {designation: row.name})` compiles with the row's value; verify a compiler test asserts the value appears as a SQL argument and an indexed plan is still chosen.
- [x] 3.3 Thread the resolver through `PatternEngine._properties_match` so quantified and fixed patterns evaluate node and relationship maps against the row; verify `hatch test tests/engine/query/test_pattern_engine.py` covers a dynamic node map and a dynamic relationship map.
- [x] 3.4 Make `Graph.explain` use a placeholder resolver for dynamic values and keep the plan readable; verify `hatch test tests/test_explain.py` covers a dynamic pattern without raising and reports an index or scan line.
- [x] 3.5 Implement the clause-specific null rules: `MATCH` matches nothing, `CREATE` omits the key, and `MERGE` raises at execution time; verify one test per clause, with the `MERGE` case added alongside its executor work.
- [x] 3.6 Update the conformance suite and the tests that asserted variable-valued pattern maps are rejected; verify every remaining rejection (`CASE`, map literal, `CALL`, index access) is unchanged and the new dynamic forms pass.
- [x] 3.7 Document pattern property expressions, their scope, and the per-clause null rules in `docs/query-language.md`; verify each documented form has a passing test and the reference matches the semantic rules.

## 4. UNWIND execution and planning

- [x] 4.1 Add `PlanOperator.UNWIND` and build it from `UnwindStage`; verify plan tests assert the operator order for `UNWIND` before and after `MATCH`.
- [x] 4.2 Implement `_run_unwind_stage` with null and empty-list handling, list expansion in order, explicit string rejection, and `QueryExecutionError` for other runtime values; verify executor tests for each case.
- [x] 4.3 Route `UnwindStage` through `_run_stage` and `_execute`, including a chain from `UNWIND` into `MATCH` and from `MATCH` into `UNWIND`; verify executor tests for both chains and for zero output rows.
- [x] 4.4 Report an `UNWIND` line from `QueryExecutor.explain` and keep write operators out of the plan as before; verify `hatch test tests/test_explain.py`.
- [x] 4.5 Add conformance scenarios for a parameter list, a literal, a list of mappings, an empty list, null, a static non-list, a runtime non-list, a redefined variable, and a misplaced clause; verify `hatch test tests/engine/query/test_conformance.py`.
- [x] 4.6 Document `UNWIND` in `docs/query-language.md` with a runnable example and add a README snippet; verify `hatch test tests/test_readme.py` executes the snippet.
- [x] 4.7 Prove row expansion is linear: unwind 10,000 generated values and assert the row count and ordering; verify the test completes without a timeout and is part of the normal suite.

## 5. MERGE execution and conditional updates

- [x] 5.1 Extract a `PatternCreator` from `MutationExecutor._create` that threads one working binding through a pattern, reuses bound and previously created variables, and supports repeated variables for a self-loop; verify unit tests for a bound anchor, a new endpoint, a repeated variable, and a relationship with properties.
- [x] 5.2 Implement per-row `MERGE`: match the whole pattern with `_match_rows`, emit one row per match, and call `PatternCreator` only when there is no match; verify tests for a match, a creation, several matches, and no partial reuse.
- [x] 5.3 Prove sequential visibility: two `UNWIND` rows with the same merge key create one node and the second row matches it, and a failed later row rolls back the statement; verify both tests against `:memory:` and a reopened file.
- [x] 5.4 Refactor `_set` into a single-row helper and a batch loop, then apply `ON CREATE SET` and `ON MATCH SET` immediately after each match or creation; verify tests for created-only, matched-only, mixed rows, null removal, and a row-derived value.
- [x] 5.5 Populate the mutation summary from `MERGE` creations and conditional assignments, and keep `RETURN` bindings refreshed after the conditional update; verify the summary counts and projected values in one executor test.
- [x] 5.6 Implement the runtime errors: a null value in a merge property map, a non-node anchor, and a relationship creation failure; verify the error class and that nothing commits.
- [x] 5.7 Add conformance and TRON-themed fixtures for `MERGE` covering a diamond, parallel relationships, a self-loop, duplicate input rows, and a relationship between bound nodes; verify `hatch test tests/engine/query/test_conformance.py`.
- [x] 5.8 Document `MERGE`, whole-pattern creation, sequential visibility, and conditional updates in `docs/query-language.md` with a runnable README example; verify `hatch test tests/test_readme.py`.
- [x] 5.9 Add a 10,000-row `UNWIND` + `MERGE` benchmark to `benchmarks/run.py`, record the command and result in `docs/performance.md`, and note whether the single-node fast path is needed; verify `hatch test tests/test_benchmarks.py` still passes.

## 6. Import engine

- [x] 6.1 Add `ImportSummary` and an `ImportRunner` that validates, batches, executes, and aggregates counters; verify unit tests for an empty input, one batch, several batches, a read-only statement rejection, and a statement that omits `$rows`.
- [x] 6.2 Add read-only `PreparedQuery.is_write` and `PreparedQuery.parameters`, populated from `Analysis`; verify a prepared read, a prepared write, and a statement with parameters.
- [x] 6.3 Implement `CsvReader` with a required header, duplicate-header rejection, field-count validation, blank-line handling, and quoted/embedded-newline support; verify unit tests for each case.
- [x] 6.4 Implement `JsonLinesReader` with blank-line skipping, object-only rows, line-numbered errors, and `NaN`/infinity rejection; verify unit tests for each case.
- [x] 6.5 Implement format selection from the explicit argument or `.csv`, `.jsonl`, and `.ndjson`, with a validation error for unknown formats before any read; verify one test per path.
- [x] 6.6 Implement positive batch-size validation, the 1000-row default, per-batch transactions, and the atomic whole-import transaction; verify tests for default batching, atomic rollback, non-atomic partial commit, and invalid sizes.
- [x] 6.7 Add row-level failure context with the source, one-based row, and batch number while preserving the original error type; verify tests for a file failure, an in-memory failure, and the preserved exception class.
- [x] 6.8 Add `Graph.import_rows` and `Graph.import_file`, export `ImportSummary`, and guard a read-only or closed handle before reading; verify `hatch test tests/test_package.py` and integration tests for both entry points.
- [x] 6.9 Cover imports end to end with TRON-themed CSV and JSONL fixtures, typed values, mapping rows, duplicate merge keys, and a reopen; verify `hatch test tests/engine/query` and a new import integration test.
- [x] 6.10 Document the import API, formats, statement contract, batching, atomicity, and failure reporting in `docs/import.md`; verify every documented snippet and option is exercised by a test.
- [x] 6.11 Add a 10,000-row CSV import to the benchmark harness and record the command and numbers in `docs/performance.md`; verify `hatch test tests/test_benchmarks.py` passes.

## 7. Shell `.import`

- [x] 7.1 Add `import` to `Commands.DESCRIPTIONS` and parse its argument with `shlex.split`, requiring `PATH` and `--statement` and accepting `--format`, `--batch`, and `--atomic`; verify tests for quoted statements, each option, and unknown options.
- [x] 7.2 Execute `Graph.import_file` and print a summary line with rows, batches, created and deleted elements, and property and label changes; verify a shell test asserts the output and the resulting graph.
- [x] 7.3 Refuse `.import` during an active transaction and surface `ReadOnlyError` in a read-only session while leaving the session usable; verify both tests.
- [x] 7.4 Reject a missing statement and a non-positive batch size with usage text and no writes; verify the error message and an unchanged graph.
- [x] 7.5 Prove `.import` works from `-f` scripts and that a later failure leaves earlier batches committed unless `--atomic` is used; verify both script tests.
- [x] 7.6 Document `.import` in `docs/cli.md`, add it to the command table, and add a runnable README example; verify `hatch test tests/test_readme.py` and `.help import`.

## 8. Changelog, integration, and quality gates

- [x] 8.1 Add the `[Unreleased]` changelog entry covering `UNWIND`, `MERGE`, conditional updates, dynamic pattern values, the import API, and `.import`; verify the entry uses Keep a Changelog categories and omits empty ones.
- [x] 8.2 Run an end-to-end scenario that imports a JSONL file with `MERGE`, queries the result, adds a conditional update, and reopens the file; verify the reopened graph returns the same values.
- [x] 8.3 Confirm the unsupported-constructs list in `docs/query-language.md` no longer names `UNWIND` or `MERGE` and still names every remaining rejection; verify the docs match the parser tests.
- [x] 8.4 Confirm every new fixture follows the TRON naming convention and no test, spec, or doc references another graph product; verify `hatch test tests/test_naming_convention.py`.
- [x] 8.5 Run `hatch check --fix` and `hatch test` and confirm both pass, coverage is at least 80 percent, and the README examples all execute.
- [x] 8.6 Review the delta specs against the implementation and confirm every ADDED and MODIFIED requirement has at least one passing scenario test.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- When archiving, confirm the durable `graph-query-language` purpose still describes the expanded dialect and the new `graph-import` purpose is carried into the main spec.
