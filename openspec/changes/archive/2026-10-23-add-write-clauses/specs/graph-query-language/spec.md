# Spec Delta

## ADDED Requirements

### Requirement: Statement execution

The system SHALL execute exactly one statement per call and return a materialized `QueryResult`. A statement MAY contain write clauses and SHALL be classified as a write when it contains `CREATE`, `SET`, `REMOVE`, `DELETE`, or `DETACH DELETE`. A read statement SHALL change no data. `Graph.query` SHALL parse and execute in one step, and `Graph.prepare` SHALL return a reusable `PreparedQuery` for either kind.

#### Scenario: Execute a read statement

- **WHEN** a caller passes a valid read-only statement and its parameters to `Graph.query`
- **THEN** the system returns a `QueryResult` containing the projected rows and changes no data

#### Scenario: Execute a write statement

- **WHEN** a caller passes a statement containing a write clause to `Graph.query`
- **THEN** the system executes it and returns a `QueryResult` with the statement's summary

#### Scenario: Prepare and reuse a statement

- **WHEN** a caller prepares a valid statement and executes the prepared query twice with different parameters
- **THEN** both executions succeed without reparsing the statement

#### Scenario: Multiple statements rejected

- **WHEN** a caller submits more than one statement separated by semicolons
- **THEN** the system raises a query error before executing either statement

### Requirement: CREATE clause

`CREATE` SHALL create nodes and relationships from a pattern. A created node SHALL bind its variable for later clauses and `RETURN`. A created relationship SHALL require both endpoint nodes to be already bound by a variable. `CREATE` SHALL always create new elements and SHALL NOT match existing ones. Labels and property maps SHALL be validated before execution, and property values SHALL be literals or parameters.

#### Scenario: Create a standalone node

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Quorra', cycles: 37}) RETURN n`
- **THEN** one node with that label and those properties exists and is returned

#### Scenario: Create a relationship between bound nodes

- **WHEN** a caller matches two nodes and submits `CREATE (a)-[r:ALLIES_WITH {since_cycle: 2020}]->(b)`
- **THEN** one relationship of that type and those properties is created between them

#### Scenario: Create from every match row

- **WHEN** a `MATCH` binds three program nodes and a following `CREATE` adds a node
- **THEN** three new nodes are created

#### Scenario: Unbound relationship endpoint

- **WHEN** a caller submits `CREATE (a)-[r:ALLIES_WITH]->(b)` without binding `a` or `b`
- **THEN** the system raises a semantic query error and creates nothing

#### Scenario: Create does not match

- **WHEN** a caller submits the same `CREATE` statement twice
- **THEN** both calls create new nodes instead of reusing an existing one

### Requirement: SET clause

`SET` SHALL assign a property from an expression and SHALL add labels to a bound node or relationship. Assigning a null value SHALL remove the property. Labels added with `SET` SHALL be static identifiers. `SET` SHALL reject an unbound variable and SHALL reject a label added to a value that is not a node.

#### Scenario: Set a property

- **WHEN** a caller submits `MATCH (n:Program) WHERE n.designation = 'Quorra' SET n.cycles = 38`
- **THEN** the matched node stores the integer 38 under `cycles`

#### Scenario: Set from an expression

- **WHEN** a caller submits `MATCH (n:Program) SET n.cycles = n.cycles + 1`
- **THEN** each matched node's property is incremented using the dialect's arithmetic rules

#### Scenario: Null removes a property

- **WHEN** a caller submits `SET n.cycles = null`
- **THEN** the `cycles` property is removed from the node

#### Scenario: Add a label

- **WHEN** a caller submits `MATCH (n:Program) SET n:SystemMonitor`
- **THEN** each matched node carries both `Program` and `SystemMonitor`

#### Scenario: Unbound variable

- **WHEN** a caller submits `SET n.cycles = 1` without binding `n`
- **THEN** the system raises a semantic query error and changes nothing

### Requirement: REMOVE clause

`REMOVE` SHALL remove a property or one or more labels from a bound element. Removing a property or label that is absent SHALL leave the element unchanged. `REMOVE` SHALL reject an unbound variable.

#### Scenario: Remove a property

- **WHEN** a caller submits `MATCH (n:Program) REMOVE n.cycles`
- **THEN** the property is absent from each matched node

#### Scenario: Remove a label

- **WHEN** a caller submits `MATCH (n:Program) REMOVE n:ISO`
- **THEN** `ISO` is absent from each matched node's labels

#### Scenario: Absent property is a no-op

- **WHEN** a caller removes a property the matched node does not have
- **THEN** the node is unchanged and no error is raised

#### Scenario: Unbound variable

- **WHEN** a caller submits `REMOVE n.cycles` without binding `n`
- **THEN** the system raises a semantic query error and changes nothing

### Requirement: DELETE clause

`DELETE` SHALL delete relationships and nodes. A node that still has an incident relationship SHALL be rejected unless `DETACH DELETE` is used, which SHALL remove its incident relationships first. `DELETE` SHALL reject an unbound variable and SHALL reject a value that is not a node or relationship.

#### Scenario: Delete a relationship

- **WHEN** a caller matches a relationship and submits `DELETE r`
- **THEN** the relationship is removed and both endpoint nodes remain

#### Scenario: Delete a disconnected node

- **WHEN** a caller matches a node with no relationships and submits `DELETE n`
- **THEN** the node and its labels and properties are removed

#### Scenario: Connected node rejected

- **WHEN** a caller submits `DELETE n` for a node with incident relationships
- **THEN** the system raises an error and the node and its relationships are unchanged

#### Scenario: Detach and delete

- **WHEN** a caller submits `DETACH DELETE n` for a connected node
- **THEN** the node and every incident relationship are removed

#### Scenario: Delete a non-entity

- **WHEN** a caller binds a scalar value and submits `DELETE` on it
- **THEN** the system raises a semantic query error and changes nothing

### Requirement: Mutation cardinality

Write clauses SHALL operate on match rows. An entity referenced by more than one row SHALL be mutated or deleted once per statement. Clauses SHALL execute in source order, and each clause SHALL observe the mutations of the clauses before it.

#### Scenario: Repeated node bound once

- **WHEN** two match rows bind the same node and a following `SET` assigns a property
- **THEN** the node is written once with the value from the final row

#### Scenario: Repeated node deleted once

- **WHEN** several match rows bind the same node and a following `DETACH DELETE` targets it
- **THEN** the node is deleted once and no missing-element error is raised

#### Scenario: Clause order is respected

- **WHEN** a statement sets a property and then removes it in a later clause
- **THEN** the property is absent from the committed data

### Requirement: Write results and summary

A statement MAY omit `RETURN` when it contains a write clause. In that case the result SHALL have no columns and no rows and SHALL expose a mutation summary with counts of created and deleted nodes and relationships and of property and label changes. When `RETURN` is present, the result SHALL carry projected rows and the same summary.

#### Scenario: Write without RETURN

- **WHEN** a caller submits `CREATE (n:Program)` without a `RETURN` clause
- **THEN** the result has no columns and no rows, and its summary reports one created node

#### Scenario: Summary counts

- **WHEN** a caller creates two nodes and one relationship in one statement
- **THEN** the summary reports two created nodes and one created relationship

#### Scenario: RETURN after a write

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Tron'}) RETURN n.designation AS name`
- **THEN** the result contains one row with `name` equal to `Tron` and a non-zero created count

### Requirement: Write atomicity

A statement classified as a write SHALL execute in one implicit `BEGIN IMMEDIATE` transaction. Success SHALL commit every mutation of that statement. Any failure SHALL roll back every mutation of that statement and leave no transaction open. A write statement executed through an active transaction SHALL participate in that transaction without opening another.

#### Scenario: Commit

- **WHEN** a multi-clause write statement completes successfully
- **THEN** every mutation is visible to later reads

#### Scenario: Rollback on failure

- **WHEN** a write statement creates a node and a later clause fails
- **THEN** the node is not present after the error is raised

#### Scenario: No transaction left open

- **WHEN** a write statement fails
- **THEN** the graph handle remains usable and able to start a new transaction

#### Scenario: Inside an active transaction

- **WHEN** a caller executes a write statement through `Transaction.query`
- **THEN** the mutations are visible inside the transaction and are undone by its rollback

### Requirement: Write value validation

Property values assigned by a write clause SHALL satisfy the stored value rules: booleans, signed 64-bit integers, finite floats, strings, and homogeneous lists of those scalars. Assigning null SHALL remove the property. A value that violates these rules SHALL raise a query execution error and SHALL change nothing.

#### Scenario: Parameter value accepted

- **WHEN** a caller creates a node with a list parameter of integers
- **THEN** the list is stored and returned unchanged

#### Scenario: Invalid parameter rejected

- **WHEN** a caller assigns a parameter holding a mapping or a nested list
- **THEN** the system raises a query execution error and commits nothing

#### Scenario: Null assignment removes

- **WHEN** a `SET` assigns null to an existing property
- **THEN** the property is removed rather than stored as null

#### Scenario: Non-finite number rejected

- **WHEN** a caller assigns a parameter holding NaN or infinity
- **THEN** the system raises a query execution error and commits nothing

### Requirement: Write error mapping

Domain and storage failures encountered while executing a write statement SHALL be raised as query execution errors. Element-specific failures, including a missing element or a protected deletion, SHALL NOT escape as storage or domain exceptions, and raw SQLite exceptions SHALL NOT escape.

#### Scenario: Missing element after deletion

- **WHEN** one clause deletes an element and a later clause reads or writes it
- **THEN** the system raises a query execution error with a source position where available

#### Scenario: Protected deletion

- **WHEN** a `DELETE` targets a connected node without `DETACH DELETE`
- **THEN** the system raises a query execution error rather than a connected-node domain error

#### Scenario: Raw storage error wrapped

- **WHEN** SQLite reports a failure during a write statement
- **THEN** the caller receives a query execution error and no raw SQLite exception

## MODIFIED Requirements

### Requirement: Core dialect profile

A statement SHALL be a non-empty ordered sequence of clauses, each with exactly one path pattern. At most one `MATCH` clause SHALL appear, before any write clause, and `WHERE` SHALL follow `MATCH`. `RETURN` SHALL be optional, at most once, and final; it SHALL carry `DISTINCT`, `ORDER BY`, `SKIP`, and `LIMIT`. A read statement SHALL require `MATCH` and `RETURN`. Unsupported statements and forms SHALL be rejected, never ignored.

#### Scenario: Minimal query

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name`
- **THEN** the statement is accepted and returns one row per matching node

#### Scenario: Unsupported pattern form

- **WHEN** a caller submits a variable-length pattern such as `MATCH (a)-[r*1..3]->(b) RETURN b`
- **THEN** the system raises a query error before execution

#### Scenario: Unsupported clause

- **WHEN** a caller submits a statement using `OPTIONAL MATCH`, `WITH`, `UNWIND`, or a subquery
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

### Requirement: Prepared queries

`Graph.prepare` SHALL parse and validate a statement once and return a `PreparedQuery` whose `execute` method may run repeatedly with different parameters. A prepared statement MAY be a write statement. Preparation SHALL reject syntax and semantic errors before any execution, and the prepared columns SHALL be available before the first execution. Prepared columns SHALL be empty when the statement has no `RETURN` clause.

#### Scenario: Reuse a prepared query

- **WHEN** a caller prepares a statement and executes it twice with different parameter values
- **THEN** both executions use the same parsed statement and return their respective results

#### Scenario: Preparation rejects invalid syntax

- **WHEN** a caller prepares a statement with invalid syntax
- **THEN** the system raises a syntax query error and no query executes

#### Scenario: Columns before execution

- **WHEN** a caller prepares a valid statement with `RETURN`
- **THEN** the prepared query exposes its projected column names before execution

#### Scenario: Prepared write

- **WHEN** a caller prepares `CREATE (n:Program {designation: $name})` and executes it twice
- **THEN** the prepared columns are empty and both calls create a node

### Requirement: Transaction and lifecycle integration

`Transaction.query` SHALL execute read and write statements within the active transaction and SHALL observe that transaction's uncommitted writes. `Graph.query` and `PreparedQuery.execute` SHALL raise `TransactionError` while an explicit transaction is active. Using a closed graph handle SHALL raise `GraphClosedError`.

#### Scenario: Transaction sees its writes

- **WHEN** a caller creates a node inside a transaction and queries it through `Transaction.query`
- **THEN** the query returns the uncommitted node

#### Scenario: Transaction executes a write statement

- **WHEN** a caller executes a `CREATE` statement through `Transaction.query` and rolls the transaction back
- **THEN** the created node is absent afterwards

#### Scenario: Graph query blocked by active transaction

- **WHEN** a caller invokes `Graph.query` while an explicit transaction is active
- **THEN** the system raises `TransactionError` and the transaction remains usable

#### Scenario: Closed handle

- **WHEN** a caller invokes `Graph.query`, `Graph.prepare`, or `PreparedQuery.execute` on a closed graph
- **THEN** the system raises `GraphClosedError`

### Requirement: Result model

`QueryResult` SHALL expose ordered column names and iterate immutable rows. A row SHALL support lookup by column name. Result values SHALL be null, booleans, integers, floats, strings, lists, maps, `Node`, `Relationship`, or `Path` snapshots. Row order without `ORDER BY` SHALL be unspecified. A result SHALL expose a mutation summary, and a write statement without `RETURN` SHALL expose no columns and no rows.

#### Scenario: Row lookup

- **WHEN** a caller reads `row['name']` from a result row
- **THEN** the projected value for that column is returned

#### Scenario: Column metadata

- **WHEN** a caller inspects a result's columns
- **THEN** the projected column names appear in projection order

#### Scenario: Immutable result values

- **WHEN** a caller inspects an entity value after a later write
- **THEN** the value still reflects the query's snapshot

#### Scenario: Empty result for a write without RETURN

- **WHEN** a caller submits a write statement with no `RETURN` clause
- **THEN** the result has no columns and no rows

#### Scenario: Zero summary for a read

- **WHEN** a caller executes a read statement
- **THEN** every mutation count in its summary is zero

## REMOVED Requirements

### Requirement: Read-only query execution

**Reason**: The dialect becomes the single statement surface for reads and writes, so rejecting write clauses would leave every mutation outside the language. Execution of one statement, with classification of read versus write, is defined by the ADDED statement execution requirement and the MODIFIED core dialect profile.

**Migration**: Callers that relied on the rejection to validate untrusted input must validate statements themselves before execution. An existing statement without write clauses behaves exactly as before.
