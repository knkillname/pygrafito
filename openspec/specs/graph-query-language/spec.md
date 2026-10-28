# graph-query-language Specification

## Purpose

Defines a pattern-matching graph query dialect for `pygrafito` that reads and writes a property graph: its statement shape, pattern semantics, write clauses, mutation cardinality, value model, filtering, projection, aggregation, parameters, result values, and errors.

## Requirements

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


### Requirement: Node patterns

A node pattern SHALL bind an optional variable, zero or more labels, and an optional property map. Labels SHALL match as a conjunction, and property map entries SHALL match stored values using the dialect's equality semantics.

#### Scenario: Labels and properties

- **WHEN** a caller matches `(p:Program:ISO {designation: 'Quorra'})`
- **THEN** only nodes carrying both labels and the matching property value are bound

#### Scenario: Arbitrary property key

- **WHEN** a caller matches a property whose key contains a dot or a space using a backtick-quoted identifier
- **THEN** the exact stored key is matched

#### Scenario: Anonymous node

- **WHEN** a caller omits the variable from a node pattern
- **THEN** the node participates in the path but is not available for projection


### Requirement: Relationship patterns

A relationship pattern SHALL bind an optional variable, zero or more relationship label filters, a direction, and an optional property map. A label filter SHALL match a relationship carrying that label. The direction forms `-->`, `<--`, and `--` SHALL follow directed relationships whose start is the current node, directed relationships whose end is the current node, and every incident relationship respectively. An undirected relationship SHALL match `--` and SHALL NOT match `-->` or `<--`. A bound relationship SHALL preserve its stored endpoints, labels, and directed flag.

#### Scenario: Outgoing relationship

- **WHEN** a caller matches `(a)-[r:ALLIES_WITH]->(b)`
- **THEN** only directed relationships carrying that label whose stored start is the current node are followed

#### Scenario: Incoming relationship

- **WHEN** a caller matches `(a)<-[r:ALLIES_WITH]-(b)`
- **THEN** only directed relationships carrying that label whose stored end is the current node are followed

#### Scenario: Undirected relationship

- **WHEN** a caller matches `(a)-[r]-(b)`
- **THEN** every incident relationship is followed, including an undirected relationship

#### Scenario: Undirected edge is not matched by an arrow

- **WHEN** a caller matches `(a)-[r]->(b)` and the relationship between the nodes is undirected
- **THEN** the relationship does not match

#### Scenario: Type alternatives

- **WHEN** a caller matches `[r:ALLIES_WITH|TRUSTS]`
- **THEN** only relationships carrying either listed label are followed

#### Scenario: Label alternatives

- **WHEN** a caller matches `[r:ALLIES_WITH]` and the relationship also carries TRUSTS
- **THEN** the relationship matches because it carries the requested label

#### Scenario: Relationship property filter

- **WHEN** a caller matches `[r {since_cycle: 2020}]`
- **THEN** only relationships carrying that exact property value are followed

#### Scenario: Bound relationship metadata

- **WHEN** a relationship variable binds a relationship carrying several labels
- **THEN** the bound snapshot reports all labels and the directed flag


### Requirement: Variable-length relationship patterns

A relationship pattern MAY carry a quantifier: `*n` for exactly `n` hops, `*n..m` for a bounded range, or `*0..m` to include the zero-hop case. Every hop SHALL apply the pattern's label filters, direction, and property map. The upper bound SHALL be explicit; a bare `*` or an open-ended `*n..` SHALL be rejected with a query error. Bounds SHALL be non-negative integers with `n` less than or equal to `m`.

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

- **WHEN** a quantified pattern carries labels, a direction, and a property map
- **THEN** every traversed relationship satisfies all of them

#### Scenario: Undirected hop

- **WHEN** a caller matches a quantified pattern with `--` and the route uses an undirected relationship
- **THEN** the undirected relationship may be traversed from either endpoint

#### Scenario: Arrow excludes undirected hops

- **WHEN** a caller matches a quantified pattern with `-->` and the route would require an undirected relationship
- **THEN** that route is not returned

#### Scenario: Undirected relationship may not repeat

- **WHEN** continuing a quantified path would reuse an undirected relationship already in that path
- **THEN** that extension is not returned

#### Scenario: Unbounded quantifier is rejected

- **WHEN** a caller writes `MATCH (a)-[*]->(b) RETURN b` or `MATCH (a)-[*1..]->(b) RETURN b`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Invalid bounds are rejected

- **WHEN** a caller writes a negative bound or a lower bound greater than the upper bound
- **THEN** the system raises a query error before execution


### Requirement: Pattern variables and paths

A variable used more than once in a pattern SHALL refer to the same node or relationship. A path variable SHALL expose the matched nodes and relationships in traversal order, with nodes ordered from the path start to the path end even when relationships are traversed against their stored direction or are undirected.

#### Scenario: Repeated node variable

- **WHEN** a caller matches `(a)-[r]->(a)`
- **THEN** only self-loop relationships bind, because both node positions refer to the same node

#### Scenario: Path variable

- **WHEN** a caller matches `p = (a)-[r]->(b)` and returns `p`
- **THEN** the result value is a `Path` whose nodes run from `a` to `b` and whose relationships are in traversal order

#### Scenario: Incoming path order

- **WHEN** a path is built through an incoming relationship
- **THEN** its node sequence still runs from the start node to the end node

#### Scenario: Undirected path order

- **WHEN** a path includes an undirected relationship
- **THEN** its node sequence still runs from the path start to the path end


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


### Requirement: Pattern match row semantics

`MATCH` SHALL produce one row per distinct match of the pattern. Parallel relationships,
self-loops, diamonds, and cycles SHALL produce the matches implied by the graph, and duplicate
projected rows SHALL be removed only when `DISTINCT` is requested.

#### Scenario: Diamond produces two rows

- **WHEN** two distinct two-hop routes connect the start node to the same end node and both are matched
- **THEN** two rows are returned

#### Scenario: Parallel relationships are distinct

- **WHEN** two separate relationships of the same type connect the same pair of nodes
- **THEN** the pattern produces one row per relationship

#### Scenario: Self-loop

- **WHEN** a relationship starts and ends at the same node and the pattern matches it
- **THEN** the self-loop produces a binding

#### Scenario: Distinct removes duplicate rows

- **WHEN** the projected values of two matched rows are equal and `DISTINCT` is requested
- **THEN** only one of those rows is returned


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


### Requirement: CREATE clause

`CREATE` SHALL create nodes and relationships from a pattern. A created node SHALL bind its variable for later clauses and `RETURN`. A created relationship SHALL require both endpoint nodes to be already bound by a variable. `CREATE` SHALL always create new elements and SHALL NOT match existing ones. A created relationship SHALL carry the single label named in its pattern, or no label when the pattern names none, and SHALL be directed. Labels and property maps SHALL be validated before execution, and property values SHALL be non-aggregate expressions evaluated against the current row.

#### Scenario: Create a standalone node

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Quorra', cycles: 37}) RETURN n`
- **THEN** one node with that label and those properties exists and is returned

#### Scenario: Create a relationship between bound nodes

- **WHEN** a caller matches two nodes and submits `CREATE (a)-[r:ALLIES_WITH {since_cycle: 2020}]->(b)`
- **THEN** one relationship carrying that label and those properties is created between them

#### Scenario: Create an unlabeled relationship

- **WHEN** a caller matches two nodes and submits `CREATE (a)-[r]->(b)`
- **THEN** one relationship with an empty label set is created between them

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


### Requirement: SET clause

`SET` SHALL assign a property from an expression and SHALL add labels to a bound node or relationship. Assigning a null value SHALL remove the property. Labels added with `SET` SHALL be static identifiers. `SET` SHALL reject an unbound variable and SHALL reject a label added to a value that is not a node or relationship.

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

#### Scenario: Add a relationship label

- **WHEN** a caller submits `MATCH ()-[r:ALLIES_WITH]->() SET r:TRUSTS`
- **THEN** each matched relationship carries both `ALLIES_WITH` and `TRUSTS`

#### Scenario: Unbound variable

- **WHEN** a caller submits `SET n.cycles = 1` without binding `n`
- **THEN** the system raises a semantic query error and changes nothing

#### Scenario: Label on a non-element

- **WHEN** a caller unwinds a scalar value and submits `SET` with a label on that variable
- **THEN** the system raises a semantic query error and changes nothing


### Requirement: REMOVE clause

`REMOVE` SHALL remove a property or one or more labels from a bound element. Removing a property or label that is absent SHALL leave the element unchanged. `REMOVE` SHALL reject an unbound variable.

#### Scenario: Remove a property

- **WHEN** a caller submits `MATCH (n:Program) REMOVE n.cycles`
- **THEN** the property is absent from each matched node

#### Scenario: Remove a label

- **WHEN** a caller submits `MATCH (n:Program) REMOVE n:ISO`
- **THEN** `ISO` is absent from each matched node's labels

#### Scenario: Remove a relationship label

- **WHEN** a caller submits `MATCH ()-[r:ALLIES_WITH]->() REMOVE r:TRUSTS`
- **THEN** `TRUSTS` is absent from each matched relationship's labels

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


### Requirement: Value equality and comparison

The dialect SHALL treat integers and floats as one numeric family for equality and ordering, while booleans SHALL remain distinct from numbers. Strings SHALL compare by Unicode code point, and lists SHALL compare element-wise with order significant. Null SHALL propagate through comparison operators.

#### Scenario: Numeric equality

- **WHEN** a caller compares the integer `36` with the float `36.0`
- **THEN** the comparison reports equality

#### Scenario: Boolean is not a number

- **WHEN** a caller compares the boolean `true` with the integer `1`
- **THEN** the comparison does not report equality

#### Scenario: List order matters

- **WHEN** a caller compares the list `[1, 2]` with the list `[2, 1]`
- **THEN** the comparison does not report equality

#### Scenario: String comparison is case-sensitive

- **WHEN** a caller compares the strings `'Quorra'` and `'quorra'`
- **THEN** the comparison does not report equality


### Requirement: Null semantics

A missing property SHALL evaluate to null. Comparisons, arithmetic, string predicates, and `IN` SHALL propagate null. `IS NULL` and `IS NOT NULL` SHALL always return a boolean. `WHERE` SHALL keep only rows whose predicate is true; false and null SHALL both be discarded.

#### Scenario: Missing property is null

- **WHEN** a caller projects a property that the matched element does not have
- **THEN** the projected value is null

#### Scenario: Null predicate is discarded

- **WHEN** a `WHERE` predicate evaluates to null for a row
- **THEN** that row is not returned

#### Scenario: Null test

- **WHEN** a caller filters with `n.designation IS NULL` or `n.designation IS NOT NULL`
- **THEN** the predicate returns a boolean and the matching rows are returned

#### Scenario: Null in aggregation

- **WHEN** an aggregate receives null inputs
- **THEN** `count(expr)`, `sum`, `avg`, `min`, `max`, and `collect` ignore those inputs, while `count(*)` still counts rows


### Requirement: Filtering expressions

`WHERE` SHALL support comparison operators, `AND`, `OR`, `NOT`, `IN`, `IS NULL`, `IS NOT NULL`, `STARTS WITH`, `ENDS WITH`, `CONTAINS`, arithmetic, list literals, parameters, and parenthesized expressions. String predicates SHALL be case-sensitive.

#### Scenario: Numeric range

- **WHEN** a caller filters with `p.cycles >= 36 AND p.cycles < 40`
- **THEN** only nodes whose numeric property falls in that range are returned

#### Scenario: Membership

- **WHEN** a caller filters with `p.designation IN ['Quorra', 'Tron']`
- **THEN** only nodes with either exact string value are returned

#### Scenario: String predicate

- **WHEN** a caller filters with `p.designation STARTS WITH 'Qu'`
- **THEN** only values beginning with the exact case-sensitive prefix are returned

#### Scenario: Boolean precedence

- **WHEN** a caller combines `AND`, `OR`, and `NOT` in one predicate
- **THEN** `NOT` binds tighter than `AND`, and `AND` binds tighter than `OR`


### Requirement: Scalar functions

The core function set SHALL include `id`, `labels`, `type`, `properties`, `keys`, `size`, `coalesce`, `toInteger`, `toFloat`, `toString`, `lower`, `upper`, `trim`, `abs`, `concat`, `startNode`, and `endNode`. Function names SHALL be case-insensitive, and `labels` and `keys` SHALL return sorted lists. `labels` SHALL accept a node or a relationship. `type` SHALL return the lexicographically first label of a relationship, or null when the relationship has no labels.

#### Scenario: Entity metadata

- **WHEN** a caller projects `id(n)`, `labels(n)`, or `properties(n)`
- **THEN** the result contains the element id, its sorted labels, or its property mapping respectively

#### Scenario: Relationship metadata

- **WHEN** a caller projects `type(r)`, `startNode(r)`, or `endNode(r)`
- **THEN** the result contains the relationship's first sorted label, or null when it has no labels, or the corresponding node snapshot

#### Scenario: Relationship labels

- **WHEN** a caller projects `labels(r)` for a relationship carrying several labels
- **THEN** the result contains every label in sorted order

#### Scenario: Conversion

- **WHEN** a caller applies `toInteger`, `toFloat`, or `toString` to a compatible scalar
- **THEN** the converted value is returned, and an impossible conversion yields null

#### Scenario: Unknown function

- **WHEN** a caller uses a function name that is not in the core set
- **THEN** the system raises a semantic query error before execution


### Requirement: Arithmetic

The dialect SHALL support `+`, `-`, `*`, `/`, `%`, and unary minus on numeric values. `/` SHALL always return a float. Integer overflow and division by zero SHALL raise a query execution error rather than returning a coerced or partial value.

#### Scenario: Numeric promotion

- **WHEN** a caller adds an integer and a float
- **THEN** the result is a float

#### Scenario: Division returns a float

- **WHEN** a caller divides two integers
- **THEN** the result is a float

#### Scenario: Division by zero

- **WHEN** a caller divides by zero
- **THEN** the system raises a query execution error

#### Scenario: Integer overflow

- **WHEN** an arithmetic result falls outside the signed 64-bit range
- **THEN** the system raises a query execution error


### Requirement: Projection and result columns

`RETURN` SHALL project expressions, aliases, and node, relationship, or path values. A column SHALL take its alias when present and otherwise its expression text. Duplicate column names SHALL be rejected. `DISTINCT` SHALL remove duplicate projected rows.

#### Scenario: Scalar projection

- **WHEN** a caller returns `n.designation AS name, n.cycles`
- **THEN** the result has columns `name` and `n.cycles` in that order

#### Scenario: Entity projection

- **WHEN** a caller returns a node, relationship, or path variable
- **THEN** the result value is the corresponding immutable snapshot

#### Scenario: Duplicate columns

- **WHEN** two projected items produce the same column name
- **THEN** the system raises a semantic query error

#### Scenario: Distinct projection

- **WHEN** a caller returns `DISTINCT n.designation`
- **THEN** equal projected values appear once


### Requirement: Aggregation and grouping

The dialect SHALL support `count`, `collect`, `sum`, `avg`, `min`, and `max`, including `DISTINCT` variants. Non-aggregate `RETURN` expressions SHALL form implicit grouping keys. `count(*)` SHALL count rows, while `count(expr)` SHALL count non-null values. Empty input SHALL yield count 0, collect an empty list, sum 0, and null for avg, min, and max.

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


### Requirement: Ordering and pagination

`ORDER BY` SHALL accept one or more expressions or projected aliases with optional `ASC` or `DESC`, defaulting to ascending. Nulls SHALL sort last in ascending order and first in descending order. `SKIP` and `LIMIT` SHALL accept non-negative integers or parameters and SHALL reject negative or non-integer values.

#### Scenario: Ascending and descending order

- **WHEN** a caller orders by a property ascending and then descending
- **THEN** rows are returned in the corresponding order

#### Scenario: Null ordering

- **WHEN** an ordered expression is null for some rows
- **THEN** those rows sort last in ascending order and first in descending order

#### Scenario: Pagination

- **WHEN** a caller applies `SKIP 2 LIMIT 5`
- **THEN** at most five rows are returned after skipping the first two

#### Scenario: Parameterized pagination

- **WHEN** `SKIP` or `LIMIT` receives a parameter
- **THEN** the parameter value is validated as a non-negative integer before execution


### Requirement: Parameters and injection safety

The dialect SHALL bind `$name` parameters from a mapping. Parameter values SHALL be bound as data and SHALL never be interpolated into SQL text or used as identifiers. A referenced parameter that is missing SHALL raise a semantic query error. Extra parameters SHALL be ignored.

#### Scenario: Bind a value

- **WHEN** a caller passes a string containing quotes as a parameter value
- **THEN** the value is matched literally and does not change the query structure

#### Scenario: Missing parameter

- **WHEN** a statement references `$cycles` and the parameter mapping omits it
- **THEN** the system raises a semantic query error before execution

#### Scenario: Parameters are not identifiers

- **WHEN** a parameter appears where a label, relationship type, or property key is required
- **THEN** the system raises a query error


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


### Requirement: Query errors and positions

The system SHALL raise `QuerySyntaxError`, `QuerySemanticError`, or `QueryExecutionError`, all subclasses of `QueryError` and `PygrafitoError`. Syntax and semantic errors SHALL report a line and column when a source position is available. Raw SQLite exceptions SHALL NOT escape; execution failures SHALL be raised as a query execution error.

#### Scenario: Syntax error position

- **WHEN** a caller submits a statement with an unexpected token
- **THEN** the raised error reports the offending line and column

#### Scenario: Semantic error

- **WHEN** a statement references an unbound variable or uses an aggregate illegally
- **THEN** the system raises a semantic query error before execution

#### Scenario: Execution error

- **WHEN** a query fails during evaluation, such as by division by zero
- **THEN** the system raises an execution query error and does not leak a raw SQLite exception


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


### Requirement: Identifier casing and quoting

Keywords and function names SHALL be case-insensitive. Variable names, labels, relationship labels, and property keys SHALL be case-sensitive. Backtick-quoted identifiers SHALL allow spaces, dots, and escaped backticks in labels, relationship labels, property keys, and variables.

#### Scenario: Keyword casing

- **WHEN** a caller writes `match ... where ... return ...` in lowercase
- **THEN** the statement is accepted

#### Scenario: Identifier casing

- **WHEN** a caller uses `Program` as a label and `program` as a separate label
- **THEN** the two labels are distinct

#### Scenario: Quoted property key

- **WHEN** a caller writes ``n.`a.b` `` or a property map key in backticks
- **THEN** the exact key containing the dot is addressed

#### Scenario: Quoted label with spaces

- **WHEN** a caller writes a label or relationship label in backticks with spaces
- **THEN** the exact stored label is matched
