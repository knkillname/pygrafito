# Tasks

## 1. Query budget foundation

- [x] 1.1 Add the frozen `QueryBudget` value object to `model.py` with `max_expansions`, `max_rows`, and `max_seconds`, write the numpydoc docstring, and export it from `__init__.py`; verify unit tests cover the documented defaults, `None` as unlimited, and rejection of negative values
- [x] 1.2 Add `QueryBudgetExceededError` as a `QueryExecutionError` subclass carrying `counter` and `limit`, and export it; verify tests assert the attributes and the message names both the counter and the limit
- [x] 1.3 Let `Graph.open` set a graph default budget and `Graph.query` and `PreparedQuery.execute` accept a per-execution override, leaving the default untouched; verify tests show override precedence across graph, query, and prepared execution
- [x] 1.4 Add a per-execution budget tracker to `QueryExecutor` that counts relationship expansions and stage-emitted rows and checks the optional clock at stage boundaries and every 1,024 expansions; verify deterministic tests trigger each counter with small budgets and that no rows are returned
- [x] 1.5 Make a budget exhaustion inside a write roll the statement back, and inside an active transaction undo only that statement's mutations; verify tests assert the data is unchanged, the handle remains usable, and the caller's transaction continues
- [x] 1.6 Document `QueryBudget`, the defaults, the error, and the override points in the API reference and the querying guide; verify `hatch run docs:build` passes with warnings treated as errors

## 2. Path mode syntax and static resolution

- [x] 2.1 Add the internal `PathMode` enum and the per-path and per-clause mode fields to `ast.py`; verify parser tests read `MATCH WALK`, `MATCH TRAIL`, `MATCH SIMPLE`, and `MATCH ACYCLIC` without changing execution
- [x] 2.2 Parse an optional clause mode after `MATCH` and `OPTIONAL MATCH` and an optional per-path mode before each comma-separated path; verify grammar tests cover both positions, the bare `(a)-(b)` form, and a second path overriding the clause mode
- [x] 2.3 Resolve each path's mode in `SemanticAnalyzer` with the order explicit per-path, explicit clause, legacy quantifier implies `TRAIL`, otherwise `WALK`, and raise the mixing error; verify unit tests cover each step and the error
- [x] 2.4 Carry the resolved mode from analysis into the plan so the matcher never re-derives it; verify an explain or plan-level test shows the resolved mode per path
- [x] 2.5 Document the explicit mode grammar and the resolution order in the query-language reference; verify `hatch run docs:build` passes

## 3. Mode-aware matching

- [x] 3.1 Rework `WalkState` memory per mode: none for `WALK`, the relationship set for `TRAIL`, a node set for `ACYCLIC`, and a node set plus a `closed` flag for `SIMPLE`; verify pattern tests distinguish `SIMPLE` from `ACYCLIC` on a closed cycle and a self-loop
- [x] 3.2 Enforce the mode in the quantified walker for fixed and quantified segments; verify one test per mode on the diamond, directed-cycle, parallel-relationship, and self-loop fixtures
- [x] 3.3 Add mode predicates to the fixed-length SQL compiler: relationship-id inequality for `TRAIL`, node inequality for `ACYCLIC`, and node inequality except between the first and last node for `SIMPLE`; verify indexed tests for each mode and a repeated-self-loop test that `TRAIL` rejects and `WALK` accepts
- [x] 3.4 Share one mode/edge predicate helper between the compiler and the in-memory matcher; verify a parity test forces each execution path and compares results for the same fixture and query
- [x] 3.5 Document the semantics of `WALK`, `TRAIL`, `SIMPLE`, and `ACYCLIC` in the reference and the querying guide, including the self-loop and closed-path examples; verify `hatch run docs:build` passes

## 4. Canonical quantifier and deferred open bounds

- [x] 4.1 Parse the canonical closed forms `{n}`, `{m,n}`, and `{,n}` into the existing quantifier fields; verify parser tests for each form and for `{n}` equaling a fixed length
- [x] 4.2 Validate canonical bounds with the same non-negative and lower-not-greater rules, and keep `{n,m}` out of the legacy-quantifier path; verify semantic tests reject invalid bounds and confirm the mode comes from the path-mode rule
- [x] 4.3 Reject `*`, `+`, `*n..`, and `{m,}` with a deferred-construct error naming `add-gql-unbounded-traversal`, and update `gated.py` so the closed and direction gates are removed; verify tests cover every rejected form and the error text
- [x] 4.4 Document the closed canonical forms and the deferred open bounds in the query-language reference and the profile; verify `hatch run docs:build` passes

## 5. Remaining edge directions

- [x] 5.1 Add the internal `EdgeDirection` enum with the seven direction values and parse `<~`, `~>`, and `<->`, including the bare forms without a relationship detail; verify parser tests for each spelling
- [x] 5.2 Map `EdgeDirection` to storage traversal in the in-memory matcher; verify the direction matrix tests: directed forward, directed backward, either directed, undirected only, incoming-or-undirected, outgoing-or-undirected, and any
- [x] 5.3 Map `EdgeDirection` to the compiler's SQL predicates; verify indexed parity tests for every form, including that `<->` rejects an undirected relationship
- [x] 5.4 Document the seven direction forms with one example each in the query-language reference; verify `hatch run docs:build` passes

## 6. Flip the default and align the profile

- [x] 6.1 Change the canonical default from the implicit trail to `WALK` while legacy quantifiers keep `TRAIL`; verify the suite passes with trail-dependent tests updated to name `TRAIL` or keep a legacy quantifier
- [x] 6.2 Add the conformance fixtures and cases the new matrix rows require: each path mode, each direction form, each budget counter, the canonical quantifier forms, and a repeated self-loop under the new default; verify `hatch test tests/test_conformance.py tests/test_gql_profile.py` passes
- [x] 6.3 Flip the `WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC`, `{n,m}`, and edge-direction rows to supported, update the status wording and the deferred table, and record the open-bound deferral; verify `tests/test_gql_profile.py` enforces the matrix and `openspec validate --strict` passes
- [x] 6.4 Update `examples/tours/04-paths.gql` and the tour catalog so the canonical forms are shown as implemented and no supported-only tour claims a pending migration; verify `hatch test tests/test_examples.py tests/test_docs_examples.py` passes
- [x] 6.5 Update `README.md` and the querying guide with the `WALK` default and the `MATCH TRAIL` migration, and confirm every fenced Python block still runs; verify `hatch test tests/test_readme.py`
- [x] 6.6 Run the benchmark with and without the new mode predicates, record the defaults and the measured cost in the performance reference, and retune the budget defaults if the data calls for it; verify the recorded command reproduces the published numbers
- [x] 6.7 Add the `CHANGELOG.md` entry under `[Unreleased]` with a **Changed** entry for the breaking default and **Added** entries for the budget, modes, quantifier, and directions; verify the file lists every public addition
- [x] 6.8 Run `hatch check --fix`, `hatch test` with the coverage gate, and `hatch run docs:build`; verify all three pass before archive

## Workflow follow-up

- Review the change artifacts and obtain approval before implementation.
- Archive the change after the implementation and release checks pass.
