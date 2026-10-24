# Spec Delta

## ADDED Requirements

### Requirement: Multiple patterns and match stages

A `MATCH` clause MAY contain several comma-separated path patterns, and a statement MAY contain several `MATCH` clauses. Each clause SHALL be a read stage over the rows produced by earlier stages. Variables shared by patterns SHALL bind the same element; patterns with no shared variable SHALL produce a cartesian product. A later `MATCH` MAY constrain earlier variables, introduce new ones, or both. An input row with no match SHALL be removed.

#### Scenario: Shared variable joins patterns

- **WHEN** a caller matches `MATCH (a:Program), (b:Program) WHERE a.cycles = b.cycles RETURN a, b`
- **THEN** each returned pair satisfies the filter and may bind the same node twice

#### Scenario: Shared variable unifies elements

- **WHEN** a caller matches `MATCH (a:Program)-[:ALLIES_WITH]->(b:Program), (b)-[:ALLIES_WITH]->(c:Program) RETURN a, c`
- **THEN** `b` refers to the same node in both patterns

#### Scenario: Independent patterns form a cartesian product

- **WHEN** two comma-separated patterns share no variable and match three and two elements respectively
- **THEN** six rows are returned

#### Scenario: Chained match stages

- **WHEN** a caller submits `MATCH (a:Program) MATCH (a)-[:ALLIES_WITH]->(b:Program) RETURN b`
- **THEN** the second stage joins against the rows produced by the first

#### Scenario: Unmatched input row is removed

- **WHEN** a later `MATCH` finds no match for some input row
- **THEN** that row is absent from the result

#### Scenario: Path variable cannot be bound twice

- **WHEN** a caller binds the same path variable to two patterns
- **THEN** the system raises a semantic query error before execution

### Requirement: Optional match

An `OPTIONAL MATCH` clause SHALL be a read stage with left-join semantics. When a pattern matches for an input row, it SHALL produce one row per match. When it does not, the input row SHALL survive with variables introduced by the optional stage bound to null and variables bound earlier unchanged. The stage's `WHERE` SHALL be part of the optional match, and a null value SHALL never satisfy a downstream filter.

#### Scenario: Matched rows expand

- **WHEN** an optional pattern matches twice for one input row
- **THEN** two rows are produced for that row

#### Scenario: Unmatched row is preserved with nulls

- **WHEN** an optional pattern matches nothing for an input row
- **THEN** the row is returned with the optional variable bound to null

#### Scenario: Earlier variables are unchanged

- **WHEN** an optional match fails for a row that already bound `a`
- **THEN** the returned row still binds `a` to its original value

#### Scenario: Optional where clause filters the optional match

- **WHEN** `OPTIONAL MATCH (a)-[r:ALLIES_WITH]->(b) WHERE b.cycles > 40` matches no row
- **THEN** the input row survives with `b` and `r` bound to null

#### Scenario: Downstream filter excludes nulls

- **WHEN** a `WHERE` after an optional match tests a variable that is null for some rows
- **THEN** those rows do not satisfy the filter

#### Scenario: Optional match is allowed first

- **WHEN** a statement starts with `OPTIONAL MATCH (n:Program) RETURN n`
- **THEN** the statement is accepted and returns every match or one null row when none exists

### Requirement: WITH projection and scope

A `WITH` clause SHALL be a read stage that projects expressions into a new scope. Only names projected by the `WITH` SHALL be visible to later stages. A projected variable keeps its kind and snapshot; a non-variable expression SHALL require an alias. Duplicate output names SHALL be rejected, `WITH DISTINCT` SHALL remove duplicate rows, and `WITH` SHALL NOT be the final clause of a statement.

#### Scenario: Scope is reset

- **WHEN** a caller projects `WITH a` and a later stage references `b`
- **THEN** the system raises a semantic query error for the unbound `b`

#### Scenario: Expression requires an alias

- **WHEN** a caller projects `WITH a.cycles + 1` without an alias
- **THEN** the system raises a semantic query error

#### Scenario: Variable keeps its identity

- **WHEN** a caller projects `WITH a` and later returns `a.designation`
- **THEN** `a` still refers to the same node snapshot

#### Scenario: Distinct removes duplicate rows

- **WHEN** a caller projects `WITH DISTINCT a.designation AS name`
- **THEN** equal names appear once

#### Scenario: Duplicate output names are rejected

- **WHEN** a `WITH` projects two items with the same name
- **THEN** the system raises a semantic query error

#### Scenario: With cannot end a statement

- **WHEN** a statement ends with a `WITH` clause and has no `RETURN`
- **THEN** the system raises a query error

### Requirement: WITH aggregation and pagination

A `WITH` clause SHALL support the same aggregate functions, implicit grouping, `WHERE`, `ORDER BY`, `SKIP`, and `LIMIT` as `RETURN`. `WHERE` after `WITH` SHALL filter that stage's rows and MAY reference an aggregate alias. Names produced by the stage SHALL bind following stages, so grouped rows can be filtered, sorted, and paginated downstream.

#### Scenario: Aggregate then filter

- **WHEN** a caller submits `MATCH (a)-[:ALLIES_WITH]->(b) WITH a, count(*) AS friends WHERE friends > 2 RETURN a`
- **THEN** only nodes with more than two matches are returned

#### Scenario: Order by aggregate alias

- **WHEN** a caller orders a `WITH` stage by an aggregate alias descending
- **THEN** rows are ordered by that aggregate

#### Scenario: Grouped pagination

- **WHEN** a `WITH` stage groups rows and applies `SKIP` and `LIMIT`
- **THEN** pagination applies to the grouped result, not to the input rows

#### Scenario: One row per group

- **WHEN** a `WITH` stage mixes an aggregate with a non-aggregate expression
- **THEN** one row is returned per distinct non-aggregate value

### Requirement: Variable-length relationship patterns

A relationship pattern MAY carry a quantifier: `*n` for exactly `n` hops, `*n..m` for a bounded range, or `*0..m` to include the zero-hop case. Every hop SHALL apply the pattern's types, direction, and property map. The upper bound SHALL be explicit; a bare `*` or an open-ended `*n..` SHALL be rejected with a query error. Bounds SHALL be non-negative integers with `n` less than or equal to `m`.

#### Scenario: Exact length

- **WHEN** a caller matches `(a)-[:ALLIES_WITH*2]->(b)`
- **THEN** only nodes two relationships away are bound

#### Scenario: Bounded range

- **WHEN** a caller matches `(a)-[:ALLIES_WITH*1..3]->(b)`
- **THEN** nodes at depths one, two, and three are bound

#### Scenario: Zero hop

- **WHEN** a caller matches `(a)-[:ALLIES_WITH*0..2]->(b)`
- **THEN** `a` itself is included as a zero-hop match

#### Scenario: Every hop applies the pattern

- **WHEN** a quantified pattern carries types, a direction, and a property map
- **THEN** every traversed relationship satisfies all of them

#### Scenario: Unbounded quantifier is rejected

- **WHEN** a caller writes `MATCH (a)-[*]->(b) RETURN b` or `MATCH (a)-[*1..]->(b) RETURN b`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Invalid bounds are rejected

- **WHEN** a caller writes a negative bound or a lower bound greater than the upper bound
- **THEN** the system raises a query error before execution

### Requirement: Variable-length bindings and trails

A variable-length relationship variable SHALL bind the ordered list of relationships traversed. Traversal SHALL be relationship-unique within one matched path: no relationship may be used twice, while nodes MAY repeat. A path variable SHALL include every expanded relationship in traversal order and its nodes from path start to end. A variable-length relationship variable SHALL NOT be used where a single relationship is required.

#### Scenario: Relationship variable binds a list

- **WHEN** a caller matches `(a)-[r:ALLIES_WITH*1..3]->(b) RETURN r`
- **THEN** each row binds `r` to the list of relationships in that match

#### Scenario: Relationship uniqueness

- **WHEN** a directed cycle offers a route that would reuse one relationship
- **THEN** that route is not produced

#### Scenario: Nodes may repeat

- **WHEN** a trail revisits a node without reusing a relationship
- **THEN** the match is produced

#### Scenario: Path includes expanded relationships

- **WHEN** a caller matches `p = (a)-[:ALLIES_WITH*1..2]->(b) RETURN p`
- **THEN** `p` contains every traversed relationship in order

#### Scenario: Size of the relationship list

- **WHEN** a caller projects `size(r)` for a variable-length relationship variable
- **THEN** the value is the number of traversed relationships

#### Scenario: Single-relationship use is rejected

- **WHEN** a caller passes a variable-length relationship variable to `type(r)` or accesses `r.property`
- **THEN** the system raises a semantic query error

## MODIFIED Requirements

### Requirement: Core dialect profile

A statement SHALL be a non-empty ordered sequence of read stages, optional write clauses, and an optional final `RETURN`. A read stage SHALL be `MATCH`, `OPTIONAL MATCH`, or `WITH`. Every write clause SHALL follow every read stage, and `RETURN` SHALL be at most once and final. A read statement SHALL contain at least one matching stage and a `RETURN`; a statement with a write clause MAY omit `MATCH` and `RETURN`. Unsupported forms SHALL be rejected, never ignored.

#### Scenario: Minimal query

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name`
- **THEN** the statement is accepted and returns one row per matching node

#### Scenario: Chained read stages

- **WHEN** a caller submits `MATCH (a:Program) WITH a MATCH (a)-[:ALLIES_WITH]->(b) RETURN b`
- **THEN** the statement is accepted and the second stage joins against the first

#### Scenario: Unsupported pattern form

- **WHEN** a caller submits `MATCH (a)-[*]->(b) RETURN b` or `MATCH (a)-[*1..]->(b) RETURN b`
- **THEN** the system raises a semantic query error before execution because the upper bound is missing

#### Scenario: Unsupported clause

- **WHEN** a caller submits a statement using `UNWIND`, `CALL { ... }`, `EXISTS { ... }`, `CASE`, a map literal, `MERGE`, or `WITH *`
- **THEN** the system raises a query error before execution

#### Scenario: Multiple statements

- **WHEN** a caller submits more than one statement separated by semicolons
- **THEN** the system raises a query error before execution

#### Scenario: Write-only statement

- **WHEN** a caller submits `CREATE (n:Program)` with no `MATCH` and no `RETURN`
- **THEN** the statement is accepted and executed

#### Scenario: Match with write and no RETURN

- **WHEN** a caller submits `MATCH (n:Program) SET n.cycles = 1`
- **THEN** the statement is accepted and executed

#### Scenario: RETURN before a write clause

- **WHEN** a caller submits `MATCH (n:Program) RETURN n CREATE (m:Program)`
- **THEN** the system raises a query error before execution

#### Scenario: Write clause before MATCH

- **WHEN** a caller submits `CREATE (n:Program) WITH n MATCH (m) RETURN m`
- **THEN** the system raises a query error before execution

#### Scenario: Read statement without RETURN

- **WHEN** a caller submits a read statement with matching stages but no `RETURN`
- **THEN** the system raises a query error before execution

#### Scenario: Write after a WITH stage

- **WHEN** a caller submits `MATCH (a:Program) WITH a CREATE (b:Program {designation: 'Tron'}) RETURN b`
- **THEN** the statement is accepted and creates one node per row produced by the `WITH`

### Requirement: Consistent execution snapshot

A query SHALL evaluate against one consistent graph state. Writes made after execution starts SHALL NOT change an already returned result, and a query executed through an active transaction SHALL include that transaction's uncommitted writes.

#### Scenario: Later write does not change the result

- **WHEN** a caller executes a query, changes the graph, and then inspects the earlier result
- **THEN** the earlier result still reflects the state at execution time

#### Scenario: Transaction snapshot

- **WHEN** a caller executes a query inside a transaction that has uncommitted writes
- **THEN** the result includes those writes and excludes writes from other connections

#### Scenario: All stages share one snapshot

- **WHEN** a statement with several read stages runs while another connection changes a row between stages
- **THEN** every stage observes the state at execution start
