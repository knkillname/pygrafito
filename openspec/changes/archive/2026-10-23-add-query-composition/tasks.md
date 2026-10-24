# Tasks

## 1. Stage pipeline refactor (no behavior change)

- [x] 1.1 Add `MatchStage`, `OptionalMatchStage`, and `WithStage` analysis types and replace `Analysis.match_clause` with `Analysis.stages` plus `write_clauses`; verify `hatch test tests/engine/query/test_semantic.py` passes and a new test asserts one stage per read clause.
- [x] 1.2 Add `PlanStage` and `Plan.stages`, keep `Plan.operators` as a flattened property, and build one stage per analysed read stage in `PlanBuilder`; verify the existing plan assertions in `hatch test tests/engine/query/test_compiler.py` pass unchanged.
- [x] 1.3 Make `QueryExecutor` run a loop over plan stages starting from one empty binding, with the current match behavior as the only stage implementation; verify `hatch test tests/engine/query` passes without editing existing expectations.
- [x] 1.4 Make `QueryExecutor.explain` collect plan lines stage by stage and keep the single-stage output identical; verify `hatch test tests/test_explain.py tests/engine/query/test_compiler.py` passes.
- [x] 1.5 Prove the refactor changed no observable behavior by running the full query and integration suites before enabling new syntax; verify `hatch test tests/engine/query tests/test_query_integration.py tests/test_integration.py` passes with a clean working tree for test files.

## 2. Multiple patterns and match stages

- [x] 2.1 Change `Match.pattern` to `Match.patterns` and parse comma-separated patterns in one `MATCH` plus repeated `MATCH` clauses; verify `hatch test tests/engine/query/test_parser.py` covers two patterns, three patterns, and two match clauses.
- [x] 2.2 Compile every pattern of a stage into one SQL statement using the shared node and relationship alias maps; verify a compiler test asserts one shared alias for a variable used by two patterns and a cross join for patterns with no shared variable.
- [x] 2.3 Analyse patterns and match clauses in source order with one scope, bind shared variables once, and reject a path variable bound twice or a variable reused with a conflicting kind; verify one semantic test per rule.
- [x] 2.4 Fuse adjacent mandatory match stages, compile each stage once per bound-variable shape, and execute it per input row with bound node and relationship ids as parameters; verify executor tests for a chained join, a cartesian product, and a later match with no match for one input row.
- [x] 2.5 Add the five multiple-pattern conformance scenarios to `tests/engine/query/test_conformance.py` using TRON fixtures; verify `hatch test tests/engine/query/test_conformance.py` passes.
- [x] 2.6 Document multiple patterns and chained `MATCH` in `docs/query-language.md`, add a runnable README snippet, and add the `[Unreleased]` changelog bullet; verify `hatch test tests/test_readme.py` executes the snippet and the docs match the parser tests.

## 3. OPTIONAL MATCH

- [x] 3.1 Parse `OPTIONAL MATCH` as an optional match stage, reject `OPTIONAL` without `MATCH`, and keep its `WHERE` attached to the stage; verify parser tests for an optional stage, an optional stage with `WHERE`, and the rejected form.
- [x] 3.2 Analyse the variables a stage introduces, record them on `OptionalMatchStage`, and give them kinds for later stages; verify semantic tests accept a later `a.designation` on a bound variable and reject a reference to a variable the optional stage never introduced.
- [x] 3.3 Implement the left join: run the stage per input row, keep the input row with nulls for introduced variables when no match exists, and produce one row per match otherwise; verify executor tests for zero, one, and two matches.
- [x] 3.4 Prove null propagation: property access on an optional null yields null, a downstream `WHERE` excludes null rows, and a later mandatory `MATCH` drops them; verify one executor test per case and add the six optional conformance scenarios to `test_conformance.py`.
- [x] 3.5 Document `OPTIONAL MATCH` scope and null rules in `docs/query-language.md`, add a runnable README snippet, and add the changelog bullet; verify `hatch test tests/test_readme.py` passes.

## 4. WITH stages

- [x] 4.1 Add a `With` clause type and parse `WITH [DISTINCT] items [WHERE ...] [ORDER BY ...] [SKIP ...] [LIMIT ...]`, enforcing that it is not the final clause and that read stages may follow it; verify parser tests for each accepted form and for `WITH` last, `WITH` after a write, and `WITH *`.
- [x] 4.2 Analyse `WITH` as a scope boundary: project only its output names with their kinds, require an alias for a non-variable item, reject duplicate names, and reject an unbound reference in a later stage; verify one semantic test per rule.
- [x] 4.3 Implement `WITH` as a row transformer that reuses the existing project, aggregate, distinct, order, and pagination helpers and returns a new binding list keyed by output names; verify executor tests show a projected variable surviving and a non-projected variable disappearing.
- [x] 4.4 Cover the aggregation boundary: implicit grouping, `WHERE` on an aggregate alias, `ORDER BY` an aggregate alias, `DISTINCT`, and `SKIP`/`LIMIT` over grouped rows; verify the four WITH conformance scenarios and the aggregate tests in `test_executor.py`.
- [x] 4.5 Confirm `MATCH` after `WITH` joins against the projected rows and `WITH` before a write shapes mutation input; verify executor tests for both and a conformance test for a three-stage statement.
- [x] 4.6 Document `WITH` scope, aliasing, aggregation, and pagination in `docs/query-language.md`, add a runnable README snippet, and add the changelog bullet; verify `hatch test tests/test_readme.py` passes.

## 5. Variable-length relationships

- [x] 5.1 Add `min_hops` and `max_hops` to `RelationshipPattern` and parse `*n`, `*n..m`, `*0..m`, and the anonymous forms; verify lexer and parser tests cover every form, a malformed bound, and a bare `*` reaching analysis.
- [x] 5.2 Validate bounds in the analyzer (non-negative, lower no greater than upper, explicit upper bound required) and add `VariableKind.RELATIONSHIP_LIST`; verify semantic tests for each reject and for projecting the list variable.
- [x] 5.3 Add start-node selection for a pattern inside the pattern engine, reusing indexed label and property predicates; verify a test shows a selective start pattern does not read every node.
- [x] 5.4 Implement the depth-first pattern engine over a `TraversalCapture` region: per-position direction, types, property map, node labels and properties, `min_hops`/`max_hops` pruning, and one used-relationship set per path; verify unit tests with diamond, directed cycle, parallel relationship, and self-loop fixtures in `tests/engine/query/test_pattern_engine.py`.
- [x] 5.5 Route a match stage containing any quantified relationship to the pattern engine and keep stages without one on the SQL path; verify a parity test evaluates the same fixed pattern through both paths and returns identical rows.
- [x] 5.6 Cover the variable-length semantics end to end: exact length, bounded range, zero hop, per-hop type/direction/property filters, relationship-unique trails with repeating nodes, relationship list projection with `size(r)`, path order, and rejected `type(r)` on a list; verify the six added conformance scenarios.
- [x] 5.7 Prove uniqueness across a path that mixes quantified and fixed positions, including a cycle that would reuse a relationship; verify the pattern-engine test fails without the used-set check and passes with it.
- [x] 5.8 Add a bounded quantified-match scenario to `benchmarks/run.py`, record the command and numbers in `docs/performance.md`, and verify `hatch test tests/test_benchmarks.py` still runs the harness.
- [x] 5.9 Document quantifier syntax, bounds, relationship lists, path order, and trail semantics in `docs/query-language.md`, add a runnable README snippet, and add the changelog bullet; verify `hatch test tests/test_readme.py` passes.

## 6. Diagnostics and error surface

- [x] 6.1 Make `Graph.explain` report every stage in order, including the start-node plan plus a synthetic expansion line for a stage run by the pattern engine; verify `hatch test tests/test_explain.py` covers a two-stage statement and a quantified statement.
- [x] 6.2 Classify the new failures: syntax errors for malformed quantifiers and clause order, semantic errors for unbounded bounds, list misuse, missing aliases, duplicate path variables, and unbound later references; verify `hatch test tests/engine/query/test_errors.py tests/engine/query/test_semantic.py` asserts the class and position for each.
- [x] 6.3 Update the tests that currently assert these constructs are rejected so they assert the new behavior, keeping genuine rejections (`UNWIND`, subqueries, `CASE`, map literals, `MERGE`, map assignment, index access, `WITH *`); verify `hatch test tests/engine/query/test_parser.py tests/engine/query/test_semantic.py` passes.
- [x] 6.4 Rewrite the grammar summary and unsupported-constructs list in `docs/query-language.md` so every accepted form is documented and every remaining rejection is named; verify every parser acceptance test has a matching grammar form and `hatch test tests/test_readme.py` passes.

## 7. Integration checks

- [x] 7.1 Add an end-to-end test that creates a graph with multiple patterns, an `OPTIONAL MATCH`, a `WITH` aggregation, and a variable-length path, then reopens the file and returns the same rows; verify with `tmp_path` in `tests/test_query_integration.py`.
- [x] 7.2 Run the full quality gate and confirm coverage stays at or above 80 percent; verify `hatch check --fix` and `hatch test` both pass.
- [x] 7.3 Review the final `docs/query-language.md`, `README.md`, and `CHANGELOG.md` against the delta spec and confirm no deferred construct appears as supported; verify every ADDED and MODIFIED requirement has a scenario exercised by a test.

## Workflow follow-up

- Archive the change after the project review requirements are satisfied.
- Verify the archived result with `openspec validate --specs --strict`.
