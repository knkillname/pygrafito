# Spec Delta

## MODIFIED Requirements

### Requirement: Statement execution

The system SHALL execute exactly one statement per call and return a materialized `QueryResult`. A statement MAY contain write clauses and SHALL be classified as a write when it contains `INSERT`, `CREATE`, `MERGE`, `SET`, `REMOVE`, `DELETE`, `DETACH DELETE`, or `NODETACH DELETE`. A read statement SHALL change no data. `Graph.query` SHALL parse and execute in one step, and `Graph.prepare` SHALL return a reusable `PreparedQuery` for either kind.

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

#### Scenario: Insert is classified as a write

- **WHEN** a caller passes an `INSERT` statement to `Graph.query`
- **THEN** the statement is classified as a write and runs in its own transaction


### Requirement: Core dialect profile

A statement SHALL be an ordered sequence of read stages, optional write clauses, and an optional final `RETURN`. A read stage SHALL be `MATCH`, `OPTIONAL MATCH`, `FOR`, `FILTER`, or `WITH`. `UNWIND` SHALL be accepted as an alias for `FOR`, and a stage-level `WHERE` SHALL be accepted as an alias for `FILTER`. Every write clause SHALL follow every read stage, and `RETURN` SHALL be at most once and final. A read statement SHALL contain at least one row source and a `RETURN`; a write statement MAY omit both. Unsupported forms SHALL be rejected, never ignored.

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

A node pattern SHALL bind an optional variable, a label expression, an optional property map, and an optional inline `WHERE` predicate. A label expression SHALL support `&` conjunction, `|` disjunction, `!` negation, and `%` wildcard. `IS` SHALL be accepted as the explicit label form in place of `:`. Property map entries SHALL match stored values using the dialect's equality semantics.

#### Scenario: Labels and properties

- **WHEN** a caller matches `(p:Program:ISO {designation: 'Quorra'})`
- **THEN** only nodes carrying both labels and the matching property value are bound

#### Scenario: Conjunction and disjunction

- **WHEN** a caller matches `(p:Program&ISO)` or `(p:Program|Agent)`
- **THEN** the first binds nodes carrying both labels and the second binds nodes carrying either

#### Scenario: Negation and wildcard

- **WHEN** a caller matches `(p:Program&!ISO)` or `(p:%)`
- **THEN** the first excludes `ISO` nodes and the second binds every labeled or unlabeled node

#### Scenario: IS label form

- **WHEN** a caller matches `(p IS Program)` or `(p IS Program&ISO)`
- **THEN** the statement is accepted with the same label semantics as the `:` form

#### Scenario: Inline element predicate

- **WHEN** a caller matches `(n:Program WHERE n.cycles > 36)`
- **THEN** only nodes satisfying the predicate are bound, and the predicate is scoped to that element

#### Scenario: Arbitrary property key

- **WHEN** a caller matches a property whose key contains a dot or a space using a backtick-quoted identifier
- **THEN** the exact stored key is matched

#### Scenario: Anonymous node

- **WHEN** a caller omits the variable from a node pattern
- **THEN** the node participates in the path but is not available for projection


### Requirement: Relationship patterns

A relationship pattern SHALL bind an optional variable, a label expression, a direction, an optional property map, and an optional inline `WHERE` predicate. The canonical direction forms SHALL be `->` for a directed relationship traversed forward, `<-` for a directed relationship traversed backward, `-` for any incident relationship, and `~` for an undirected relationship only. `-->` and `<--` SHALL be accepted as aliases for `->` and `<-`. `--` SHALL NOT be an arrow. The profile's `<~`, `~>`, and `<->` forms SHALL be rejected with a gated-construct error until their semantics are defined. A relationship label filter SHALL match a relationship carrying that label.

#### Scenario: Outgoing relationship

- **WHEN** a caller matches `(a)-[r:ALLIES_WITH]->(b)`
- **THEN** only directed relationships carrying that label whose stored start is the current node are followed

#### Scenario: Incoming relationship

- **WHEN** a caller matches `(a)<-[r:ALLIES_WITH]-(b)`
- **THEN** only directed relationships carrying that label whose stored end is the current node are followed

#### Scenario: Undirected relationship

- **WHEN** a caller matches `(a)-[r]-(b)`
- **THEN** every incident relationship is followed, including an undirected relationship

#### Scenario: Undirected-only relationship

- **WHEN** a caller matches `(a)~[r]~(b)`
- **THEN** only relationships stored as undirected are followed

#### Scenario: Undirected edge is not matched by an arrow

- **WHEN** a caller matches `(a)-[r]->(b)` and the relationship between the nodes is undirected
- **THEN** the relationship does not match

#### Scenario: Double-dash arrow alias

- **WHEN** a caller matches `(a)-[r:ALLIES_WITH]->(b)` using `-->` or `<--`
- **THEN** the alias is accepted with the same semantics as the single-dash form

#### Scenario: Inline relationship predicate

- **WHEN** a caller matches `(a)-[r:ALLIES_WITH WHERE r.since_cycle > 2010]->(b)`
- **THEN** only relationships satisfying the predicate are followed

#### Scenario: Extended direction forms are gated

- **WHEN** a caller uses `<~`, `~>`, or `<->`
- **THEN** the system raises a gated-construct error because the profile does not define their semantics yet

#### Scenario: Type alternatives

- **WHEN** a caller matches `[r:ALLIES_WITH|TRUSTS]`
- **THEN** relationships carrying either listed label are followed

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

A relationship pattern MAY carry a legacy quantifier: `*n` for exactly `n` hops, `*n..m` for a bounded range, or `*0..m` to include the zero-hop case. Every hop SHALL apply the pattern's label filters, direction, and property map. The upper bound SHALL be explicit; a bare `*` or an open-ended `*n..` SHALL be rejected with a query error. Bounds SHALL be non-negative integers with `n` less than or equal to `m`. The canonical `{n,m}` quantifier SHALL be rejected with a gated-construct error until path semantics land and SHALL NOT be interpreted as a legacy quantifier.

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

- **WHEN** a caller matches a quantified pattern with `-` and the route uses an undirected relationship
- **THEN** the undirected relationship may be traversed from either endpoint

#### Scenario: Arrow excludes undirected hops

- **WHEN** a caller matches a quantified pattern with `->` and the route would require an undirected relationship
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

#### Scenario: Canonical quantifier is gated

- **WHEN** a caller writes `MATCH (a)-[:ALLIES_WITH{1,3}]->(b) RETURN b`
- **THEN** the system raises a gated-construct error naming `add-gql-path-semantics` and does not traverse


### Requirement: UNWIND clause

`FOR` SHALL expand a list-valued expression into one row per element and bind each element to a variable. `UNWIND <expression> AS <variable>` SHALL be accepted as an alias for `FOR <variable> IN <expression>`. A null value or an empty list SHALL produce no rows. A value that is not a list SHALL raise a query error. The variable SHALL be available to later clauses, and the clause SHALL be a read stage that precedes every write clause and `RETURN`. `WITH ORDINALITY` and `WITH OFFSET` SHALL be rejected with a gated-construct error until ordinality lands.

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
- **THEN** the system raises a gated-construct error and executes nothing


### Requirement: UNWIND as a row source

A statement SHALL accept `FOR` as its only row source, with `UNWIND` accepted as the alias. A read statement with `FOR` and `RETURN` SHALL be valid without a `MATCH`, and a write statement MAY begin with `FOR` and omit both `MATCH` and `RETURN`.

#### Scenario: Read without MATCH

- **WHEN** a caller submits `FOR value IN [1, 2] RETURN value`
- **THEN** the statement is accepted and returns two rows

#### Scenario: Write without MATCH

- **WHEN** a caller submits `FOR row IN $rows CREATE (n:Program {designation: row.designation})`
- **THEN** the statement is accepted and creates one node per row

#### Scenario: No row source and no write

- **WHEN** a caller submits `RETURN 1 AS value` without a `MATCH`, `FOR`, or write clause
- **THEN** the system raises a query error before execution


### Requirement: WITH aggregation and pagination

A `WITH` clause SHALL support the same aggregate functions, implicit grouping, `FILTER` (with `WHERE` as its alias), `ORDER BY`, `OFFSET` (with `SKIP` as its alias), and `LIMIT` as `RETURN`. A filter after `WITH` SHALL filter that stage's rows and MAY reference an aggregate alias. Names produced by the stage SHALL bind following stages, so grouped rows can be filtered, sorted, and paginated downstream.

#### Scenario: Aggregate then filter

- **WHEN** a caller submits `MATCH (a)-[:ALLIES_WITH]->(b) WITH a, count(*) AS friends WHERE friends > 2 RETURN a`
- **THEN** only nodes with more than two matches are returned

#### Scenario: Filter alias after WITH

- **WHEN** a caller submits the same statement with `FILTER friends > 2`
- **THEN** the result is identical to the `WHERE` alias

#### Scenario: Order by aggregate alias

- **WHEN** a caller orders a `WITH` stage by an aggregate alias descending
- **THEN** rows are ordered by that aggregate

#### Scenario: Grouped pagination

- **WHEN** a `WITH` stage groups rows and applies `OFFSET` and `LIMIT`
- **THEN** pagination applies to the grouped result, not to the input rows

#### Scenario: One row per group

- **WHEN** a `WITH` stage mixes an aggregate with a non-aggregate expression
- **THEN** one row is returned per distinct non-aggregate value


### Requirement: CREATE clause

`INSERT` SHALL create nodes and relationships from a pattern. `CREATE` SHALL be accepted as an alias for a data-modifying `INSERT` and SHALL NOT be accepted for a catalog operation. A created node SHALL bind its variable for later clauses and `RETURN`. A created relationship SHALL require both endpoint nodes to be already bound by a variable. `INSERT` SHALL always create new elements and SHALL NOT match existing ones. A created relationship SHALL carry the single label named in its pattern, or no label when the pattern names none, and SHALL be directed. Labels and property maps SHALL be validated before execution, and property values SHALL be non-aggregate expressions evaluated against the current row.

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


### Requirement: DELETE clause

`DELETE` SHALL delete relationships and nodes. A node that still has an incident relationship SHALL be rejected unless `DETACH DELETE` is used, which SHALL remove its incident relationships first. `NODETACH DELETE` SHALL be accepted as the explicit non-detaching form and SHALL behave exactly as `DELETE`. `DELETE` SHALL reject an unbound variable and SHALL reject a value that is not a node or relationship.

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

#### Scenario: Explicit non-detaching form

- **WHEN** a caller submits `NODETACH DELETE n` for a disconnected node
- **THEN** the node is removed exactly as `DELETE` would remove it

#### Scenario: Delete a non-entity

- **WHEN** a caller binds a scalar value and submits `DELETE` on it
- **THEN** the system raises a semantic query error and changes nothing


### Requirement: Ordering and pagination

`ORDER BY` SHALL accept one or more expressions or projected aliases with optional `ASC` or `DESC`, defaulting to ascending. Each sort key MAY specify `NULLS FIRST` or `NULLS LAST`; the default SHALL place nulls last in ascending order and first in descending order. `OFFSET` SHALL accept a non-negative integer or parameter, and `SKIP` SHALL be accepted as its alias. `LIMIT` SHALL accept a non-negative integer or parameter. Negative and non-integer values SHALL be rejected before execution.

#### Scenario: Ascending and descending order

- **WHEN** a caller orders by a property ascending and then descending
- **THEN** rows are returned in the corresponding order

#### Scenario: Null ordering

- **WHEN** an ordered expression is null for some rows
- **THEN** those rows sort last in ascending order and first in descending order

#### Scenario: Explicit null ordering

- **WHEN** a caller writes `ORDER BY n.cycles ASC NULLS FIRST` or `DESC NULLS LAST`
- **THEN** the null rows are placed at the requested end regardless of the direction default

#### Scenario: Pagination

- **WHEN** a caller applies `OFFSET 2 LIMIT 5`
- **THEN** at most five rows are returned after skipping the first two

#### Scenario: Skip alias

- **WHEN** a caller applies `SKIP 2 LIMIT 5`
- **THEN** the result is identical to the `OFFSET` spelling

#### Scenario: Parameterized pagination

- **WHEN** `OFFSET`, `SKIP`, or `LIMIT` receives a parameter
- **THEN** the parameter value is validated as a non-negative integer before execution


### Requirement: Projection and result columns

`RETURN` SHALL project expressions, aliases, and node, relationship, or path values. A column SHALL take its alias when present and otherwise its expression text. `RETURN ALL` SHALL be the explicit form of the default and `RETURN *` SHALL project every variable in scope in introduction order. `RETURN NO BINDINGS` SHALL be rejected with a gated-construct error until its result shape is defined. Duplicate column names SHALL be rejected. `DISTINCT` SHALL remove duplicate projected rows.

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

- **WHEN** a caller submits `RETURN NO BINDINGS` after a match
- **THEN** the system raises a gated-construct error and executes nothing


## ADDED Requirements

### Requirement: FILTER stage

A `FILTER` stage SHALL filter the rows produced by the preceding read stage. `FILTER WHERE` SHALL be accepted as the explicit spelling. A filter SHALL evaluate a boolean expression against the current row, keep only rows whose predicate is true, and SHALL NOT introduce a new binding.

#### Scenario: Filter after a match

- **WHEN** a caller submits `MATCH (n:Program) FILTER n.cycles > 36 RETURN n`
- **THEN** only rows whose predicate is true are returned

#### Scenario: Explicit FILTER WHERE

- **WHEN** a caller submits `MATCH (n:Program) FILTER WHERE n.cycles > 36 RETURN n`
- **THEN** the statement is accepted with the same result

#### Scenario: Filter introduces no binding

- **WHEN** a `FILTER` references a variable that is not bound before the stage
- **THEN** the system raises a semantic query error before execution


### Requirement: Comments

The dialect SHALL accept `//` line comments, `/* ... */` block comments, and `--` line comments. `-->` and `<--` SHALL be read as arrows, never as comments. A `--` that immediately follows a node or relationship pattern SHALL raise a syntax error rather than start a comment.

#### Scenario: Line and block comments

- **WHEN** a caller submits a statement containing `//` and `/* ... */` comments
- **THEN** the comments are ignored and the statement executes

#### Scenario: Dash comment

- **WHEN** a caller submits a statement beginning a line with `-- explanation`
- **THEN** the rest of that line is ignored

#### Scenario: Arrow wins over a comment

- **WHEN** a caller matches `(a)-->(b)` or `(a)<--(b)`
- **THEN** the statement parses as a directed pattern rather than a comment

#### Scenario: Ambiguous dash form is rejected

- **WHEN** a caller writes `MATCH (a)--(b) RETURN b`
- **THEN** the system raises a syntax error with a position and does not silently ignore the pattern


### Requirement: Gated construct diagnostics

A construct the profile lists as gated SHALL raise a semantic query error that names the construct and the follow-up change that implements it. The error SHALL NOT be reported as an unexpected token, and the statement SHALL NOT execute or partially execute.

#### Scenario: Quantifier gate

- **WHEN** a caller uses `{n,m}` or a path mode before the path-semantics change lands
- **THEN** the error names the construct and `add-gql-path-semantics`

#### Scenario: Composition gate

- **WHEN** a caller uses `LET`, `NEXT`, or `GROUP BY`
- **THEN** the error names the construct and `add-gql-composition`

#### Scenario: Statement does not execute

- **WHEN** a gated construct appears in a statement that also contains a write clause
- **THEN** the statement changes no data
