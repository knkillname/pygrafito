# Spec Delta: graph-query-language

## MODIFIED Requirements

### Requirement: Core dialect profile

A statement SHALL be an ordered sequence of one or more linear segments separated by `NEXT`. Each segment SHALL contain an ordered sequence of read stages, optional write clauses, and a result clause, and every write clause SHALL follow every read stage within its segment.

#### Scenario: Minimal query

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name`
- **THEN** the statement is accepted and returns one row per matching node

#### Scenario: Chained read stages

- **WHEN** a caller submits `MATCH (a:Program) WITH a MATCH (a)-[:ALLIES_WITH]->(b) RETURN b`
- **THEN** the statement is accepted and the second stage joins against the first

#### Scenario: UNWIND as a row source

- **WHEN** a caller submits `UNWIND [1, 2] AS value RETURN value` without a `MATCH`
- **THEN** the statement is accepted and returns two rows

#### Scenario: FOR as a row source

- **WHEN** a caller submits `FOR value IN [1, 2] RETURN value` without a `MATCH`
- **THEN** the statement is accepted and returns two rows

#### Scenario: LET as a row source

- **WHEN** a caller submits `LET value = 1 RETURN value` without a `MATCH`, `FOR`, or write clause
- **THEN** the statement is accepted and returns one row

#### Scenario: FILTER stage

- **WHEN** a caller submits `MATCH (n:Program) FILTER n.cycles > 36 RETURN n`
- **THEN** the statement is accepted and returns only rows whose predicate is true

#### Scenario: Stage WHERE alias

- **WHEN** a caller submits `MATCH (n:Program) WITH n WHERE n.cycles > 36 RETURN n`
- **THEN** the stage filters its rows exactly as the `FILTER` spelling would

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
- **THEN** the system raises a query error before execution in the same segment

#### Scenario: Write clause before MATCH

- **WHEN** a caller submits `CREATE (n:Program) WITH n MATCH (m) RETURN m`
- **THEN** the system raises a query error before execution in the same segment

#### Scenario: Later segment reads after a write

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Rinzler'}) NEXT MATCH (m:Program {designation: 'Rinzler'}) RETURN m`
- **THEN** the statement is accepted, the later segment sees the created node, and one row is returned

#### Scenario: Read statement without RETURN

- **WHEN** a caller submits a read statement with matching stages but no `RETURN` or `FINISH`
- **THEN** the system raises a query error before execution

#### Scenario: Write after a WITH stage

- **WHEN** a caller submits `MATCH (a:Program) WITH a CREATE (b:Program {designation: 'Tron'}) RETURN b`
- **THEN** the statement is accepted and creates one node per row produced by the `WITH`

#### Scenario: NEXT requires a following segment

- **WHEN** a caller submits `MATCH (n:Program) NEXT`
- **THEN** the system raises a query error before execution

#### Scenario: NEXT after RETURN

- **WHEN** a caller submits `MATCH (n:Program) RETURN n NEXT RETURN n`
- **THEN** the statement is accepted and the final result comes from the last `RETURN`

#### Scenario: Intermediate RETURN feeds NEXT

- **WHEN** a caller submits `MATCH (n:Program) RETURN n AS element NEXT MATCH (element)-[:TRUSTS]->(m) RETURN m`
- **THEN** the later segment matches from the returned element column

#### Scenario: YIELD selects columns

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT YIELD name RETURN name`
- **THEN** the later segment sees `name` but not `cycles`

#### Scenario: Write-only segment passes bindings

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Rinzler'}) NEXT MATCH (n) RETURN n.designation`
- **THEN** the later segment sees the created node through the unchanged binding

#### Scenario: FINISH ends without a result

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'}) FINISH`
- **THEN** the node is created and the result has no rows

#### Scenario: FINISH is final

- **WHEN** a caller submits `MATCH (n:Program) FINISH NEXT MATCH (m:Program) RETURN m`
- **THEN** the system raises a query error before execution

#### Scenario: Read segment requires a result

- **WHEN** a caller submits `MATCH (n:Program) NEXT RETURN n`
- **THEN** the system raises a query error because the first read segment has no `RETURN` or `FINISH`

### Requirement: UNWIND clause

`FOR` SHALL expand a list-valued expression into one row per element and bind each element to a variable. `UNWIND <expression> AS <variable>` SHALL be accepted as an alias for `FOR <variable> IN <expression>`, including the ordinality suffix. A null value or an empty list SHALL produce no rows, and a value that is not a list SHALL raise a query error.

#### Scenario: Expand a parameter list

- **WHEN** a caller submits `UNWIND $names AS name RETURN name` with `["Kevin Flynn", "Quorra"]`
- **THEN** the result contains two rows in list order

#### Scenario: Canonical FOR spelling

- **WHEN** a caller submits `FOR name IN $names RETURN name` with the same parameter
- **THEN** the result is identical to the `UNWIND` alias

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

#### Scenario: Ordinality is gated

- **WHEN** a caller submits `FOR value IN [1, 2] WITH ORDINALITY index RETURN index`
- **THEN** the statement is accepted and returns indexes 1 and 2

#### Scenario: Zero-based offset

- **WHEN** a caller submits `FOR value IN [1, 2] WITH OFFSET index RETURN index`
- **THEN** the statement is accepted and returns indexes 0 and 1

#### Scenario: UNWIND accepts ordinality

- **WHEN** a caller submits `UNWIND [10, 20] AS value WITH ORDINALITY index RETURN value, index`
- **THEN** the result contains `(10, 1)` and `(20, 2)`

#### Scenario: Index name must be fresh

- **WHEN** a caller submits `FOR value IN [1] WITH ORDINALITY value RETURN value`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Ordinality and offset are exclusive

- **WHEN** a caller submits `FOR value IN [1] WITH ORDINALITY index WITH OFFSET other RETURN index`
- **THEN** the system raises a query error before execution

### Requirement: CREATE clause

`INSERT` SHALL create nodes and relationships from a pattern. `CREATE` SHALL be accepted as an alias for a data-modifying `INSERT` and SHALL NOT be accepted for a catalog operation. `INSERT` SHALL always create new elements and SHALL NOT match existing ones.

#### Scenario: Create a standalone node

- **WHEN** a caller submits `INSERT (n:Program {designation: 'Quorra', cycles: 37}) RETURN n`
- **THEN** one node with that label and those properties exists and is returned

#### Scenario: Create alias

- **WHEN** a caller submits the same statement with `CREATE`
- **THEN** the statement creates the same element with the same semantics

#### Scenario: Create a relationship between bound nodes

- **WHEN** a caller matches two nodes and submits `INSERT (a)-[r:ALLIES_WITH {since_cycle: 2020}]->(b)`
- **THEN** one relationship carrying that label and those properties is created between them

#### Scenario: Create an unlabeled relationship

- **WHEN** a caller matches two nodes and submits `INSERT (a)-[r]->(b)`
- **THEN** one relationship with an empty label set is created between them

#### Scenario: Create from every match row

- **WHEN** a `MATCH` binds three program nodes and a following `INSERT` adds a node
- **THEN** three new nodes are created

#### Scenario: Create from a row expression

- **WHEN** a caller unwinds rows and creates a node whose property is a row field
- **THEN** each created node stores that row's value

#### Scenario: Unbound relationship endpoint

- **WHEN** a caller submits `INSERT (a)-[r:ALLIES_WITH]->(b)` without binding `a` or `b`
- **THEN** the system raises a semantic query error and creates nothing

#### Scenario: Create does not match

- **WHEN** a caller submits the same `INSERT` statement twice
- **THEN** both calls create new nodes instead of reusing an existing one

#### Scenario: Catalog form is out of profile

- **WHEN** a caller submits `CREATE GRAPH` or `INSERT GRAPH`
- **THEN** the system raises a query error because catalog statements are out of profile

### Requirement: Projection and result columns

`RETURN` SHALL project expressions, aliases, and node, relationship, or path values. A column SHALL take its alias when present and otherwise its expression text. `RETURN ALL` SHALL be the explicit form of the default, and `RETURN *` SHALL project every variable in scope in introduction order. Duplicate column names SHALL be rejected, and `DISTINCT` SHALL remove duplicate projected rows.

#### Scenario: Scalar projection

- **WHEN** a caller returns `n.designation AS name, n.cycles`
- **THEN** the result has columns `name` and `n.cycles` in that order

#### Scenario: Entity projection

- **WHEN** a caller returns a node, relationship, or path variable
- **THEN** the result value is the corresponding immutable snapshot

#### Scenario: Return all bindings

- **WHEN** a caller matches `(a:Program)-[r:ALLIES_WITH]->(b:Program)` and returns `*`
- **THEN** the result has one column per bound variable in introduction order

#### Scenario: Explicit ALL

- **WHEN** a caller returns `ALL n.designation AS name`
- **THEN** the result is identical to the same projection without `ALL`

#### Scenario: Duplicate columns

- **WHEN** two projected items produce the same column name
- **THEN** the system raises a semantic query error

#### Scenario: Distinct projection

- **WHEN** a caller returns `DISTINCT n.designation`
- **THEN** equal projected values appear once

#### Scenario: No bindings is gated

- **WHEN** a caller submits `MATCH (n:Program) RETURN NO BINDINGS`
- **THEN** the result has zero columns and one empty row per matched node

#### Scenario: No bindings with empty input

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Nobody'}) RETURN NO BINDINGS`
- **THEN** the result has zero columns and no rows

#### Scenario: No bindings rejects modifiers

- **WHEN** a caller submits `MATCH (n:Program) RETURN NO BINDINGS ORDER BY n.designation`
- **THEN** the system raises a syntax error before execution

#### Scenario: No bindings in a write

- **WHEN** a caller submits `CREATE (n:Program) RETURN NO BINDINGS`
- **THEN** the node is created and the result has one empty row

### Requirement: Aggregation and grouping

The dialect SHALL support `count`, `collect`, `sum`, `avg`, `min`, and `max`, including `DISTINCT` variants. `count(*)` SHALL count rows, `count(expr)` SHALL count non-null values, and empty input SHALL yield count 0, an empty collected list, sum 0, and null for `avg`, `min`, and `max` when the projection is a global aggregate.

#### Scenario: Count rows

- **WHEN** a caller returns `count(*)` for a match with ten rows
- **THEN** the result is 10

#### Scenario: Grouped aggregation

- **WHEN** a caller returns `labels(n), count(*)` after matching nodes
- **THEN** one row is returned per distinct non-aggregate value

#### Scenario: Collect values

- **WHEN** a caller returns `collect(n.designation)`
- **THEN** the result is a list of non-null projected values in result order

#### Scenario: Empty aggregate input

- **WHEN** a query matches no rows and returns aggregates
- **THEN** the aggregate row contains count 0, an empty collected list, sum 0, and null for avg, min, and max

#### Scenario: Invalid aggregate use

- **WHEN** a projected expression mixes an aggregate with a non-grouped expression that is not a grouping key
- **THEN** the system raises a semantic query error

#### Scenario: Explicit grouping replaces implicit

- **WHEN** a caller returns `n.cycles, count(*) GROUP BY n.cycles`
- **THEN** one row is returned for each distinct value of `n.cycles`, even if another non-aggregate expression could have formed a different implicit key

#### Scenario: Explicit grouping without aggregates

- **WHEN** a caller returns `n.cycles GROUP BY n.cycles`
- **THEN** one row is returned per distinct value of `n.cycles`

## ADDED Requirements

### Requirement: NEXT and segment results

`NEXT` SHALL carry the preceding segment's `RETURN` table into the next segment. An optional `YIELD`
SHALL select and rename its columns; without `YIELD`, every preceding column SHALL remain in scope.
A non-final `RETURN` SHALL act as a projection and scope reset, and only the final segment's
`RETURN` or `FINISH` SHALL produce the statement result. `FINISH` SHALL be final.

#### Scenario: NEXT carries the return table

- **WHEN** a caller submits `MATCH (n:Program) RETURN n AS element NEXT MATCH (element)-[:TRUSTS]->(m) RETURN m`
- **THEN** the later segment matches from the returned element column

#### Scenario: YIELD narrows the next segment

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT YIELD name RETURN name`
- **THEN** the later segment sees `name` but not `cycles`

#### Scenario: FINISH cannot be followed

- **WHEN** a caller submits `MATCH (n:Program) FINISH NEXT MATCH (m:Program) RETURN m`
- **THEN** the system raises a query error before execution

### Requirement: Statement row sources and result requirements

A read segment SHALL end with `RETURN` or `FINISH`; a write segment MAY omit the result clause. A
read statement SHALL contain at least one row source and a final `RETURN` or `FINISH`; a write
statement MAY end with a write clause. Unsupported forms SHALL be rejected, never ignored.

#### Scenario: UNWIND supplies rows without MATCH

- **WHEN** a caller submits `UNWIND [1, 2] AS value RETURN value` without a `MATCH`
- **THEN** the statement is accepted and returns two rows

#### Scenario: Write-only statement needs no result

- **WHEN** a caller submits `CREATE (n:Program)` with no `MATCH` and no `RETURN`
- **THEN** the statement is accepted and executed

#### Scenario: Unsupported clause is rejected

- **WHEN** a caller submits a statement using `CALL { ... }`, `EXISTS { ... }`, `CASE`, a map literal, or `WITH *`
- **THEN** the system raises a query error before execution

### Requirement: UNWIND ordinality

`WITH ORDINALITY <name>` SHALL bind a one-based position and `WITH OFFSET <name>` SHALL bind a
zero-based position. The index name SHALL be fresh and distinct from the element variable, and the
two forms SHALL NOT be combined.

#### Scenario: ORDINALITY is one-based

- **WHEN** a caller submits `FOR value IN [1, 2] WITH ORDINALITY index RETURN index`
- **THEN** the statement is accepted and returns indexes 1 and 2

#### Scenario: OFFSET is zero-based

- **WHEN** a caller submits `FOR value IN [1, 2] WITH OFFSET index RETURN index`
- **THEN** the statement is accepted and returns indexes 0 and 1

### Requirement: UNWIND placement and scope

The element variable SHALL be fresh in the current scope. The element and index variables SHALL be
available to later clauses, and `FOR` or `UNWIND` SHALL be a read stage that precedes the result
clause within its segment.

#### Scenario: UNWIND cannot follow a write clause

- **WHEN** a caller submits `CREATE (n:Program) UNWIND [1] AS value RETURN value`
- **THEN** the system raises a query error before execution

### Requirement: CREATE element validation

A created node SHALL bind its variable for later clauses and `RETURN`. Labels and property maps
SHALL be validated before execution, and property values SHALL be non-aggregate expressions
evaluated against the current row.

#### Scenario: Created node binds its variable

- **WHEN** a caller submits `INSERT (n:Program {designation: 'Quorra', cycles: 37}) RETURN n`
- **THEN** one node with that label and those properties exists and is returned

#### Scenario: Created property uses the current row

- **WHEN** a caller unwinds rows and creates a node whose property is a row field
- **THEN** each created node stores that row's value

### Requirement: CREATE relationship constraints

A created relationship SHALL require both endpoint nodes to be already bound by a variable. A
created relationship SHALL carry the single label named in its pattern, or no label when the
pattern names none, and SHALL be directed.

#### Scenario: Unbound endpoint is rejected

- **WHEN** a caller submits `INSERT (a)-[r:ALLIES_WITH]->(b)` without binding `a` or `b`
- **THEN** the system raises a semantic query error and creates nothing

#### Scenario: Relationship may be unlabeled

- **WHEN** a caller matches two nodes and submits `INSERT (a)-[r]->(b)`
- **THEN** one relationship with an empty label set is created between them

### Requirement: RETURN NO BINDINGS extension

As a pygrafito extension, `RETURN NO BINDINGS` SHALL return zero columns and one empty row per input
binding, SHALL be final-only, and SHALL NOT combine with `DISTINCT`, `ALL`, `*`, `GROUP BY`, `ORDER
BY`, `OFFSET`, or `LIMIT`; GQL's canonical no-result form is `FINISH`.

#### Scenario: NO BINDINGS returns an empty row per binding

- **WHEN** a caller submits `MATCH (n:Program) RETURN NO BINDINGS`
- **THEN** the result has zero columns and one empty row per matched node

#### Scenario: NO BINDINGS rejects ORDER BY

- **WHEN** a caller submits `MATCH (n:Program) RETURN NO BINDINGS ORDER BY n.designation`
- **THEN** the system raises a syntax error before execution

### Requirement: Grouping keys

A non-aggregate `RETURN` expression SHALL form an implicit grouping key when the projection has no
explicit `GROUP BY`. With an explicit `GROUP BY`, the grouping keys SHALL be exactly the listed
keys.

#### Scenario: Non-aggregate projection groups rows

- **WHEN** a caller returns `labels(n), count(*)` after matching nodes
- **THEN** one row is returned per distinct non-aggregate value

#### Scenario: Explicit GROUP BY fixes the keys

- **WHEN** a caller returns `n.cycles, count(*) GROUP BY n.cycles`
- **THEN** one row is returned for each distinct value of `n.cycles`, even if another non-aggregate expression could have formed a different implicit key
