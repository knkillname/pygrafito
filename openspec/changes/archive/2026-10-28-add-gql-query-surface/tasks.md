# Tasks

## 1. Parser and AST Foundation

- [x] 1.1 Add `WHEN`, `THEN`, `ELSE`, `END`, `UNION`, `INTERSECT`, and `EXCEPT` to the keyword
      catalog and `||` to the operator catalog. Add lexer tests for the new tokens and for
      backtick-quoted variables using the new keyword spellings.
- [x] 1.2 Add the `Case`, `MapLiteral`, `ListAccess`, `ListSlice`, `ListComprehension`, and
      `Subquery` expression nodes, `With.star`, and the compound-query AST. Verify with
      `hatch check --fix` and AST/parser type checks.
- [x] 1.3 Parse simple and searched `CASE`, map literals, duplicate map keys, and the `ELSE`/`END`
      boundaries. Verify with parser tests for each form and positioned errors.
- [x] 1.4 Parse list indexing, slicing, and comprehensions, including the `[x IN ...]` lookahead
      that distinguishes a comprehension from a list literal. Verify with parser tests for index,
      slice, filter, projection, and malformed brackets.
- [x] 1.5 Parse `WITH *` and `WITH DISTINCT *`; reject mixing `*` with explicit items and reject a
      final `WITH *`. Verify with parser and semantic tests.
- [x] 1.6 Parse `EXISTS { ... }` and `COUNT { ... }` inner blocks with read stages only. Verify that
      `RETURN`, `FINISH`, `NEXT`, `YIELD`, and write clauses are rejected before execution.
- [x] 1.7 Parse compound queries with left-associative set operators, operand final `RETURN`
      boundaries, and trailing compound `ORDER BY`/`OFFSET`/`LIMIT`. Verify that a single-term
      query keeps its current ordering behavior and that operand-level final ordering is rejected.

## 2. Expression Surface

- [x] 2.1 Add `CASE` evaluation to the scalar and group evaluators. Verify simple/search case,
      null-not-matching, missing `ELSE`, and lazy branch tests.
- [x] 2.2 Add map-literal evaluation, immutable mapping results, map equality, grouping, and the
      "maps are not orderable" error. Verify projection, empty map, duplicate key, list/map nesting,
      and write-value rejection tests.
- [x] 2.3 Add list index/slice and list-comprehension evaluation. Verify negative and out-of-range
      indexes, open/clamped slices, null and non-list sources, filtering, projection, and shadowing
      tests.
- [x] 2.4 Add `||` and the string-operand `+` alias to expression evaluation and static kind checks.
      Verify canonical concatenation, null propagation, mixed-operand errors, and unchanged numeric
      `+` tests.
- [x] 2.5 Add `nodes`, `relationships`, and `length` to the function catalog and handlers. Verify
      traversal order, path length, null path, and non-path errors.
- [x] 2.6 Add the extended scalar function signatures and handlers, including `range`, `head`,
      `last`, `tail`, `reverse`, `split`, `substring`, `replace`, `toBoolean`, `round`, `ceil`, and
      `floor`. Verify every edge case listed in the delta spec.
- [x] 2.7 Add semantic checks for new expression nodes, static result kinds, aggregate/grouping
      interaction, and subquery-free expression positions. Verify with semantic tests covering
      invalid combinations.
- [x] 2.8 Add expression corpus cases for `case`, `map-literals`, `list-indexing-and-slicing`,
      `list-comprehensions`, `string-concatenation`, `path-functions`, `extended-scalar-functions`,
      and `with` (the `WITH *` matrix row). Verify with `hatch test tests/test_conformance.py`.
- [x] 2.9 Update `docs/reference/query-language.md` sections for `CASE`, maps, list expressions,
      string concatenation, path functions, extended functions, and `WITH *`; update the grammar
      summary. Run `hatch run docs:build` and fix warnings.

## 3. Read-Only Subqueries

- [x] 3.1 Add child semantic analysis for subquery bodies, seeded with outer variable kinds and
      parameters. Verify correlation, local scope, shadowing rejection, at-least-one-row-source,
      read-only, and no-result-clause tests.
- [x] 3.2 Add a subquery runner to the evaluator and executor. Verify correlated and uncorrelated
      `EXISTS`/`COUNT`, early-exit `EXISTS`, and no-match behavior.
- [x] 3.3 Share the enclosing budget, transaction, and snapshot with subqueries. Verify expansion
      and row budget failures, no partial result, concurrent-write snapshot, and no extra
      transaction/savepoint.
- [x] 3.4 Add corpus cases for `exists` and `count` and document both query expressions in the
      query-language reference. Run the conformance tests and `hatch run docs:build`.

## 4. Set Operations

- [x] 4.1 Add compound-query semantic analysis, including read-only operands, column count/name
      checks, first-operand columns, no `FINISH`/`RETURN NO BINDINGS`, and operand-level ordering
      rejection. Verify with semantic tests.
- [x] 4.2 Add compound execution with one transaction, one snapshot, and one budget. Verify
      `UNION ALL`, `UNION`, `INTERSECT`, `EXCEPT`, left associativity, duplicate rules, and set
      result ordering.
- [x] 4.3 Resolve compound ordering and pagination against output column names; integrate prepared
      columns, parameters, `is_write`, and explain operators. Verify prepared-query, explain, and
      result-model tests.
- [x] 4.4 Add corpus cases for `union`, `union-all`, `intersect`, and `except`; document compound
      queries, ordering, and pagination in the query-language reference and grammar summary. Run
      the conformance tests and `hatch run docs:build`.

## 5. Profile, Tours, and Integration

- [x] 5.1 Update `docs/reference/gql-profile.md` to mark the expression, subquery, and set-operation
      rows `supported`, remove them from the gated table, update the construct inventory and matrix
      owners/corpus names, and keep the path rows gated. Verify with
      `hatch test tests/test_gql_profile.py`.
- [x] 5.2 Update the query-language reference's gated and unsupported sections and the tour catalog.
      Add or update tour statements that use map literals and the new expression surface; update
      `tests/test_examples.py` so the forbidden-tour pattern no longer rejects supported forms.
      Verify with `hatch test tests/test_examples.py`.
- [x] 5.3 Add the `[Unreleased]` changelog entry and a clear migration note for the newly reserved
      keywords (`WHEN`, `THEN`, `ELSE`, `END`, `UNION`, `INTERSECT`, `EXCEPT`). Verify the changelog
      renders and the note tells users to backtick-quote affected identifiers.
- [x] 5.4 Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; confirm coverage remains
      at least 80%, the profile consistency test passes, and no supported row lacks a corpus case.

## Workflow follow-up

- Archive the change after review and sync the delta into the main `graph-query-language` spec.
- After archive, verify expression, subquery, and set-operation rows are `supported`, the remaining
  gated rows are only the path-engine families, and `openspec validate --specs --strict` passes.
- Confirm no active changes remain and the changelog migration note is still present.
