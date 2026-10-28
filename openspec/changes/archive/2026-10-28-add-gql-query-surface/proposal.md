# Proposal

## Why

The 1.0 GQL profile still marks the expression surface, read-only subqueries, and set operations as
gated. These are the remaining items in the roadmap's "Foundation and query surface" section, and
they block `complete-gql-profile`. They also share parser, semantic, evaluator, and execution
infrastructure, so landing them together avoids three overlapping rewrites of the same expression
pipeline.

## What Changes

- Add the expression surface:
  - Simple and searched `CASE`.
  - Map literals.
  - List indexing, slicing, and comprehensions.
  - Canonical `||` string concatenation, with `+` as a string-operand compatibility alias.
  - `nodes(path)`, `relationships(path)`, and `length(path)`.
  - Extended scalar functions: `range`, `head`, `last`, `tail`, `reverse`, `split`, `substring`,
    `replace`, `toBoolean`, `round`, `ceil`, and `floor`.
  - `WITH *` as a scope-preserving part of the `WITH` extension.
- Add read-only query expressions:
  - `EXISTS { ... }` and `COUNT { ... }`, with correlated and uncorrelated inner queries.
  - One shared budget, transaction, and snapshot with the enclosing statement.
- Add set operations:
  - `UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT` over read-only compound queries.
  - First-operand column names, matching column count and names, set semantics, and compound-level
    ordering and pagination.
- Update the GQL profile statuses, construct inventory, matrix, conformance corpus, query-language
  reference, grammar summary, tours, and changelog as the new rows become supported.
- **BREAKING**: reserve the new `WHEN`, `THEN`, `ELSE`, `END`, `UNION`, `INTERSECT`, and `EXCEPT`
  keywords. Existing variables or aliases using those names must be backtick-quoted. The migration
  note will be in the changelog and query-language reference.
- No other existing supported behavior is removed. The new `+` string behavior is an additive alias
  for string operands; numeric `+` keeps its current meaning.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `graph-query-language`: adds the expression, subquery, and set-operation requirements and updates
  the existing expression, function, statement, and prepared-query contracts.

## Impact

- Query frontend: lexer, parser, AST, semantic analysis, planning, and error positions.
- Query evaluator: scalar evaluation, grouping evaluation, function catalog, value semantics, and
  subquery execution.
- Query executor: compound-query execution, shared budget and snapshot handling, and prepared
  columns.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md`, grammar
  summary, tours, and `CHANGELOG.md`.
- Tests: parser, semantic, evaluator, executor, conformance corpus, profile consistency, and tour
  coverage.
- No new runtime dependencies; runtime remains standard-library only.
- Out of scope: the path-engine features (match modes, grouped quantified paths, path search, and
  open-ended traversal), `CALL { ... }`, write subqueries, `INTERSECT ALL`, `EXCEPT ALL`,
  whole-map assignment, `exists(n.prop)`, regex predicates, temporal values, catalog operations, and
  path indexing.
