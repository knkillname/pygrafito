# Tasks

## 1. Query package foundation and errors

- [x] 1.1 Create `src/pygrafito/engine/query/` with the package `__init__.py` and empty modules for tokens, lexer, AST, parser, semantic analysis, plan, compiler, values, executor, prepared queries, and results; verify the package imports with `hatch run python -c "import pygrafito.engine.query"` and a package smoke test.
- [x] 1.2 Add `QueryError`, `QuerySyntaxError`, `QuerySemanticError`, and `QueryExecutionError` to `src/pygrafito/model.py` with optional line and column attributes, export them from `pygrafito.model` and `pygrafito`, and verify the hierarchy with `hatch test tests/engine/query/test_errors.py`.

## 2. Lexer and tokens

- [x] 2.1 Implement token kinds and source spans for keywords, identifiers, backtick-quoted identifiers, strings, integers, floats, parameters, operators, punctuation, comments, and end of input; verify token construction and span tests pass in `tests/engine/query/test_lexer.py`.
- [x] 2.2 Implement the lexer with case-insensitive keywords, case-sensitive identifiers, string escapes, numeric literals, `$name` parameters, backtick escaping, `//` and `/* */` comments, and line/column tracking; verify every token class is covered.
- [x] 2.3 Add lexer error tests for unterminated strings, unterminated backticks, invalid characters, and malformed numbers; verify each error reports the expected line and column.
- [x] 2.4 Recognize unsupported clause keywords (`OPTIONAL`, `WITH`, `UNWIND`, `CREATE`, `MERGE`, `SET`, `REMOVE`, `DELETE`, `DETACH`, `CASE`) as distinct tokens; verify the lexer tests confirm they are tokenized rather than treated as identifiers.

## 3. AST and parser

- [x] 3.1 Define frozen, slotted AST nodes for the statement, path pattern, node pattern, relationship pattern, property map, `WHERE`, `RETURN` items, `ORDER BY`, `SKIP`, `LIMIT`, and every expression form; verify immutability and construction tests pass in `tests/engine/query/test_ast.py`.
- [x] 3.2 Implement recursive-descent parsing for `MATCH`, one path pattern with multiple node segments, path variables, labels, relationship type alternatives, directions, property maps, and anonymous elements; verify accepted and rejected pattern tests pass.
- [x] 3.3 Implement the Pratt expression parser for literals, variables, parameters, property access, function calls, list literals, unary and binary arithmetic, comparisons, `IN`, `IS NULL`, `IS NOT NULL`, string predicates, `AND`, `OR`, `NOT`, and parentheses; verify precedence and grouping tests pass.
- [x] 3.4 Implement parsing for `WHERE`, `RETURN`, `DISTINCT`, aliases, `ORDER BY` with `ASC`/`DESC`, `SKIP`, `LIMIT`, the optional trailing semicolon, and rejection of additional statements; verify full-statement and multiple-statement tests pass.
- [x] 3.5 Add parser error tests for unexpected tokens, missing clauses, malformed patterns, and unsupported clauses; verify every error reports a line, a column, and a pointed message in `tests/engine/query/test_parser.py`.

## 4. Semantic analysis

- [x] 4.1 Implement scopes and variable kinds for node, relationship, and path variables, including repeated-variable constraints and use of a variable in an incompatible position; verify scope and kind tests pass in `tests/engine/query/test_semantic.py`.
- [x] 4.2 Implement static checks for function calls, argument kinds, arithmetic operands, comparison operands, aggregate placement, and nested aggregates; verify valid and invalid expression tests pass.
- [x] 4.3 Implement projection column naming from aliases or expression text, duplicate-column rejection, grouping-key discovery, and aggregate validation; verify column and grouping tests pass.
- [x] 4.4 Collect referenced `$name` parameters, reject parameters in identifier positions, and raise a semantic error for missing parameters at execution; verify parameter tests pass.
- [x] 4.5 Implement clear semantic errors for recognized but unsupported constructs, including variable-length patterns, multiple patterns, multiple `MATCH` clauses, `OPTIONAL MATCH`, `WITH`, `UNWIND`, subqueries, `CASE`, map literals, and write clauses; verify each boundary is covered by a test.

## 5. Value model and expression evaluation

- [x] 5.1 Implement the query value model, numeric equality with booleans distinct, null propagation, list equality, `ValueKey` for distinct and grouping, and the ordering key for null placement and mixed types; verify equality, hashing, distinct, and ordering tests pass in `tests/engine/query/test_values.py`.
- [x] 5.2 Implement the scalar function set: `id`, `labels`, `type`, `properties`, `keys`, `size`, `coalesce`, `toInteger`, `toFloat`, `toString`, `lower`, `upper`, `trim`, `abs`, `concat`, `startNode`, and `endNode`; verify every function has a success and an edge-case test.
- [x] 5.3 Implement arithmetic operators with numeric promotion, float division, signed 64-bit overflow detection, division-by-zero errors, and unary minus; verify arithmetic and error tests pass.
- [x] 5.4 Implement the expression evaluator over a binding of variables, including property access, parameters, operators, functions, list literals, and null propagation; verify evaluator tests pass.
- [x] 5.5 Implement aggregation for `count(*)`, `count(expr)`, `collect`, `sum`, `avg`, `min`, `max`, `DISTINCT` variants, grouping, and empty-input semantics; verify aggregate and grouping tests pass.

## 6. SQL compilation and pushdown

- [x] 6.1 Implement a SQL fragment builder that accumulates selected columns, joins, predicates, and bound parameters without interpolating user values; verify generated SQL uses placeholders and that quoted JSON paths are built from the property codec in `tests/engine/query/test_compiler.py`.
- [x] 6.2 Compile node patterns with labels, property maps, and anonymous elements into indexed `nodes` and `node_labels` access; verify label and property-map compilation tests pass.
- [x] 6.3 Compile relationship patterns with type alternatives and direction into joins against the indexed endpoint columns; verify outgoing, incoming, and type-filter tests pass.
- [x] 6.4 Compile repeated variables into equality constraints and path variables into node and relationship selections; verify repeated-variable and path-selection tests pass.
- [x] 6.5 Compile undirected relationships through a canonical-orientation subquery so self-loops are produced once; verify self-loop, parallel-relationship, diamond, and cycle tests pass.
- [x] 6.6 Implement the pushdown analyser that splits `WHERE` into SQL predicates and a Python residual expression for `AND`, `OR`, `NOT`, literal-list `IN`, parameter-list `IN`, functions, and null tests, leaving functions, parameter-list `IN`, and arithmetic as residual; verify pushdown and residual tests pass.
- [x] 6.7 Add batch node loading by id, including labels and properties, so execution avoids a per-node query; verify batch loading returns the same snapshots as individual reads.
- [x] 6.8 Implement the logical and physical plan pipeline from match to residual filter, projection, aggregation, distinct, ordering, skip, and limit; verify plan construction and ordering tests pass.

## 7. Execution and results

- [x] 7.1 Implement bindings and row decoding from SQL rows, including immutable node and relationship snapshots and path assembly; verify binding and snapshot tests pass in `tests/engine/query/test_executor.py`.
- [x] 7.2 Implement projection, residual filtering, and `DISTINCT` over projected rows; verify projection, duplicate-value, and distinct tests pass.
- [x] 7.3 Implement grouping and aggregation execution, including zero-input behavior and `DISTINCT` aggregates; verify grouped and empty-input tests pass.
- [x] 7.4 Implement multi-key ordering with `ASC`/`DESC`, null-last ascending and null-first descending placement, and `SKIP`/`LIMIT` slicing; verify ordering and pagination tests pass.
- [x] 7.5 Implement `QueryResult` and immutable `Row` mappings with ordered columns, name lookup, and the documented query-value types; verify result-model tests pass.
- [x] 7.6 Implement the deferred read transaction around graph-level execution, materialize before returning, and roll back on failure; verify a result is unchanged by a later write and that the connection is not left in a transaction.
- [x] 7.7 Implement `Transaction.query` so it runs on the active transaction and sees uncommitted writes without starting or finishing a transaction; verify transaction-visibility tests pass.

## 8. Public API and lifecycle

- [x] 8.1 Implement `Graph.query`, `Graph.prepare`, and `PreparedQuery` with reusable columns, repeated execution with different parameters, and parse/semantic failures at preparation; verify API and reuse tests pass in `tests/engine/query/test_api.py`.
- [x] 8.2 Export the query API and errors from `src/pygrafito/__init__.py`, add the active-transaction guard for graph-level queries, and add closed-handle checks; verify guards, closed-handle, and package-export tests pass.
- [x] 8.3 Add an `[Unreleased]` `CHANGELOG.md` entry for the query language and a short README section introducing `Graph.query` with a runnable example; verify `hatch test tests/test_readme.py` passes and the changelog entry is present.

## 9. Language reference and conformance

- [x] 9.1 Write `docs/query-language.md` covering the grammar, core profile, value and null semantics, ordering, aggregation, functions, parameters, errors, and deliberate divergences from exact-match object lookups; verify every section maps to an ADDED requirement and every unsupported construct is listed.
- [x] 9.2 Add a table-driven dialect conformance suite in `tests/engine/query/test_conformance.py` using TRON fixtures, with representative queries and expected rows for patterns, filters, projection, aggregates, ordering, and nulls; verify the suite passes.
- [x] 9.3 Add query-language Python examples to `README.md` and extend `tests/test_readme.py` if needed so every fenced example executes; verify `hatch test tests/test_readme.py` passes.

## 10. Integration and final gates

- [x] 10.1 Add an end-to-end integration test that combines file persistence, transactions, prepared queries, aggregation, ordering, and a later write; verify the test passes and the earlier result stays unchanged.
- [x] 10.2 Add a schema-compatibility test that opens a database created with the pre-change schema and runs a query; verify no schema version bump or migration is required.
- [x] 10.3 Run `hatch check --fix` and `hatch test`; verify lint, formatting, types, the full suite, and coverage of at least 80% all pass.
- [x] 10.4 Review new code, specs, tests, and docs for product names or trademarks and confirm the language reference uses only generic dialect wording; verify by a final source and documentation review.

## Workflow follow-up

- Run `openspec validate add-read-query-language --strict` and resolve any artifact issues before implementation is considered complete.
- Archive the change after the project's review requirements are satisfied.
- Verify the archived specs describe the shipped behavior.
