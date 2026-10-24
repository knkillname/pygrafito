# Spec Delta

## ADDED Requirements

### Requirement: UNWIND clause

`UNWIND` SHALL expand a list-valued expression into one row per element and bind each element to a variable. A null value or an empty list SHALL produce no rows. A value that is not a list SHALL raise a query error. The variable SHALL be available to later clauses, and the clause SHALL be a read stage that precedes every write clause and `RETURN`.

#### Scenario: Expand a parameter list

- **WHEN** a caller submits `UNWIND $names AS name RETURN name` with `["Kevin Flynn", "Quorra"]`
- **THEN** the result contains two rows in list order

#### Scenario: Expand a list literal

- **WHEN** a caller submits `UNWIND [36, 37] AS cycles RETURN cycles`
- **THEN** the result contains one row for each integer

#### Scenario: Expand a list of mappings

- **WHEN** a caller unwinds a list of mappings and returns `row.designation`
- **THEN** each mapping contributes one row and its field is read as a value

#### Scenario: Empty list

- **WHEN** a caller submits `UNWIND [] AS value RETURN value`
- **THEN** the result contains no rows

#### Scenario: Null value

- **WHEN** a caller unwinds a null parameter
- **THEN** the result contains no rows

#### Scenario: Non-list literal

- **WHEN** a caller submits `UNWIND 36 AS value RETURN value`
- **THEN** the system raises a query error before execution

#### Scenario: Non-list runtime value

- **WHEN** a caller unwinds a parameter whose value is a string or mapping
- **THEN** the system raises an execution query error

#### Scenario: Variable already in scope

- **WHEN** a caller submits `MATCH (n:Program) UNWIND [1] AS n RETURN n`
- **THEN** the system raises a semantic query error before execution

#### Scenario: UNWIND after a write clause

- **WHEN** a caller submits `CREATE (n:Program) UNWIND [1] AS value RETURN value`
- **THEN** the system raises a query error before execution

### Requirement: UNWIND as a row source

A statement SHALL accept `UNWIND` as its only row source. A read statement with `UNWIND` and `RETURN` SHALL be valid without a `MATCH`, and a write statement MAY begin with `UNWIND` and omit both `MATCH` and `RETURN`.

#### Scenario: Read without MATCH

- **WHEN** a caller submits `UNWIND [1, 2] AS value RETURN value`
- **THEN** the statement is accepted and returns two rows

#### Scenario: Write without MATCH

- **WHEN** a caller submits `UNWIND $rows AS row CREATE (n:Program {designation: row.designation})`
- **THEN** the statement is accepted and creates one node per row

#### Scenario: No row source and no write

- **WHEN** a caller submits `RETURN 1 AS value` without a `MATCH`, `UNWIND`, or write clause
- **THEN** the system raises a query error before execution

### Requirement: MERGE matching and creation

`MERGE` SHALL match one fixed-length path pattern as a whole. When the pattern matches, `MERGE` SHALL bind the existing elements and create nothing. When it does not match, `MERGE` SHALL create every unbound node and relationship in the pattern and reuse variables bound by earlier clauses. `MERGE` SHALL produce one row per match or one created row.

#### Scenario: Match an existing node

- **WHEN** a caller submits `MERGE (n:Program {designation: 'Quorra'})` and a matching node exists
- **THEN** no node is created and `n` binds the existing node

#### Scenario: Create a missing node

- **WHEN** a caller submits `MERGE (n:Program {designation: 'Quorra'})` and no matching node exists
- **THEN** one node is created, labeled `Program`, with that property, and `n` binds it

#### Scenario: Match an existing relationship

- **WHEN** a caller merges a relationship pattern whose endpoints and relationship already exist
- **THEN** no element is created and the relationship variable binds the existing relationship

#### Scenario: Create a relationship between bound nodes

- **WHEN** a caller matches two nodes and merges a relationship between them
- **THEN** the endpoints are reused and one relationship is created when no matching relationship exists

#### Scenario: No partial reuse

- **WHEN** a merged relationship pattern does not match as a whole and its first node is not bound by an earlier clause
- **THEN** `MERGE` creates a new node for that position instead of reusing an equivalent existing node

#### Scenario: Repeated variable

- **WHEN** a caller submits `MERGE (a:Program {designation: 'Rinzler'})-[:MONITORS]->(a)`
- **THEN** one node is created and the relationship is a self-loop on it

#### Scenario: Return the merged element

- **WHEN** a caller appends `RETURN n.designation AS name` to a successful `MERGE`
- **THEN** the result contains one row with the matched or created designation

### Requirement: MERGE with multiple input rows

`MERGE` SHALL run once per input row, in order, and a creation made for one row SHALL be visible to later rows in the same statement. When several input rows describe the same pattern, the first SHALL create it and later rows SHALL match it. A pattern that matches several existing rows SHALL produce several rows and SHALL NOT create.

#### Scenario: Batch upsert

- **WHEN** a caller unwinds rows with duplicate designations into a `MERGE` on that property
- **THEN** one node exists per distinct designation and each input row produces one result row

#### Scenario: Later row matches an earlier creation

- **WHEN** two rows in one `UNWIND` carry the same merge key
- **THEN** the second row matches the node created by the first instead of creating another

#### Scenario: Several existing matches

- **WHEN** two nodes satisfy a merged node pattern
- **THEN** the result contains two rows and no node is created

#### Scenario: Failure rolls back the statement

- **WHEN** a later row of a `MERGE` statement fails
- **THEN** every creation made by that statement is rolled back

### Requirement: MERGE pattern restrictions

A `MERGE` pattern SHALL contain one path, SHALL NOT bind a path variable, SHALL NOT use a quantified relationship, and SHALL use exactly one relationship type with the outgoing direction for every relationship it can create. `MERGE` SHALL reject a relationship variable already bound by an earlier clause.

#### Scenario: Multiple patterns rejected

- **WHEN** a caller submits `MERGE (a:Program), (b:Program)`
- **THEN** the system raises a query error before execution

#### Scenario: Path variable rejected

- **WHEN** a caller submits `MERGE path = (a:Program)-[:TRUSTS]->(b:Program)`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Quantified relationship rejected

- **WHEN** a caller submits `MERGE (a)-[:ALLIES_WITH*1..2]->(b)`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Undirected or incoming relationship rejected

- **WHEN** a caller submits a `MERGE` relationship with `--` or `<--`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Missing relationship type rejected

- **WHEN** a caller submits `MERGE (a:Program)-[]->(b:Program)`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Bound relationship variable rejected

- **WHEN** a caller merges a relationship variable already bound by an earlier clause
- **THEN** the system raises a semantic query error before execution

### Requirement: Conditional updates for MERGE

A `MERGE` MAY carry at most one `ON CREATE SET` and one `ON MATCH SET`, in that order. `ON CREATE SET` SHALL apply only to rows the clause created, and `ON MATCH SET` only to rows it matched. Assignments SHALL follow `SET` rules and SHALL be evaluated once per output row.

#### Scenario: ON CREATE only

- **WHEN** a `MERGE` creates a node and carries `ON CREATE SET n.cycles = 40`
- **THEN** the created node stores `40`

#### Scenario: ON MATCH only

- **WHEN** a `MERGE` matches an existing node and carries `ON MATCH SET n.cycles = 41`
- **THEN** the matched node stores `41` and no node is created

#### Scenario: Mixed rows

- **WHEN** one statement merges a mix of existing and missing keys with both conditional clauses
- **THEN** matched rows receive only the `ON MATCH` assignments and created rows only the `ON CREATE` assignments

#### Scenario: Duplicate conditional clause

- **WHEN** a caller submits two `ON CREATE SET` clauses on one `MERGE`
- **THEN** the system raises a query error before execution

#### Scenario: Reversed order

- **WHEN** a caller writes `ON MATCH SET` before `ON CREATE SET`
- **THEN** the system raises a query error before execution

#### Scenario: Conditional assignment from the row

- **WHEN** a caller writes `ON CREATE SET n.designation = row.designation`
- **THEN** the created node stores the current row's value

#### Scenario: Conditional null removal

- **WHEN** a conditional assignment sets a property to null
- **THEN** the property is removed, following `SET` rules

### Requirement: Pattern property expressions

A pattern property value SHALL be a non-aggregate expression evaluated against the current row and the statement parameters. A referenced variable SHALL be in scope before the pattern. In `MATCH`, a null value SHALL match nothing. In `CREATE`, a null value SHALL be omitted from the created properties. In `MERGE`, a null value SHALL raise a query error.

#### Scenario: Match from a row value

- **WHEN** a caller unwinds rows and matches a node whose property equals `row.designation`
- **THEN** only nodes whose stored value equals that row's value are bound

#### Scenario: Create from a row value

- **WHEN** a caller unwinds rows and creates a node whose property is a row field
- **THEN** each created node stores its row's value

#### Scenario: Merge from a row value

- **WHEN** a caller unwinds rows and merges a node whose property is a row field
- **THEN** the pattern matches or creates using that row's value

#### Scenario: Null in a match pattern

- **WHEN** a pattern property expression evaluates to null during `MATCH`
- **THEN** the pattern matches no element

#### Scenario: Null in a create pattern

- **WHEN** a `CREATE` property expression evaluates to null
- **THEN** the property is omitted from the created element

#### Scenario: Null in a merge pattern

- **WHEN** a `MERGE` property expression evaluates to null
- **THEN** the system raises a query error and changes nothing

#### Scenario: Aggregate rejected

- **WHEN** a pattern property value contains an aggregate function
- **THEN** the system raises a semantic query error before execution

#### Scenario: Forward reference rejected

- **WHEN** a pattern property value references a variable the pattern itself introduces
- **THEN** the system raises a semantic query error before execution

## MODIFIED Requirements

### Requirement: Statement execution

The system SHALL execute exactly one statement per call and return a materialized `QueryResult`. A statement MAY contain write clauses and SHALL be classified as a write when it contains `CREATE`, `MERGE`, `SET`, `REMOVE`, `DELETE`, or `DETACH DELETE`. A read statement SHALL change no data. `Graph.query` SHALL parse and execute in one step, and `Graph.prepare` SHALL return a reusable `PreparedQuery` for either kind.

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

### Requirement: Core dialect profile

A statement SHALL be an ordered sequence of read stages, optional write clauses, and an optional final `RETURN`. A read stage SHALL be `MATCH`, `OPTIONAL MATCH`, `UNWIND`, or `WITH`. Every write clause SHALL follow every read stage, and `RETURN` SHALL be at most once and final. A read statement SHALL contain at least one row source and a `RETURN`; a write statement MAY omit both. Unsupported forms SHALL be rejected, never ignored.

#### Scenario: Minimal query

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name`
- **THEN** the statement is accepted and returns one row per matching node

#### Scenario: Chained read stages

- **WHEN** a caller submits `MATCH (a:Program) WITH a MATCH (a)-[:ALLIES_WITH]->(b) RETURN b`
- **THEN** the statement is accepted and the second stage joins against the first

#### Scenario: UNWIND as a row source

- **WHEN** a caller submits `UNWIND [1, 2] AS value RETURN value` without a `MATCH`
- **THEN** the statement is accepted and returns two rows

#### Scenario: MERGE without MATCH

- **WHEN** a caller submits `MERGE (n:Program {designation: 'Tron'})` without a `MATCH`
- **THEN** the statement is accepted and executes as a write

#### Scenario: Unsupported pattern form

- **WHEN** a caller submits `MATCH (a)-[*]->(b) RETURN b` or `MATCH (a)-[*1..]->(b) RETURN b`
- **THEN** the system raises a semantic query error before execution because the upper bound is missing

#### Scenario: Unsupported clause

- **WHEN** a caller submits a statement using `CALL { ... }`, `EXISTS { ... }`, `CASE`, a map literal, or `WITH *`
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

### Requirement: CREATE clause

`CREATE` SHALL create nodes and relationships from a pattern. A created node SHALL bind its variable for later clauses and `RETURN`. A created relationship SHALL require both endpoint nodes to be already bound by a variable. `CREATE` SHALL always create new elements and SHALL NOT match existing ones. Labels and property maps SHALL be validated before execution, and property values SHALL be non-aggregate expressions evaluated against the current row.

#### Scenario: Create a standalone node

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Quorra', cycles: 37}) RETURN n`
- **THEN** one node with that label and those properties exists and is returned

#### Scenario: Create a relationship between bound nodes

- **WHEN** a caller matches two nodes and submits `CREATE (a)-[r:ALLIES_WITH {since_cycle: 2020}]->(b)`
- **THEN** one relationship of that type and those properties is created between them

#### Scenario: Create from every match row

- **WHEN** a `MATCH` binds three program nodes and a following `CREATE` adds a node
- **THEN** three new nodes are created

#### Scenario: Create from a row expression

- **WHEN** a caller unwinds rows and creates a node whose property is a row field
- **THEN** each created node stores that row's value

#### Scenario: Unbound relationship endpoint

- **WHEN** a caller submits `CREATE (a)-[r:ALLIES_WITH]->(b)` without binding `a` or `b`
- **THEN** the system raises a semantic query error and creates nothing

#### Scenario: Create does not match

- **WHEN** a caller submits the same `CREATE` statement twice
- **THEN** both calls create new nodes instead of reusing an existing one
