# graph-query-language Specification

## Purpose

Defines a pattern-matching graph query dialect for `pygrafito` that reads and writes a property graph: its statement shape, pattern semantics, write clauses, mutation cardinality, value model, filtering, projection, aggregation, parameters, result values, and errors.

## Requirements

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

A relationship pattern SHALL bind an optional variable, zero or more relationship types, a direction, and an optional property map. The direction forms `-->`, `<--`, and `--` SHALL follow outgoing, incoming, and both directions respectively. A bound relationship SHALL preserve its stored start node, end node, and type.

#### Scenario: Outgoing relationship

- **WHEN** a caller matches `(a)-[r:ALLIES_WITH]->(b)`
- **THEN** only relationships whose stored start is the current node are followed

#### Scenario: Incoming relationship

- **WHEN** a caller matches `(a)<-[r:ALLIES_WITH]-(b)`
- **THEN** only relationships whose stored end is the current node are followed

#### Scenario: Undirected relationship

- **WHEN** a caller matches `(a)-[r]-(b)`
- **THEN** relationships are followed in either stored direction

#### Scenario: Type alternatives

- **WHEN** a caller matches `[r:ALLIES_WITH|TRUSTS]`
- **THEN** only relationships of either listed type are followed

#### Scenario: Relationship property filter

- **WHEN** a caller matches `[r {since_cycle: 2020}]`
- **THEN** only relationships carrying that exact property value are followed

### Requirement: Pattern variables and paths

A variable used more than once in a pattern SHALL refer to the same node or relationship. A path variable SHALL expose the matched nodes and relationships in traversal order, with nodes ordered from the path start to the path end even when relationships are traversed against their stored direction.

#### Scenario: Repeated node variable

- **WHEN** a caller matches `(a)-[r]->(a)`
- **THEN** only self-loop relationships bind, because both node positions refer to the same node

#### Scenario: Path variable

- **WHEN** a caller matches `p = (a)-[r]->(b)` and returns `p`
- **THEN** the result value is a `Path` whose nodes run from `a` to `b` and whose relationships are in traversal order

#### Scenario: Incoming path order

- **WHEN** a path is built through an incoming relationship
- **THEN** its node sequence still runs from the start node to the end node

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

The core function set SHALL include `id`, `labels`, `type`, `properties`, `keys`, `size`, `coalesce`, `toInteger`, `toFloat`, `toString`, `lower`, `upper`, `trim`, `abs`, `concat`, `startNode`, and `endNode`. Function names SHALL be case-insensitive, and `labels` and `keys` SHALL return sorted lists.

#### Scenario: Entity metadata

- **WHEN** a caller projects `id(n)`, `labels(n)`, or `properties(n)`
- **THEN** the result contains the element id, its sorted labels, or its property mapping respectively

#### Scenario: Relationship metadata

- **WHEN** a caller projects `type(r)`, `startNode(r)`, or `endNode(r)`
- **THEN** the result contains the relationship type or the corresponding node snapshot

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

### Requirement: Identifier casing and quoting

Keywords and function names SHALL be case-insensitive. Variable names, labels, relationship types, and property keys SHALL be case-sensitive. Backtick-quoted identifiers SHALL allow spaces, dots, and escaped backticks in labels, relationship types, property keys, and variables.

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

- **WHEN** a caller writes a label or relationship type in backticks with spaces
- **THEN** the exact stored label or type is matched
