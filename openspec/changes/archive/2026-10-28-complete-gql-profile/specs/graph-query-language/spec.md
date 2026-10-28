# Spec Delta

## ADDED Requirements

### Requirement: Recognized out-of-profile rejection

A statement that uses a recognized out-of-profile construct SHALL raise a positioned `QuerySemanticError` before execution. The message SHALL name the construct and either the supported alternative or the reason none exists. The statement SHALL NOT execute, and a write statement SHALL NOT mutate data.

#### Scenario: Procedure call is named as a procedure

- **WHEN** a caller submits `CALL tron.proc() YIELD value RETURN value`
- **THEN** the error names procedure calls as out of profile and does not describe them as subqueries

#### Scenario: Subquery form names its alternative

- **WHEN** a caller submits `CALL { MATCH (n) RETURN n } RETURN n`
- **THEN** the error names `CALL { ... }` and points to `EXISTS { ... }`, `COUNT { ... }`, or separate statements

#### Scenario: Whole-map assignment names its alternative

- **WHEN** a caller submits `MATCH (n) SET n = {designation: 'Tron'} RETURN n`
- **THEN** the error names whole-map assignment and points to assigning properties individually

#### Scenario: Property existence names its alternative

- **WHEN** a caller submits `MATCH (n) WHERE exists(n.designation) RETURN n`
- **THEN** the error names `exists(n.prop)` and points to `n.prop IS NOT NULL`

#### Scenario: Regex predicate names supported predicates

- **WHEN** a caller submits `MATCH (n) WHERE n.designation =~ 'Tr.*' RETURN n`
- **THEN** the error names regex predicates and points to `STARTS WITH`, `ENDS WITH`, and `CONTAINS`

#### Scenario: Path function names path search

- **WHEN** a caller submits a pattern that uses `shortestPath()` or `allShortestPaths()`
- **THEN** the error names the Cypher-only path function and points to the supported path-search prefixes

#### Scenario: Statement-level forms are named

- **WHEN** a caller submits `SELECT`, an in-language transaction, a full temporal literal, or a catalog statement such as `DROP GRAPH`
- **THEN** each is rejected by name as out of profile rather than as a stray token

#### Scenario: Rejected write changes nothing

- **WHEN** a write statement contains an out-of-profile construct
- **THEN** the call raises before execution and no node, relationship, or property changes

### Requirement: Syntax errors stay syntax errors

Text that is not a recognized out-of-profile construct and does not fit the grammar SHALL raise a `QuerySyntaxError`. A syntax error SHALL NOT claim that a construct is out of profile.

#### Scenario: Unknown operator is a syntax error

- **WHEN** a caller submits `RETURN 1 ^ 2`
- **THEN** the error is a syntax error reporting the offending line and column

#### Scenario: Invalid use of a supported feature is not a boundary error

- **WHEN** a caller uses `MERGE` over a quantified pattern
- **THEN** the error is a semantic error naming the restriction, not an out-of-profile rejection

### Requirement: Rejection without new reserved words

Recognizing an out-of-profile construct SHALL NOT reserve a new keyword or change the meaning of an existing identifier. Words such as `date`, `start`, `drop`, and `select` SHALL remain usable as variables, aliases, labels, and property keys.

#### Scenario: Out-of-profile words stay identifiers

- **WHEN** a caller uses `date`, `start`, `drop`, or `select` as a variable, alias, label, or property key in an otherwise supported statement
- **THEN** the statement is accepted and the identifier is not treated as a construct boundary

#### Scenario: Boundary recognition is contextual

- **WHEN** a caller writes `DROP GRAPH` or `SELECT` in a statement position that cannot be a supported clause
- **THEN** the statement is rejected as a recognized out-of-profile construct
