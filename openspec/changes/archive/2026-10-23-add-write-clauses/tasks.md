# Tasks

## 1. Clause model and parser

- [x] 1.1 Replace the flat `Statement` with an ordered `clauses: tuple[Clause, ...]` and add frozen clause types for `Match`, `Create`, `Set`, `Remove`, `Delete`, and `Return`; verify `hatch test tests/engine/query/test_ast.py` passes with the new nodes and every clause type is frozen and slotted.
- [x] 1.2 Confirm the lexer tokenizes `CREATE`, `SET`, `REMOVE`, `DELETE`, `DETACH`, and `MERGE` case-insensitively as keywords rather than identifiers; verify `hatch test tests/engine/query/test_lexer.py` covers each spelling.
- [x] 1.3 Parse a clause sequence with `MATCH` and `RETURN` optional: accept `CREATE (n:Program)`, `MATCH (n:Program) SET n.cycles = 1`, and `MATCH (a)-[:ALLIES_WITH]->(b) CREATE (a)-[r:TRUSTS]->(b)`; verify parser tests cover each accepted form and the parsed clause order.
- [x] 1.4 Implement the rejection rules: `RETURN` must be last, at most one `MATCH` and one `RETURN`, a write clause may not precede `MATCH`, and a read statement still requires both; verify each case raises `QuerySyntaxError` with line and column in `tests/engine/query/test_parser.py`.
- [x] 1.5 Parse `DETACH DELETE v` as one `Delete` clause with `detach=True`, and parse `DELETE a, r, b` target lists; verify parser tests distinguish the two forms by the clause flag.
- [x] 1.6 Parse `CREATE` relationship patterns with bound endpoints, labels, and property maps whose values are literals or parameters; verify tests reject a variable-valued property map in `CREATE` with a semantic error.
- [x] 1.7 Replace the read-only grammar section in `docs/query-language.md` with the clause sequence, optional `MATCH` and `RETURN`, and the accepted order; verify every accepted form in the parser tests appears in the reference.

## 2. Semantic analysis and scope

- [x] 2.1 Extend `Analysis` with `is_write` and allow an empty `columns` tuple when the statement has no `RETURN`; verify `hatch test tests/engine/query/test_semantic.py` covers a read statement, a write with `RETURN`, and a write without it.
- [x] 2.2 Walk clauses in order with one scope map from variable to kind, binding node and relationship variables in `MATCH` and `CREATE`; verify tests cover a variable bound by `CREATE` and used in a later `SET` and in `RETURN`.
- [x] 2.3 Validate write targets: `SET` and `REMOVE` require a bound node or relationship, labels may only be added to nodes, and `DELETE` requires a bound node or relationship value; verify one semantic error test per rule.
- [x] 2.4 Require both `CREATE` relationship endpoints to be already bound and reject a relationship pattern that invents an endpoint; verify tests for one bound and one unbound endpoint.
- [x] 2.5 Keep aggregate, ordering, projection, and duplicate-column validation working when `RETURN` follows a write clause; verify tests for `RETURN` after `CREATE` and for an illegal aggregate mix.
- [x] 2.6 Confirm read statements analyse to the same `is_write == False` and columns as before; verify the existing semantic and conformance suites pass unchanged.

## 3. Execution pipeline and mutation stages

- [x] 3.1 Add `CREATE`, `SET`, `REMOVE`, and `DELETE` plan operators and build them in source order from the clause sequence; verify `hatch test tests/engine/query/test_compiler.py` and a plan test cover read and write pipelines.
- [x] 3.2 Add a mutation-stage class that converts bindings into deduplicated operations keyed by entity id, with last-row-wins for properties and set union for labels; verify unit tests cover repeated ids and conflicting values.
- [x] 3.3 Implement `SET` from an expression, including null removal and label addition; verify executor tests cover `n.cycles = n.cycles + 1`, `n.cycles = null`, and `SET n:SystemMonitor`.
- [x] 3.4 Implement `REMOVE` for properties and labels, treating an absent key as a no-op; verify executor tests cover removal, absent keys, and label removal.
- [x] 3.5 Implement `CREATE` per input row, appending one binding per created element so `RETURN` can project created variables; verify tests cover standalone creation, creation from three match rows, and relationship creation between bound nodes.
- [x] 3.6 Implement `DELETE` and `DETACH DELETE` with relationship targets applied before node targets and each id deleted once; verify tests cover a deleted relationship, a disconnected node, a protected connected node, and detach.
- [x] 3.7 Refresh mutated bindings after each `SET` and `REMOVE` while keeping pre-deletion snapshots after `DELETE`; verify tests prove `RETURN` observes a new value and returns a deleted element's snapshot.
- [x] 3.8 Raise a query execution error when a later write clause targets an element deleted earlier in the same statement; verify the test asserts the error and that nothing commits.
- [x] 3.9 Exercise cardinality with TRON fixtures covering a diamond, a directed cycle, parallel relationships, and a self-loop; verify each fixture's write statement applies its mutation once per entity.

## 4. Transaction boundary, atomicity, and error mapping

- [x] 4.1 Route a standalone write statement through `BEGIN IMMEDIATE` and commit on success while leaving the read path's deferred transaction unchanged; verify tests on `tmp_path` show the write persists after reopen.
- [x] 4.2 Roll back every mutation when any clause fails and leave no transaction open; verify a test that fails after a `CREATE` and then opens a new transaction on the same handle.
- [x] 4.3 Execute write statements through `Transaction.query` inside the active transaction without opening another; verify a test shows uncommitted visibility and that rollback removes the created node.
- [x] 4.4 Wrap `ValidationError`, `NotFoundError`, `ConnectedNodeError`, and `sqlite3.Error` raised during a write as `QueryExecutionError` without double-wrapping; verify one test per mapping plus a raw-SQLite failure test.
- [x] 4.5 Enforce stored value rules for assigned values: accept parameters with scalars and homogeneous lists, reject mappings, nested lists, NaN, and infinity, and remove a property on null; verify one test per accepted and rejected shape with nothing committed on rejection.
- [x] 4.6 Keep the active-transaction guard and the closed-handle guard effective for write statements; verify `Graph.query("CREATE ...")` inside an explicit transaction raises `TransactionError` and that a closed handle raises `GraphClosedError`.

## 5. Result model

- [x] 5.1 Add frozen `MutationSummary` counters and an optional `QueryResult.summary` defaulting to zero counts, and export `MutationSummary` from the package root; verify `hatch test tests/engine/query/test_executor.py` and `tests/test_package.py` cover the new export.
- [x] 5.2 Populate the counters from the applied operations after deduplication, not from the number of rows; verify a test where several rows touch one entity reports one change.
- [x] 5.3 Return an empty result (no columns, no rows) for a write without `RETURN`, and expose empty prepared columns for the same statement; verify `hatch test tests/engine/query/test_api.py` covers both.
- [x] 5.4 Prove result immutability still holds around writes: a row projected before a later write keeps its snapshot values; verify the existing immutability test is extended with a write between execution and inspection.

## 6. Public surface, documentation, and changelog

- [x] 6.1 Remove the read-only rejection from `Graph.query` and `Transaction.query` and update their docstrings to describe statement execution; verify `hatch test tests/test_query_integration.py` covers a read and a write through both entry points.
- [x] 6.2 Add runnable README examples for `CREATE`, `SET`, `DELETE`, and write-with-`RETURN`; verify `hatch test tests/test_readme.py` executes every new snippet.
- [x] 6.3 Complete `docs/query-language.md`: clause reference, mutation cardinality and deduplication, result summary, transaction boundary, and write error mapping, and drop the read-only promises and the write clauses from the unsupported list; verify every ADDED and MODIFIED requirement maps to a section and every deferred construct is still listed.
- [x] 6.4 Add the `[Unreleased]` changelog entry covering the write clauses, the single statement surface, the summary, and the read-only rejection removal; verify the entry uses Keep a Changelog categories and omits empty ones.

## 7. Integration checks

- [x] 7.1 Add write statements to the dialect conformance suite, including a mixed match-write-return statement and a deduplication case; verify the suite passes and every row is asserted.
- [x] 7.2 Run an end-to-end test that builds a graph with `CREATE`, mutates it with `SET`, deletes with `DETACH DELETE`, queries the result, and reopens the file; verify the reopened graph reflects the committed state.
- [x] 7.3 Confirm new fixtures follow the TRON naming convention and reference no other graph product; verify `hatch test tests/test_naming_convention.py`.
- [x] 7.4 Run `hatch check --fix` and `hatch test` and confirm their exit status, a green suite, and coverage at or above 80%.

## Workflow follow-up

- Correct the durable `graph-query-language` capability `Purpose` line, which still describes the dialect as read-only, when the change is archived or synced.
- Archive the change after the project's review requirements are satisfied, then plan `add-merge` as the next change in the release.
