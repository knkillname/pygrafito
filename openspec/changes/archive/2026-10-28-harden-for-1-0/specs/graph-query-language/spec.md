# Spec Delta

## ADDED Requirements

### Requirement: Total query input error contract

Parsing or executing a statement SHALL raise only `QueryError` subclasses. A parser nesting limit
and an oversized integer literal SHALL raise a positioned query error. Raw `RecursionError`,
`ValueError`, `MemoryError`, `sqlite3.Error`, and `UnicodeDecodeError` SHALL NOT escape from a
query call.

#### Scenario: Deep nesting

- **WHEN** a statement nests parentheses or list literals beyond the documented parser depth
- **THEN** the error is a `QuerySyntaxError` with a position, not a `RecursionError`

#### Scenario: Oversized integer literal

- **WHEN** a statement contains an integer literal beyond the supported conversion limit
- **THEN** the error is a `QuerySemanticError`, not a `ValueError`

#### Scenario: Arbitrary text

- **WHEN** arbitrary text is submitted as a query
- **THEN** the call either returns a result or raises a `QueryError`; no other exception escapes

#### Scenario: Execution failure

- **WHEN** a query fails during evaluation
- **THEN** the error is a `QueryExecutionError`, not a raw `sqlite3.Error`

#### Scenario: No partial result

- **WHEN** a query fails during parsing or execution
- **THEN** no rows are returned

### Requirement: Materialized result memory contract

`QueryResult` SHALL be fully materialized before the call returns. The intermediate row budget
SHALL bound the result; exceeding it SHALL raise `QueryBudgetExceededError`. The library SHALL
document the default row limit and how to lower it. No streaming result API SHALL exist in 1.x.

#### Scenario: Result is materialized

- **WHEN** a query returns
- **THEN** every row is available before the call returns and no transaction remains open

#### Scenario: Budget bounds the result

- **WHEN** `max_rows` is lowered and the query produces more intermediate rows than allowed
- **THEN** `QueryBudgetExceededError` is raised with no rows

#### Scenario: Default is documented

- **WHEN** a user reads the result-memory reference
- **THEN** the default row limit and the memory implications are stated

#### Scenario: No streaming result API

- **WHEN** a user inspects the public graph API
- **THEN** query execution exposes materialized `QueryResult` values only
