# graph-query-language Specification

## Purpose

Defines a pattern-matching graph query dialect for `pygrafito` that reads and writes a property graph: its statement shape, pattern semantics, write clauses, mutation cardinality, value model, filtering, projection, aggregation, parameters, result values, and errors.

## Requirements

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

A linear statement SHALL be an ordered sequence of one or more segments separated by `NEXT`. A compound query SHALL combine two or more linear statements with a set operator. Each linear segment SHALL contain an ordered sequence of read stages, optional write clauses, and a result clause, and every write clause SHALL follow every read stage within its segment.

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

- **WHEN** a caller submits `MATCH (a)-[:TRUSTS{-1,2}]->(b) RETURN b`
- **THEN** the system raises a semantic query error before execution because a bound is negative

#### Scenario: Open-ended pattern form

- **WHEN** a caller submits `MATCH (a)-[*]->(b) RETURN b` or `MATCH (a)-[:TRUSTS{1,}]->(b) RETURN b`
- **THEN** the statement is accepted and the open-ended pattern is matched under its resolved path mode

#### Scenario: Unsupported clause

- **WHEN** a caller submits a statement using `CALL { ... }`, `exists(n.prop)`, whole-map assignment, or a regex predicate
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

- **WHEN** a caller submits a statement using `CALL { ... }`, `exists(n.prop)`, whole-map assignment, or a regex predicate
- **THEN** the system raises a query error before execution

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

A relationship pattern SHALL bind an optional variable, a label expression, a direction, an optional property map, and an optional inline `WHERE` predicate. The canonical direction forms SHALL be `->`, `<-`, `-`, `~`, `<->`, `<~`, and `~>`. `-->` and `<--` SHALL be accepted as aliases for `->` and `<-`, and `--` SHALL NOT be an arrow. A relationship label filter SHALL match a relationship carrying that label.

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
- **THEN** the form is no longer rejected as gated: it is accepted and matched under the direction semantics below

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

#### Scenario: Either directed direction

- **WHEN** a caller matches `(a)<-[r]->(b)`
- **THEN** a directed relationship stored from `a` to `b` matches and a directed relationship stored from `b` to `a` matches

#### Scenario: Either-direction form excludes undirected edges

- **WHEN** a caller matches `(a)<-[r]->(b)` and the relationship between the nodes is stored as undirected
- **THEN** the relationship does not match

#### Scenario: Incoming or undirected

- **WHEN** a caller matches `(a)<-[r]~(b)`
- **THEN** a directed relationship stored from `b` to `a` matches and an undirected relationship matches, while a directed relationship stored from `a` to `b` does not

#### Scenario: Outgoing or undirected

- **WHEN** a caller matches `(a)~[r]->(b)`
- **THEN** a directed relationship stored from `a` to `b` matches and an undirected relationship matches, while a directed relationship stored from `b` to `a` does not

#### Scenario: Bare combined direction

- **WHEN** a caller matches `(a)<->(b)`, `(a)<~(b)`, or `(a)~>(b)` without a relationship detail
- **THEN** the statement is accepted and each form matches as its detailed counterpart does

### Requirement: Relationship quantifiers

A relationship pattern MAY carry a quantifier. Closed forms SHALL be `{n}`, `{m,n}`, and `{,n}`. Open forms SHALL be `{m,}`, `*` (zero or more), and `+` (one or more). The legacy forms `*n`, `*n..m`, `*0..m`, and `*n..` SHALL remain compatible. Every hop SHALL apply the pattern's labels, direction, properties, and predicate. Bounds SHALL be non-negative, a lower bound SHALL NOT exceed a present upper bound, and no upper bound SHALL mean unbounded.

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

- **WHEN** continuing a legacy quantified path would reuse an undirected relationship already in that path
- **THEN** that extension is not returned

#### Scenario: Canonical open quantifiers

- **WHEN** a caller writes `MATCH (a)-[:TRUSTS*]->(b) RETURN b`, `MATCH (a)-[:TRUSTS+]->(b) RETURN b`, or `MATCH (a)-[:TRUSTS{1,}]->(b) RETURN b`
- **THEN** the statement is accepted and each form means an unbounded upper bound

#### Scenario: Bare star includes zero hops

- **WHEN** a caller matches `(a)-[:TRUSTS*]->(b)`
- **THEN** a zero-hop match where `a` and `b` are the same node is included

#### Scenario: Plus requires at least one hop

- **WHEN** a caller matches `(a)-[:TRUSTS+]->(b)`
- **THEN** the zero-hop match is not included

#### Scenario: Legacy open form keeps trail

- **WHEN** a caller writes `MATCH (a)-[:TRUSTS*1..]->(b) RETURN b`
- **THEN** the form is accepted as a legacy quantifier and the path is matched under `TRAIL` unless a mode is explicit

#### Scenario: Canonical open lower bound

- **WHEN** a caller matches `(a)-[:TRUSTS{2,}]->(b)`
- **THEN** nodes at depth two or more are bound

#### Scenario: Negative bound is rejected

- **WHEN** a caller writes `MATCH (a)-[:TRUSTS{-1,2}]->(b) RETURN b`
- **THEN** the system raises a query error before execution

#### Scenario: Inverted bounds are rejected

- **WHEN** a caller writes `MATCH (a)-[:TRUSTS{3,1}]->(b) RETURN b`
- **THEN** the system raises a query error before execution

#### Scenario: Canonical exact length

- **WHEN** a caller matches `(a)-[:ALLIES_WITH{2}]->(b)`
- **THEN** only nodes two relationships away are bound

#### Scenario: Canonical bounded range

- **WHEN** a caller matches `(a)-[:ALLIES_WITH{1,3}]->(b)`
- **THEN** nodes at depths one, two, and three are bound

#### Scenario: Canonical upper bound only

- **WHEN** a caller matches `(a)-[:ALLIES_WITH{,2}]->(b)`
- **THEN** nodes at depths zero, one, and two are bound

#### Scenario: Canonical quantifier is not a legacy quantifier

- **WHEN** a caller writes `MATCH (a)-[:ALLIES_WITH{1,3}]->(b) RETURN b`
- **THEN** the quantifier is interpreted as the canonical form and its default path mode is resolved by the path-mode rule, not by the legacy `TRAIL` default

### Requirement: Open-ended traversal

An open-ended quantifier SHALL enumerate matches lazily under the effective path mode. `TRAIL`, `SIMPLE`, and `ACYCLIC` SHALL bound the walk by the graph's elements. An open `WALK` MAY be unbounded, SHALL NOT buffer the whole reachable region, and SHALL stop when downstream demand is satisfied. Without a demand bound it SHALL run until the budget raises `QueryBudgetExceededError`, with no partial result.

#### Scenario: Open walk follows the cycle

- **WHEN** a three-node directed cycle is matched with `WALK (a)-[:TRUSTS+]->(b)`
- **THEN** the walk may revisit nodes and relationships

#### Scenario: Open trail stops at the element bound

- **WHEN** the same cycle is matched with `TRAIL (a)-[:TRUSTS+]->(b)`
- **THEN** every produced path uses each relationship at most once and enumeration ends

#### Scenario: Demand stops an open walk

- **WHEN** a caller submits `MATCH (a)-[:TRUSTS+]->(b) RETURN b LIMIT 5` on a dense graph
- **THEN** at most five rows are returned and traversal stops before exhausting the walk

#### Scenario: No demand fails safely

- **WHEN** a caller submits an open `WALK` with no `LIMIT`
- **THEN** the call raises `QueryBudgetExceededError` and returns no rows or partial result

#### Scenario: Optional match keeps unmatched rows

- **WHEN** an `OPTIONAL MATCH` with an open quantifier finds no match for an input row
- **THEN** the row is preserved with the pattern variables null

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

Traversal SHALL be unique according to the effective path mode: `TRAIL` forbids reusing a relationship but allows repeated nodes, and `WALK` allows both. A variable-length relationship variable SHALL bind the ordered list of traversed relationships, and a path variable SHALL include every expanded relationship in traversal order. A variable-length relationship variable SHALL NOT be used where a single relationship is required.

#### Scenario: Relationship variable binds a list

- **WHEN** a caller matches `(a)-[r:ALLIES_WITH*1..3]->(b) RETURN r`
- **THEN** each row binds `r` to the list of relationships in that match

#### Scenario: Relationship uniqueness

- **WHEN** a `TRAIL` path offers a route that would reuse one relationship
- **THEN** that route is not produced

#### Scenario: Nodes may repeat

- **WHEN** a `TRAIL` path revisits a node without reusing a relationship
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

#### Scenario: Walk may repeat a relationship

- **WHEN** a `WALK` path offers a route that reuses a relationship
- **THEN** the route is produced

### Requirement: Pattern match row semantics

`MATCH` SHALL produce one row per distinct match of the pattern, unless a path pattern carries a
path-search prefix, in which case it SHALL produce only the paths that prefix selects. Parallel
relationships, self-loops, diamonds, and cycles SHALL produce the matches implied by the graph, and
duplicate projected rows SHALL be removed only when `DISTINCT` is requested.

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

#### Scenario: Path search reduces rows

- **WHEN** a path pattern carries a path-search prefix and matches several paths for one endpoint pair
- **THEN** only the selected paths become rows

### Requirement: Path search syntax

A path pattern MAY carry at most one path-search prefix: `ANY`, `ANY SHORTEST`, `ALL SHORTEST`,
or `SHORTEST k`. The prefix SHALL follow the optional path variable and precede any path mode.
`k` SHALL be a non-negative integer literal; parameters and expressions SHALL be rejected. A
path variable SHALL bind the selected path.

#### Scenario: Path variable binds the selection

- **WHEN** a caller writes `MATCH p = ANY SHORTEST (a)-[:TRUSTS]->(b) RETURN p`
- **THEN** `p` is the selected path

#### Scenario: Non-literal k is rejected

- **WHEN** a caller writes `SHORTEST $k` or `SHORTEST 1 + 1`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Negative k is rejected

- **WHEN** a caller writes `SHORTEST -1`
- **THEN** the system raises a query error before execution

### Requirement: Path search selection

Path search SHALL partition matches by the path's first and last node within each input row. It
SHALL select `ANY` one path, `ANY SHORTEST` one minimum-length path, `ALL SHORTEST` every
minimum-length path, and `SHORTEST k` up to `k` paths in increasing length. `k = 0` SHALL select
no path.

#### Scenario: Any selects one path per pair

- **WHEN** two distinct routes connect the same endpoint pair and the pattern uses `ANY`
- **THEN** one row is produced for that pair

#### Scenario: Any shortest selects a minimum path

- **WHEN** routes of length two and three connect the same endpoint pair and the pattern uses
  `ANY SHORTEST`
- **THEN** the selected path has length two

#### Scenario: All shortest selects every minimum path

- **WHEN** two two-hop routes and one three-hop route connect the same endpoint pair and the
  pattern uses `ALL SHORTEST`
- **THEN** two rows are produced

#### Scenario: Shortest k returns increasing lengths

- **WHEN** a pattern uses `SHORTEST 2` and the partition has paths of length two and three
- **THEN** both selected paths are returned, shortest first

#### Scenario: Zero k selects nothing

- **WHEN** a path pattern uses `SHORTEST 0`
- **THEN** the pattern produces no rows

#### Scenario: Unreachable pair is absent

- **WHEN** no path connects a candidate endpoint pair
- **THEN** the partition produces no row

### Requirement: Path identity and ordering

Two paths SHALL be identical when their node and orientation-aware relationship sequences match;
parallel relationships SHALL be distinct paths. `ALL SHORTEST` SHALL return distinct paths. Ties
SHALL break by the lexicographically smaller relationship sequence, then node sequence. Rows SHALL
be ordered by partition and selection order unless the statement has an `ORDER BY`.

#### Scenario: Parallel relationships are distinct paths

- **WHEN** two parallel relationships connect the same nodes and the pattern uses `ALL SHORTEST`
- **THEN** both paths are returned

#### Scenario: Duplicate path is not repeated

- **WHEN** the same node and relationship sequence would be produced twice by the evaluator
- **THEN** only one row is produced

#### Scenario: Tie-break is deterministic

- **WHEN** two shortest paths have the same length and different relationship identifiers
- **THEN** the same path is selected on every run and on every storage plan

#### Scenario: Output order is stable

- **WHEN** two partitions produce selected paths and the statement has no `ORDER BY`
- **THEN** rows appear in ascending start and end node identifier order

### Requirement: Path search mode interaction

Path search SHALL evaluate only paths accepted by the effective path mode and match mode. A
`DIFFERENT EDGES` clause SHALL apply its edge rule before selection. Path search SHALL apply to
whole paths only.

#### Scenario: Different edges narrows the search

- **WHEN** a `DIFFERENT EDGES` clause and a path-search prefix produce an edge-sharing candidate
- **THEN** that candidate is not selected

#### Scenario: Path mode applies before selection

- **WHEN** a `TRAIL` path and an `ALL SHORTEST` prefix find an edge-reusing candidate
- **THEN** that candidate is not selected

### Requirement: Path search termination and budget

Path search SHALL evaluate in nondecreasing length order and SHALL stop a partition once its
selection is complete. `ANY SHORTEST` and `ALL SHORTEST` SHALL stop at the shortest layer.
`SHORTEST k` SHALL stop at its k-th path. Search SHALL terminate for open `WALK` patterns by
pruning states that cannot improve a selection. A final `LIMIT` MAY stop the search. Every
expansion SHALL count against the budget, and a budget failure SHALL raise with no partial result.

#### Scenario: Any shortest does not enumerate longer paths

- **WHEN** `ANY SHORTEST` finds a path at length two for a partition with longer routes
- **THEN** it does not enumerate the longer routes

#### Scenario: Shortest k stops at k

- **WHEN** `SHORTEST 2` finds two paths for a partition and more paths exist
- **THEN** it stops expanding that partition

#### Scenario: Open walk search terminates

- **WHEN** `ANY SHORTEST` or `ALL SHORTEST` runs over an open `WALK` pattern on a cyclic graph
- **THEN** the query completes with the shortest paths

#### Scenario: Limit stops the search

- **WHEN** a path-search query has a final `LIMIT` and enough partitions are discovered
- **THEN** expansion stops when the limit is satisfied

#### Scenario: Budget failure returns nothing

- **WHEN** a path-search query exceeds the expansion budget
- **THEN** the call raises `QueryBudgetExceededError` and returns no rows

### Requirement: Path terms

A path pattern SHALL be a juxtaposition of one or more path terms. A term SHALL be a node pattern
followed by relationship-node pairs, or a parenthesized path pattern followed by a quantifier.
Adjacent terms SHALL share their boundary node: the last node of one term and the first node of the
next SHALL be the same node. A group SHALL contain a relationship position, directly or through a
nested group.

#### Scenario: Juxtaposition shares a boundary

- **WHEN** a caller writes `MATCH (a:User)((b:Program)-[r:TRUSTS]->(c:Program)){2}(d:Program) RETURN a, d`
- **THEN** `a` is the same node as `b`, and `c` of the last iteration is the same node as `d`

#### Scenario: Group without a relationship is rejected

- **WHEN** a caller writes `MATCH ((a:Program)){2} RETURN a`
- **THEN** the system raises a semantic query error before execution

### Requirement: Group syntax

A group quantifier SHALL be `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, or `+`, with the same bounds as a
relationship quantifier. The legacy `*n..m` spelling SHALL be rejected on a group. A group MAY
carry a path variable and an inner path mode, and SHALL NOT carry a path-search prefix.

#### Scenario: Fixed repetition

- **WHEN** a caller writes `MATCH ((a)-[r:TRUSTS]->(b)){2} RETURN a, b`
- **THEN** the group matches two consecutive copies and the boundary node of the first copy is the
  start node of the second

#### Scenario: Bounded repetition matches the unrolled form

- **WHEN** a caller matches `((a)-[r:TRUSTS]->(b)){2}` and the equivalent unrolled two-copy pattern
- **THEN** both return the same rows and bindings

#### Scenario: Open group

- **WHEN** a caller writes `MATCH ((a)-[r:TRUSTS]->(b)){1,} RETURN a, b` under `TRAIL`
- **THEN** the group repeats until no further iteration is allowed

#### Scenario: Legacy group quantifier is rejected

- **WHEN** a caller writes `MATCH ((a)-[r:TRUSTS]->(b))*1..2 RETURN a`
- **THEN** the system raises a query error before execution

#### Scenario: Search prefix inside a group is rejected

- **WHEN** a caller writes `MATCH ((ANY (a)-[r:TRUSTS]->(b))){2} RETURN a`
- **THEN** the system raises a semantic query error before execution

### Requirement: Group variable scope

A variable first introduced inside a group SHALL be a group variable. It SHALL occur at most once
in its group and SHALL NOT shadow a variable bound outside. A nested group SHALL NOT reference an
enclosing group's local variables. A variable bound before the group SHALL act as an equality
constraint inside it.

#### Scenario: Outer variable is an equality constraint

- **WHEN** a variable bound by an earlier clause appears inside a group
- **THEN** every position using it binds the same element and the variable keeps its single value

#### Scenario: Duplicate group variable is rejected

- **WHEN** the same new variable occurs twice inside one group
- **THEN** the system raises a semantic query error before execution

#### Scenario: Shadowing is rejected

- **WHEN** a group introduces a variable with the same name as a variable bound before it
- **THEN** the system raises a semantic query error before execution

### Requirement: Group variable kinds

Outside a group, a node group variable SHALL bind one node per iteration and a relationship group
variable SHALL bind one relationship per iteration; nested groups SHALL flatten in traversal order.
A group path variable SHALL bind one `Path` and SHALL require a positive lower bound. Property
access on a group variable and `type()` on a group relationship variable SHALL be rejected.

#### Scenario: Node group variable binds a list

- **WHEN** a caller writes `MATCH ((a)-[r:TRUSTS]->(b)){2} RETURN a`
- **THEN** `a` is a list of two nodes

#### Scenario: Relationship group variable binds a list

- **WHEN** a caller writes `MATCH ((a)-[r:TRUSTS]->(b)){2} RETURN r`
- **THEN** `r` is a list of two relationships

#### Scenario: Nested groups flatten

- **WHEN** an inner and an outer group both introduce a relationship variable over two iterations
- **THEN** the variable binds one flat list in traversal order

#### Scenario: Zero iterations bind empty lists

- **WHEN** a group with a lower bound of zero takes no iteration and the rest of the path matches
- **THEN** every group variable binds an empty list and the boundary nodes coincide

#### Scenario: Group path variable

- **WHEN** a caller writes `MATCH (p = (a)-[r:TRUSTS]->(b)){2} RETURN p`
- **THEN** `p` is one path containing both iterations in traversal order

#### Scenario: Group path variable needs a positive lower bound

- **WHEN** a group path variable is combined with a quantifier whose lower bound is zero
- **THEN** the system raises a semantic query error before execution

#### Scenario: Property access on a group variable is rejected

- **WHEN** a caller writes `RETURN a.designation` where `a` is a node group variable
- **THEN** the system raises a semantic query error before execution

### Requirement: Grouped mode composition

The outer path mode SHALL apply to the whole path, including every grouped iteration. An inner
path mode SHALL apply to the group's own repetitions. Both SHALL be enforced and the stricter
constraint SHALL win. The clause match mode SHALL span group iterations. Path search SHALL apply to
whole paths.

#### Scenario: Outer mode covers the whole path

- **WHEN** `ACYCLIC` is the outer mode and two group iterations would revisit a node
- **THEN** the match is not produced

#### Scenario: Inner mode is stricter

- **WHEN** the outer mode is `WALK` and the inner mode is `TRAIL`
- **THEN** a relationship may not repeat in any iteration

#### Scenario: Inner and outer path modes

- **WHEN** a caller writes `MATCH WALK (ACYCLIC (a)-[r:TRUSTS]->(b)){1,3} RETURN a, b`
- **THEN** the inner `ACYCLIC` rule and the outer `WALK` rule both apply, so no node repeats

#### Scenario: Match mode spans group iterations

- **WHEN** a `DIFFERENT EDGES` clause repeats a group and an edge would be used twice
- **THEN** that match is not produced

#### Scenario: Search selects whole paths

- **WHEN** a grouped path carries `ANY SHORTEST`
- **THEN** one shortest complete path is selected per endpoint pair

### Requirement: Grouped restrictions and budget

A grouped path pattern SHALL contain at least one relationship position whose effective minimum
hop count is at least one, so every iteration charges the expansion counter. A path pattern that is
only a group with a zero lower bound SHALL be rejected. The statement budget SHALL count every
expanded relationship and produced binding, and a budget failure SHALL return no partial result.

#### Scenario: Non-progressing group is rejected

- **WHEN** every relationship inside a group has a lower bound of zero
- **THEN** the system raises a semantic query error before execution

#### Scenario: Lone zero-lower group is rejected

- **WHEN** a path pattern consists only of a group with a zero lower bound
- **THEN** the system raises a semantic query error before execution

#### Scenario: Budget stops an open group

- **WHEN** an open grouped `WALK` exceeds the expansion budget
- **THEN** the call raises `QueryBudgetExceededError` and returns no partial result

#### Scenario: Path order and length include every iteration

- **WHEN** a grouped path is returned and `length(p)` is projected
- **THEN** the length counts every relationship of every iteration and the nodes run from the
  start of the first iteration to the end of the last

#### Scenario: Optional match with a group

- **WHEN** an `OPTIONAL MATCH` with a grouped pattern finds no match for an input row
- **THEN** the row is preserved with the group variables null

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

`WHERE` SHALL accept the dialect's scalar expression surface: comparison operators, `AND`, `OR`, `NOT`, `IN`, `IS NULL`, `IS NOT NULL`, `STARTS WITH`, `ENDS WITH`, `CONTAINS`, arithmetic, string concatenation, list and map literals, list access and comprehensions, `CASE`, path functions, scalar functions, and read-only query expressions. String predicates SHALL be case-sensitive.

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

#### Scenario: CASE in a filter

- **WHEN** a caller filters with `CASE WHEN n.cycles > 36 THEN true ELSE false END`
- **THEN** only rows whose `CASE` result is true are returned

#### Scenario: List comprehension in a filter

- **WHEN** a caller filters with `size([x IN n.tags WHERE x STARTS WITH 'ISO']) > 0`
- **THEN** only rows whose tags contain a matching element are returned

#### Scenario: Query expression in a filter

- **WHEN** a caller filters with `EXISTS { MATCH (n)-[:TRUSTS]->(m:Program) }`
- **THEN** only rows with at least one matching inner row are returned

### Requirement: Scalar functions

The dialect SHALL support the core functions `id`, `labels`, `type`, `properties`, `keys`, `size`, `coalesce`, `toInteger`, `toFloat`, `toString`, `lower`, `upper`, `trim`, `abs`, `concat`, `startNode`, and `endNode`, plus the extended functions in this spec. Function names SHALL be case-insensitive; `labels` and `keys` SHALL return sorted lists; `labels` SHALL accept a node or relationship; `type` SHALL return the first sorted relationship label or null.

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

- **WHEN** a caller uses a function name that is not in the supported function catalog
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

### Requirement: Demand-driven read execution

A read statement SHALL consume rows lazily when it does not need every row first, and SHALL stop matching and expanding once the final `LIMIT` and `OFFSET` are satisfied. `ORDER BY`, `DISTINCT`, aggregation, `GROUP BY`, set operations, writes, `NEXT`, and `FINISH` SHALL evaluate their input fully. `EXISTS { ... }` SHALL stop at its first inner row; `COUNT { ... }` SHALL consume all rows.

#### Scenario: Limit stops expansion

- **WHEN** a query with a final `LIMIT` and no ordering or grouping is executed
- **THEN** relationship expansions stop once the requested rows and skipped rows are produced

#### Scenario: Limit zero does nothing

- **WHEN** a query with a final `LIMIT 0` is executed
- **THEN** no pattern expansion happens and the result has no rows

#### Scenario: Ordering forces full evaluation

- **WHEN** a query with `ORDER BY` and `LIMIT` is executed
- **THEN** every matching row is produced before ordering and pagination apply

#### Scenario: Aggregation forces full evaluation

- **WHEN** a query with aggregation or `GROUP BY` and `LIMIT` is executed
- **THEN** every matching row is consumed before the aggregate result is paginated

#### Scenario: Exists stops early

- **WHEN** an `EXISTS { ... }` subquery finds its first inner row
- **THEN** the inner pattern stops expanding

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

`Graph.prepare` SHALL parse and validate a statement once and return a `PreparedQuery` whose `execute` method may run repeatedly with different parameters. A prepared statement MAY be a write statement. Preparation SHALL reject syntax and semantic errors before execution, and prepared columns SHALL be available before the first execution and SHALL be empty without `RETURN`. For a compound query, prepared columns SHALL be the first operand's columns.

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

#### Scenario: Compound columns

- **WHEN** a caller prepares a compound query whose first operand returns `name` and `cycles`
- **THEN** the prepared columns are `name` and `cycles` before execution

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

### Requirement: Consistent open-traversal snapshot

A statement with an open-ended pattern SHALL read inside one consistent snapshot per contiguous read prefix. The snapshot SHALL be released before the statement returns. Read stages SHALL be drained before the first write stage, and the write SHALL stay atomic with the statement.

#### Scenario: Concurrent write does not change an open walk

- **WHEN** another connection writes to the graph while an open walk is being iterated
- **THEN** the walk continues to reflect the graph state at the start of the statement

#### Scenario: Read stages finish before writes

- **WHEN** a statement matches with an open quantifier and then sets a property
- **THEN** the read stage is fully consumed before the statement's first write executes

#### Scenario: Budget failure leaves no transaction open

- **WHEN** an open-walk statement exceeds the budget
- **THEN** the call raises, releases the read snapshot, and leaves the graph handle usable

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

### Requirement: Path modes

A path SHALL be matched under one of four path modes. `WALK` SHALL allow a node or a relationship to repeat within the path. `TRAIL` SHALL forbid reusing a relationship while allowing a node to repeat. `SIMPLE` SHALL forbid repeating a node except that the start and end node MAY be the same. `ACYCLIC` SHALL forbid repeating any node, including the start and end node. The default for a canonical path without an explicit or implied mode SHALL be `WALK`.

#### Scenario: Walk reuses a relationship

- **WHEN** a directed cycle returns to its start after three relationships and the path is matched under `WALK`
- **THEN** the match is produced

#### Scenario: Trail excludes relationship reuse

- **WHEN** the same cycle is matched under `TRAIL`
- **THEN** the match is not produced

#### Scenario: Simple allows a closed path

- **WHEN** a path under `SIMPLE` returns to its start node without repeating an intermediate node
- **THEN** the match is produced

#### Scenario: Simple rejects an intermediate repeat

- **WHEN** a path under `SIMPLE` repeats a node that is not the start and end node
- **THEN** the match is not produced

#### Scenario: Acyclic rejects a closed path

- **WHEN** a path under `ACYCLIC` returns to its start node
- **THEN** the match is not produced

#### Scenario: Self-loop under acyclic

- **WHEN** a path under `ACYCLIC` traverses a self-loop and would repeat the node
- **THEN** the match is not produced

#### Scenario: Explicit per-path mode

- **WHEN** a caller writes `MATCH TRAIL (a)-[:TRUSTS*1..3]->(b) RETURN b`
- **THEN** only the named path is matched under `TRAIL` and other paths in the clause keep the default

### Requirement: Path mode selection

The effective path mode of a path SHALL be resolved in this order: an explicit per-path mode, an explicit clause mode, `TRAIL` when the path contains a legacy quantifier, and `WALK` otherwise. An explicit mode SHALL override both defaults. A path that mixes a legacy and a canonical quantifier without an explicit mode SHALL be a semantic error, and that error SHALL be raised before execution.

#### Scenario: Legacy quantifier implies trail

- **WHEN** a caller writes `MATCH (a)-[:ALLIES_WITH*1..3]->(b) RETURN b`
- **THEN** the path is matched under `TRAIL`

#### Scenario: Canonical quantifier implies walk

- **WHEN** a caller writes `MATCH (a)-[:ALLIES_WITH{1,3}]->(b) RETURN b`
- **THEN** the path is matched under `WALK`

#### Scenario: Explicit clause mode wins

- **WHEN** a caller writes `MATCH TRAIL (a)-[:ALLIES_WITH{1,3}]->(b) RETURN b`
- **THEN** the path is matched under `TRAIL`

#### Scenario: Explicit per-path mode wins over the clause mode

- **WHEN** a clause names `WALK` and one of its paths names `ACYCLIC`
- **THEN** that path is matched under `ACYCLIC`

#### Scenario: Mixed quantifiers are rejected

- **WHEN** one path contains both `*1..2` and `{1,2}` without an explicit mode
- **THEN** the system raises a semantic query error before execution and traverses nothing

#### Scenario: Explicit mode resolves mixed quantifiers

- **WHEN** one path contains both quantifier forms and the path or clause names an explicit mode
- **THEN** the statement is accepted and that mode applies

### Requirement: Match modes

A `MATCH` or `OPTIONAL MATCH` clause SHALL resolve exactly one match mode: `REPEATABLE ELEMENTS`
or `DIFFERENT EDGES`. `REPEATABLE ELEMENTS` SHALL add no constraint and SHALL be the default.
`DIFFERENT EDGES` SHALL forbid any relationship from binding more than once anywhere in the
clause, across every path and every repetition inside a path. Nodes MAY repeat under either mode.

#### Scenario: Default is repeatable elements

- **WHEN** a caller matches two patterns that can share one relationship without naming a match mode
- **THEN** both patterns may bind that relationship

#### Scenario: Explicit repeatable elements

- **WHEN** a caller submits `MATCH REPEATABLE ELEMENTS (a)-[r]->(b), (c)-[s]->(d) RETURN r, s`
- **THEN** `r` and `s` may bind the same relationship

#### Scenario: Different edges rejects a shared relationship

- **WHEN** a caller submits `MATCH DIFFERENT EDGES (a)-[r]->(b), (c)-[s]->(d) RETURN r, s` and
  the only candidate makes `r` and `s` the same relationship
- **THEN** that combination is not produced

#### Scenario: Different edges rejects reuse inside a walk

- **WHEN** a `WALK` path under `DIFFERENT EDGES` would revisit one relationship
- **THEN** that extension is not produced

#### Scenario: Parallel relationships stay distinct

- **WHEN** two separate relationships connect the same pair of nodes and `DIFFERENT EDGES` binds
  one to each of two positions
- **THEN** the match is produced because the relationships are different

#### Scenario: Nodes may repeat

- **WHEN** `DIFFERENT EDGES` matches a route that revisits a node without reusing a relationship
- **THEN** the match is produced

#### Scenario: Self-loop consumes one relationship

- **WHEN** `DIFFERENT EDGES` matches a self-loop in two positions
- **THEN** only one position may bind that relationship

#### Scenario: Already unique clause is unchanged

- **WHEN** a clause that never binds one relationship twice runs under `DIFFERENT EDGES`
- **THEN** it produces the same rows and bindings as the default mode

#### Scenario: Optional match uses the same rule

- **WHEN** an `OPTIONAL MATCH DIFFERENT EDGES` finds no edge-disjoint match for an input row
- **THEN** the row is preserved with the pattern variables null

### Requirement: Match mode composition and scope

The match mode SHALL be resolved independently of the path mode and SHALL combine with it by
intersection: an extension SHALL be accepted only when both the effective path mode and the match
mode allow it. The match mode SHALL apply only to the paths of its own clause. A relationship bound
by an earlier stage MAY be bound again by a later clause, and write clauses (`INSERT`, `CREATE`,
and `MERGE`) SHALL NOT carry a match mode.

#### Scenario: Different edges narrows walk

- **WHEN** a path resolves to `WALK` and its clause names `DIFFERENT EDGES`
- **THEN** each relationship is used at most once in the clause

#### Scenario: Trail and different edges agree

- **WHEN** a path resolves to `TRAIL` and its clause names `DIFFERENT EDGES`
- **THEN** both rules forbid relationship reuse and the match is produced

#### Scenario: Repeatable elements loosens trail only across paths

- **WHEN** two `TRAIL` paths in one `REPEATABLE ELEMENTS` clause use different relationships but
  the same node
- **THEN** both paths are produced

#### Scenario: Scope is the clause

- **WHEN** an earlier `MATCH` binds a relationship and a later `MATCH DIFFERENT EDGES` binds it
  again in a different path
- **THEN** the later match is accepted because the mode does not cross the clause boundary

#### Scenario: Write clauses have no match mode

- **WHEN** a caller writes `INSERT DIFFERENT EDGES (a)-[:TRUSTS]->(b)`
- **THEN** the system raises a query error before execution

### Requirement: Query budget counters

A query SHALL be limited by a budget that counts relationship expansions and intermediate rows produced by a stage. The budget MAY also carry an optional wall-clock limit, which SHALL be disabled by default. The documented defaults SHALL be 1,000,000 expansions and 100,000 intermediate rows unless the implementation records a different tuned value with its benchmark. A counter that is absent from the budget SHALL be unlimited.

#### Scenario: Expansion counter

- **WHEN** a query walks relationships
- **THEN** each relationship expansion counts once against the expansion limit

#### Scenario: Row counter

- **WHEN** a stage produces intermediate bindings
- **THEN** each produced binding counts once against the row limit

#### Scenario: Time limit is opt-in

- **WHEN** the budget carries no wall-clock limit
- **THEN** elapsed time never terminates a query

#### Scenario: Defaults are documented

- **WHEN** a caller opens a graph without a budget
- **THEN** the documented expansion and row defaults apply

### Requirement: Query budget override

A caller SHALL be able to set a graph default budget and to override it for one execution. The override SHALL apply only to that execution and SHALL NOT change the graph default. A budget passed to a prepared query execution SHALL apply to every execution that supplies it.

#### Scenario: Graph default applies

- **WHEN** a graph is opened with a budget and a query supplies no override
- **THEN** the query uses the graph default

#### Scenario: Per-query override wins

- **WHEN** a query supplies a larger budget than the graph default
- **THEN** that execution uses the supplied limits and the graph default is unchanged for later queries

#### Scenario: Prepared execution override

- **WHEN** a prepared query is executed twice with different budgets
- **THEN** each execution uses its own override

### Requirement: Budget exhaustion

Exceeding any enabled budget counter SHALL raise a query execution error that names the counter and its limit. The error SHALL never be returned as a partial result, and the same failure SHALL be raised by a query that reaches the limit through matching, filtering, or expansion.

#### Scenario: Expansion limit reached

- **WHEN** a query expands more relationships than the expansion limit allows
- **THEN** the system raises a query execution error naming the expansion counter and its limit

#### Scenario: Row limit reached

- **WHEN** a stage produces more rows than the row limit allows
- **THEN** the system raises a query execution error naming the row counter and its limit

#### Scenario: Time limit reached

- **WHEN** an enabled wall-clock limit elapses during execution
- **THEN** the system raises a query execution error naming the time limit

#### Scenario: No partial result

- **WHEN** a read query exceeds the budget after producing some rows
- **THEN** the call raises and returns no rows

### Requirement: Budget rollback

A write statement that exceeds the budget SHALL roll back every mutation it made, and the graph handle SHALL remain usable for later statements. A write inside an active transaction SHALL undo only its own mutations and leave the caller's transaction usable.

#### Scenario: Write rolls back

- **WHEN** a write statement exceeds the budget after creating nodes
- **THEN** every node it created is absent and the call raises a query execution error

#### Scenario: Handle remains usable

- **WHEN** a write statement exceeds the budget
- **THEN** a later statement on the same graph succeeds

#### Scenario: Active transaction survives

- **WHEN** a write inside an active transaction exceeds the budget
- **THEN** the statement's mutations are undone and the transaction can continue

### Requirement: LET clause

`LET` SHALL be a read stage that adds row-wise bindings without removing existing bindings.
Definitions SHALL evaluate left to right, so a later definition MAY reference an earlier one. A
`LET` assignment that is a direct variable reference SHALL preserve that variable's kind; any other
assignment SHALL bind a scalar. `LET` SHALL be usable as the only row source of a read statement.

#### Scenario: Add a binding

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Kevin Flynn'}) LET cycles = n.cycles + 1 RETURN cycles`
- **THEN** the result contains 37

#### Scenario: Preserve the existing scope

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Tron'}) LET next = n.cycles + 1 RETURN n.designation, next`
- **THEN** the result contains both the original designation and the new binding

#### Scenario: Left-to-right definitions

- **WHEN** a caller submits `LET base = 36, following = base + 1 RETURN following`
- **THEN** the result contains 37

#### Scenario: Leading row source

- **WHEN** a caller submits `LET value = 1 RETURN value`
- **THEN** the statement is accepted and returns one row

#### Scenario: Direct variable preserves its kind

- **WHEN** a caller submits `MATCH (n:Program) LET element = n MATCH (element)-[:ALLIES_WITH]->(m) RETURN m`
- **THEN** the statement is accepted and the second pattern matches from the bound node

### Requirement: LET binding rules

A `LET` name already bound in the current scope, or repeated in the same clause, SHALL be rejected.
A `LET` expression SHALL NOT contain an aggregate. `LET` SHALL NOT be the final clause of a
statement.

#### Scenario: Shadowing is rejected

- **WHEN** a caller submits `MATCH (n:Program) LET n = 1 RETURN n`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Duplicate name is rejected

- **WHEN** a caller submits `LET value = 1, value = 2 RETURN value`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Aggregate is rejected

- **WHEN** a caller submits `LET value = count(*) RETURN value`
- **THEN** the system raises a semantic query error before execution

#### Scenario: LET is not a final clause

- **WHEN** a caller submits `MATCH (n:Program) LET value = 1`
- **THEN** the system raises a query error before execution because the read segment has no `RETURN` or `FINISH`

### Requirement: NEXT composition

`NEXT` SHALL separate two linear segments. The preceding segment's `RETURN` table SHALL be the
input to the following segment. A non-final `RETURN` SHALL act as a projection and scope reset and
MAY aggregate, group, order, and paginate. A write-only segment SHALL pass its bindings unchanged
as a Cypher-compatible extension. A statement SHALL remain one transaction and one query budget.

#### Scenario: Intermediate RETURN feeds NEXT

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Kevin Flynn'}) RETURN n AS element NEXT MATCH (element)-[:TRUSTS]->(m) RETURN m.designation AS name`
- **THEN** the result contains Quorra

#### Scenario: Mid-query grouping

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.cycles AS cycles, count(*) AS total GROUP BY n.cycles NEXT FILTER total > 1 RETURN cycles, total`
- **THEN** the later segment filters the grouped rows

#### Scenario: Write-only segment passes bindings

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Rinzler'}) NEXT MATCH (n) RETURN n.designation AS name`
- **THEN** the result contains Rinzler

#### Scenario: Later segment reads an earlier write

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'}) NEXT MATCH (m:Program {designation: 'Clu'}) RETURN m.designation AS name`
- **THEN** the result contains Clu

#### Scenario: One transaction and budget

- **WHEN** a later segment exceeds the query budget after an earlier segment wrote
- **THEN** the whole statement rolls back and no earlier mutation remains

### Requirement: NEXT YIELD

`NEXT` MAY carry `YIELD item [AS alias] [, ...]`. Each item SHALL name a column of the preceding
result. `YIELD` SHALL keep only the yielded columns and SHALL apply the aliases; an unknown column
or duplicate output name SHALL be rejected. `YIELD` SHALL be rejected after a segment that does not
end in `RETURN`. Without `YIELD`, every preceding column SHALL remain in scope.

#### Scenario: Select columns

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT YIELD name RETURN name`
- **THEN** the later segment sees `name` but not `cycles`

#### Scenario: Rename a column

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name NEXT YIELD name AS designation RETURN designation`
- **THEN** the later segment sees the renamed column

#### Scenario: No YIELD passes all columns

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT RETURN name, cycles`
- **THEN** the later segment sees both columns

#### Scenario: Unknown YIELD column

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name NEXT YIELD missing RETURN name`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Duplicate YIELD alias

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT YIELD name, cycles AS name RETURN name`
- **THEN** the system raises a semantic query error before execution

#### Scenario: YIELD after a write-only segment is rejected

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'}) NEXT YIELD n RETURN n`
- **THEN** the system raises a semantic query error before execution

### Requirement: NEXT placement and result

Each read segment SHALL end with `RETURN` or `FINISH`; a write segment MAY omit the result clause.
Only the final segment's `RETURN` or `FINISH` SHALL produce the statement result; an intermediate
`RETURN` is not the call result. `NEXT` SHALL NOT appear at the start or end of a statement or twice
in a row. `FINISH` SHALL be final, and a statement SHALL contain at most one `FINISH`.

#### Scenario: Final result is the last RETURN

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name NEXT RETURN name`
- **THEN** the statement is accepted and returns the final projected rows

#### Scenario: NEXT at the start is rejected

- **WHEN** a caller submits `NEXT MATCH (n:Program) RETURN n`
- **THEN** the system raises a query error before execution

#### Scenario: NEXT at the end is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN n NEXT`
- **THEN** the system raises a query error before execution

#### Scenario: Consecutive NEXT is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN n NEXT NEXT RETURN n`
- **THEN** the system raises a query error before execution

#### Scenario: FINISH after NEXT

- **WHEN** a caller submits `MATCH (n:Program) NEXT FINISH`
- **THEN** the statement is accepted and returns no result

#### Scenario: NEXT after FINISH is rejected

- **WHEN** a caller submits `MATCH (n:Program) FINISH NEXT MATCH (m:Program) RETURN m`
- **THEN** the system raises a query error before execution

### Requirement: FINISH clause

`FINISH` SHALL end a statement without producing a result. It SHALL apply every preceding read and
write clause and SHALL return an empty result table. `FINISH` SHALL appear only in the final
segment and SHALL NOT be followed by another clause. A write statement MAY omit the result clause
instead of using `FINISH`. `FINISH` SHALL NOT be the only clause of a statement.

#### Scenario: Finish a write

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'}) FINISH`
- **THEN** the node is created and the result has no rows

#### Scenario: Finish a read

- **WHEN** a caller submits `MATCH (n:Program) FINISH`
- **THEN** the statement is accepted and the result has no rows

#### Scenario: Finish is final

- **WHEN** a caller submits `MATCH (n:Program) FINISH RETURN n`
- **THEN** the system raises a query error before execution

#### Scenario: Write-only equivalent

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'})` without `FINISH`
- **THEN** the statement is accepted, creates the node, and returns no result

#### Scenario: FINISH alone is rejected

- **WHEN** a caller submits `FINISH` with no row source and no write clause
- **THEN** the system raises a query error before execution

### Requirement: GROUP BY clause

`GROUP BY` SHALL be a suffix of `RETURN`. It SHALL group the input rows by the listed keys and
produce one row per distinct key combination. A non-aggregate return item SHALL be one of the
keys. A key MAY be a direct variable in scope and need not be returned. `GROUP BY` without
aggregates SHALL deduplicate the keys. `RETURN DISTINCT ... GROUP BY ...` SHALL be accepted.

#### Scenario: Explicit grouping

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.cycles, count(*) AS total GROUP BY n.cycles ORDER BY n.cycles`
- **THEN** one row is returned per distinct cycle count with its total

#### Scenario: Key not returned

- **WHEN** a caller submits `MATCH (n:Program) RETURN count(*) AS total GROUP BY n.cycles`
- **THEN** one row is returned per distinct cycle count, with no `n.cycles` column

#### Scenario: No aggregate deduplicates

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.cycles GROUP BY n.cycles`
- **THEN** one row is returned per distinct cycle count

#### Scenario: Group by a LET binding

- **WHEN** a caller submits `MATCH (n:Program) LET cycles = n.cycles RETURN count(*) AS total GROUP BY cycles`
- **THEN** one row is returned per distinct cycle count

#### Scenario: DISTINCT with GROUP BY

- **WHEN** a caller submits `MATCH (n:Program) RETURN DISTINCT n.cycles GROUP BY n.cycles ORDER BY n.cycles`
- **THEN** the statement is accepted and returns one row per distinct cycle count

### Requirement: GROUP BY keys and grouping rules

GQL grouping keys are direct variable references; pygrafito additionally accepts expressions as a
labeled extension. `GROUP BY ()` SHALL group all input rows into one group and SHALL be valid only
when the projection contains at least one aggregate and no non-aggregate item. `RETURN *` and
`RETURN NO BINDINGS` SHALL NOT be combined with `GROUP BY`. Null key values SHALL form one group.
Empty input SHALL produce no groups unless `GROUP BY ()` is used.

#### Scenario: Expression key extension

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.cycles + 0 AS shifted, count(*) AS total GROUP BY n.cycles + 0`
- **THEN** the statement is accepted and groups by the expression

#### Scenario: Variable key

- **WHEN** a caller submits `MATCH (n:Program) LET cycles = n.cycles RETURN cycles, count(*) AS total GROUP BY cycles`
- **THEN** the statement is accepted and groups by the variable

#### Scenario: Empty key list

- **WHEN** a caller submits `MATCH (n:Program) RETURN count(*) AS total GROUP BY ()`
- **THEN** one row is returned with the total row count

#### Scenario: Empty key list on empty input

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Nobody'}) RETURN count(*) AS total GROUP BY ()`
- **THEN** the result contains one row with total 0

#### Scenario: Return star is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN * GROUP BY n.cycles`
- **THEN** the system raises a query error before execution

#### Scenario: No bindings is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN NO BINDINGS GROUP BY n.cycles`
- **THEN** the system raises a query error before execution

#### Scenario: Null keys form one group

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.missing AS missing, count(*) AS total GROUP BY n.missing`
- **THEN** all null values form one group

#### Scenario: Empty input produces no groups

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Nobody'}) RETURN n.cycles, count(*) GROUP BY n.cycles`
- **THEN** the result contains no rows

### Requirement: CASE expressions

The dialect SHALL support simple and searched `CASE` expressions. A simple `CASE` SHALL compare its
operand with each `WHEN` operand using dialect equality and select the first matching result. A
searched `CASE` SHALL select the first `WHEN` whose predicate is true. Null SHALL never match, a
missing `ELSE` SHALL produce null, and only the selected branch SHALL be evaluated.

#### Scenario: Simple CASE

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Quorra'}) RETURN CASE n.cycles WHEN 37 THEN 'active' ELSE 'unknown' END AS state`
- **THEN** the result contains `active`

#### Scenario: Searched CASE

- **WHEN** a caller submits `MATCH (n:Program) RETURN CASE WHEN n.cycles > 36 THEN 'veteran' ELSE 'rookie' END AS rank`
- **THEN** each row is classified by its cycle count

#### Scenario: Null does not match

- **WHEN** a caller submits `RETURN CASE null WHEN null THEN 'matched' ELSE 'other' END AS result`
- **THEN** the result is `other`

#### Scenario: Else defaults to null

- **WHEN** a caller submits `RETURN CASE WHEN false THEN 1 END AS result`
- **THEN** the result is null

#### Scenario: Only the selected branch is evaluated

- **WHEN** a caller submits `RETURN CASE WHEN true THEN 1 ELSE 1 / 0 END AS result`
- **THEN** the result is 1 and no division error is raised

### Requirement: Map literals

The dialect SHALL support map literals of the form `{key: expression, ...}`. Keys SHALL be static
identifiers or backtick-quoted names; duplicate keys SHALL be rejected, and values SHALL be
evaluated left to right. A map literal SHALL produce an immutable mapping usable in projections,
list literals, and function arguments. Maps SHALL compare by key set and dialect equality, and
SHALL NOT be orderable.

#### Scenario: Project a map

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Tron'}) RETURN {designation: n.designation, cycles: n.cycles} AS program`
- **THEN** the result contains a mapping with both fields

#### Scenario: Empty map

- **WHEN** a caller submits `RETURN {} AS empty`
- **THEN** the result contains an empty mapping

#### Scenario: Duplicate key is rejected

- **WHEN** a caller submits `RETURN {designation: 'Tron', designation: 'Clu'} AS program`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Map equality

- **WHEN** a caller submits `RETURN {designation: 'Tron'} = {designation: 'Tron'} AS same`
- **THEN** the result is true

#### Scenario: Map in a list

- **WHEN** a caller submits `RETURN [{designation: 'Tron'}, {designation: 'Clu'}] AS programs`
- **THEN** the result contains a list of two mappings

#### Scenario: Map is not orderable

- **WHEN** a caller submits `UNWIND [{designation: 'Tron'}] AS row RETURN row ORDER BY row`
- **THEN** the system raises a query execution error

#### Scenario: Map property is rejected

- **WHEN** a caller submits `INSERT (n:Program {metadata: {role: 'system'}})`
- **THEN** the system raises a query execution error and creates no node

### Requirement: List indexing and slicing

The dialect SHALL support zero-based list indexing `list[index]` and slicing `list[start:end]` with
either bound optional. A negative index SHALL count from the end, an out-of-range index SHALL
produce null, and a slice SHALL be end-exclusive and clamp to the list bounds. A null list SHALL
produce null, and a non-list target SHALL raise a query error.

#### Scenario: First and last element

- **WHEN** a caller submits `RETURN [36, 37, 38][0] AS first, [36, 37, 38][-1] AS last`
- **THEN** the first value is 36 and the last value is 38

#### Scenario: Out-of-range index

- **WHEN** a caller submits `RETURN [36, 37][5] AS missing`
- **THEN** the result is null

#### Scenario: Slice with both bounds

- **WHEN** a caller submits `RETURN [36, 37, 38][1:3] AS middle`
- **THEN** the result is `[37, 38]`

#### Scenario: Open slice bounds

- **WHEN** a caller submits `RETURN [36, 37, 38][:2] AS first_two, [36, 37, 38][1:] AS last_two`
- **THEN** the first list is `[36, 37]` and the second is `[37, 38]`

#### Scenario: Slice clamps to the list

- **WHEN** a caller submits `RETURN [36, 37][-5:5] AS values`
- **THEN** the result is `[36, 37]`

#### Scenario: Null list

- **WHEN** a caller submits `RETURN null[0] AS value`
- **THEN** the result is null

#### Scenario: Non-list index target

- **WHEN** a caller submits `RETURN 36[0] AS value`
- **THEN** the system raises a query error before execution

### Requirement: List comprehensions

The dialect SHALL support list comprehensions of the form `[variable IN list [WHERE predicate] [| expression]]`.
The list SHALL be evaluated once, the variable SHALL be local and SHALL NOT shadow an enclosing
variable, and only elements whose predicate is true SHALL be emitted. Without a projection the
element SHALL be emitted; with a projection the expression SHALL be evaluated for each emitted
element. A null list SHALL produce null, and a non-list SHALL raise a query error.

#### Scenario: Transform each element

- **WHEN** a caller submits `RETURN [x IN [36, 37] | x + 1] AS cycles`
- **THEN** the result is `[37, 38]`

#### Scenario: Filter elements

- **WHEN** a caller submits `RETURN [x IN [36, 37, 38] WHERE x > 36] AS cycles`
- **THEN** the result is `[37, 38]`

#### Scenario: Filter and transform

- **WHEN** a caller submits `RETURN [x IN [36, 37, 38] WHERE x > 36 | x * 2] AS cycles`
- **THEN** the result is `[74, 76]`

#### Scenario: Comprehension variable is local

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Tron'}) RETURN [x IN [1, 2] | x] AS values, n.designation AS name`
- **THEN** the result contains `[1, 2]` and `Tron`

#### Scenario: Null comprehension list

- **WHEN** a caller submits `RETURN [x IN null | x] AS values`
- **THEN** the result is null

#### Scenario: Non-list comprehension source

- **WHEN** a caller submits `RETURN [x IN 36 | x] AS values`
- **THEN** the system raises a query error before execution

#### Scenario: Comprehension shadowing is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN [n IN [1, 2] | n] AS values`
- **THEN** the system raises a semantic query error before execution

### Requirement: String concatenation

The dialect SHALL support string concatenation with `||`. Both operands SHALL be strings, null SHALL
propagate, and a non-string operand SHALL raise a query error. `+` SHALL remain numeric addition,
except that it SHALL also concatenate when both operands are strings; mixed string and numeric
operands SHALL raise a query error.

#### Scenario: Canonical concatenation

- **WHEN** a caller submits `RETURN 'Kevin' || ' ' || 'Flynn' AS name`
- **THEN** the result is `Kevin Flynn`

#### Scenario: Null propagates

- **WHEN** a caller submits `RETURN 'Tron' || null AS name`
- **THEN** the result is null

#### Scenario: Non-string operand

- **WHEN** a caller submits `RETURN 'Tron' || 1 AS name`
- **THEN** the system raises a query error

#### Scenario: String plus alias

- **WHEN** a caller submits `RETURN 'Quorra' + ' ' + 'ISO' AS name`
- **THEN** the result is `Quorra ISO`

#### Scenario: Numeric plus remains arithmetic

- **WHEN** a caller submits `RETURN 36 + 1 AS cycles`
- **THEN** the result is 37

#### Scenario: Mixed plus is rejected

- **WHEN** a caller submits `RETURN 'Tron' + 1 AS value`
- **THEN** the system raises a query error

### Requirement: Path functions

The dialect SHALL support `nodes(path)`, `relationships(path)`, and `length(path)`. `nodes` SHALL
return the path's node snapshots in traversal order, `relationships` SHALL return its relationship
snapshots in traversal order, and `length` SHALL return the number of relationships. A null path
SHALL produce null, and a non-path argument SHALL raise a query error.

#### Scenario: Nodes in traversal order

- **WHEN** a caller submits `MATCH p = (a:Program {designation: 'Kevin Flynn'})-[:TRUSTS]->(b:Program) RETURN [n IN nodes(p) | n.designation] AS names`
- **THEN** `names` starts with `Kevin Flynn` and has one entry per path node

#### Scenario: Relationships in traversal order

- **WHEN** a caller submits `MATCH p = (a:Program)-[:TRUSTS]->(b:Program) RETURN [r IN relationships(p) | type(r)] AS types`
- **THEN** `types` has one entry per traversed relationship

#### Scenario: Path length

- **WHEN** a caller submits `MATCH p = (a:Program)-[:TRUSTS]->(b:Program) RETURN length(p) AS hops`
- **THEN** every row returns 1

#### Scenario: Null path

- **WHEN** a caller submits `OPTIONAL MATCH p = (a:Program {designation: 'Nobody'})-[:TRUSTS]->(b) RETURN length(p) AS hops`
- **THEN** the result is null

#### Scenario: Non-path argument

- **WHEN** a caller submits `MATCH (n:Program) RETURN nodes(n) AS nodes`
- **THEN** the system raises a semantic query error before execution

### Requirement: List construction functions

The dialect SHALL support `range` and `reverse`. `range(start, end [, step])` SHALL produce an
inclusive integer list; `step` SHALL default to 1 and SHALL NOT be zero. A step whose direction does
not reach the opposite bound SHALL produce an empty list. `reverse` SHALL return a list with its
elements in reverse order. Null arguments SHALL produce null, and wrong types or a zero step SHALL
raise a query error.

#### Scenario: Inclusive range

- **WHEN** a caller submits `RETURN range(36, 38) AS cycles`
- **THEN** the result is `[36, 37, 38]`

#### Scenario: Range with a step

- **WHEN** a caller submits `RETURN range(36, 40, 2) AS cycles`
- **THEN** the result is `[36, 38, 40]`

#### Scenario: Descending range

- **WHEN** a caller submits `RETURN range(40, 36, -2) AS cycles`
- **THEN** the result is `[40, 38, 36]`

#### Scenario: Empty range direction

- **WHEN** a caller submits `RETURN range(36, 40, -1) AS cycles`
- **THEN** the result is `[]`

#### Scenario: Reverse a list

- **WHEN** a caller submits `RETURN reverse([36, 37, 38]) AS cycles`
- **THEN** the result is `[38, 37, 36]`

#### Scenario: Null range argument

- **WHEN** a caller submits `RETURN range(36, null) AS cycles`
- **THEN** the result is null

#### Scenario: Zero range step

- **WHEN** a caller submits `RETURN range(36, 38, 0) AS cycles`
- **THEN** the system raises a query error

#### Scenario: Wrong range type

- **WHEN** a caller submits `RETURN range('36', 38) AS cycles`
- **THEN** the system raises a query error

### Requirement: List element functions

The dialect SHALL support `head`, `last`, and `tail`. `head` SHALL return the first element, `last`
the last element, and `tail` all but the first element. `head` and `last` SHALL return null for an
empty list, and `tail` SHALL return an empty list. Null arguments SHALL produce null, and a non-list
argument SHALL raise a query error.

#### Scenario: Head and last

- **WHEN** a caller submits `RETURN head([36, 37, 38]) AS first, last([36, 37, 38]) AS final`
- **THEN** the first value is 36 and the final value is 38

#### Scenario: Tail

- **WHEN** a caller submits `RETURN tail([36, 37, 38]) AS rest`
- **THEN** the result is `[37, 38]`

#### Scenario: Empty list

- **WHEN** a caller submits `RETURN head([]) AS first, last([]) AS final, tail([]) AS rest`
- **THEN** the first two values are null and the third is `[]`

#### Scenario: Null list argument

- **WHEN** a caller submits `RETURN head(null) AS first`
- **THEN** the result is null

#### Scenario: Non-list argument

- **WHEN** a caller submits `RETURN tail(36) AS rest`
- **THEN** the system raises a query error

### Requirement: String scalar functions

The dialect SHALL support `split`, `substring`, and `replace`. `split(string, delimiter)` SHALL
split on every non-empty delimiter and retain empty segments. `substring(string, start [, length])`
SHALL use a zero-based start and an optional non-negative length. `replace(string, search,
replacement)` SHALL replace every non-empty search occurrence. Null arguments SHALL produce null,
and invalid delimiters, negative positions, or wrong types SHALL raise a query error.

#### Scenario: Split a string

- **WHEN** a caller submits `RETURN split('Kevin Flynn|Quorra', '|') AS names`
- **THEN** the result is `['Kevin Flynn', 'Quorra']`

#### Scenario: Substring to the end

- **WHEN** a caller submits `RETURN substring('Kevin Flynn', 6) AS surname`
- **THEN** the result is `Flynn`

#### Scenario: Substring with a length

- **WHEN** a caller submits `RETURN substring('Quorra', 1, 3) AS value`
- **THEN** the result is `uor`

#### Scenario: Replace every occurrence

- **WHEN** a caller submits `RETURN replace('Tron|Clu|Tron', 'Tron', 'Rinzler') AS value`
- **THEN** the result is `Rinzler|Clu|Rinzler`

#### Scenario: Null string argument

- **WHEN** a caller submits `RETURN split(null, '|') AS values`
- **THEN** the result is null

#### Scenario: Empty delimiter

- **WHEN** a caller submits `RETURN split('Tron', '') AS values`
- **THEN** the system raises a query error

#### Scenario: Negative substring start

- **WHEN** a caller submits `RETURN substring('Tron', -1) AS value`
- **THEN** the system raises a query error

#### Scenario: Wrong string function type

- **WHEN** a caller submits `RETURN replace(36, '3', '4') AS value`
- **THEN** the system raises a query error

### Requirement: Numeric and boolean scalar functions

The dialect SHALL support `toBoolean`, `round`, `ceil`, and `floor`. `toBoolean` SHALL convert
booleans, the strings `true` and `false` case-insensitively, and the numbers 0 and 1; other inputs
SHALL produce null. `round(number [, precision])` SHALL round to the nearest value with ties away
from zero, using a non-negative precision. `ceil` and `floor` SHALL return integers. Null arguments
SHALL produce null, and wrong types or negative precision SHALL raise a query error.

#### Scenario: Convert a boolean string

- **WHEN** a caller submits `RETURN toBoolean('TRUE') AS value`
- **THEN** the result is true

#### Scenario: Convert a numeric boolean

- **WHEN** a caller submits `RETURN toBoolean(0) AS value`
- **THEN** the result is false

#### Scenario: Invalid boolean input

- **WHEN** a caller submits `RETURN toBoolean('maybe') AS value`
- **THEN** the result is null

#### Scenario: Round a number

- **WHEN** a caller submits `RETURN round(36.5) AS value`
- **THEN** the result is 37

#### Scenario: Round with precision

- **WHEN** a caller submits `RETURN round(36.346, 2) AS value`
- **THEN** the result is 36.35

#### Scenario: Ceiling and floor

- **WHEN** a caller submits `RETURN ceil(36.1) AS up, floor(36.9) AS down`
- **THEN** the result is 37 and 36

#### Scenario: Null numeric argument

- **WHEN** a caller submits `RETURN round(null) AS value`
- **THEN** the result is null

#### Scenario: Negative precision

- **WHEN** a caller submits `RETURN round(36.5, -1) AS value`
- **THEN** the system raises a query error

### Requirement: WITH * projection

`WITH *` SHALL project every variable in the current scope in introduction order, preserving each
variable's kind and snapshot. It SHALL be the only projection item in the clause, MAY carry
`DISTINCT`, `WHERE`, `ORDER BY`, `OFFSET`, or `LIMIT`, and SHALL NOT be the final clause of a
statement. A `WITH *` that would duplicate a name SHALL be rejected.

#### Scenario: Preserve the full scope

- **WHEN** a caller submits `MATCH (a:Program)-[r:ALLIES_WITH]->(b:Program) WITH * RETURN a.designation, b.designation`
- **THEN** both nodes and the relationship remain visible

#### Scenario: Keep variable kinds

- **WHEN** a caller submits `MATCH (a:Program) WITH * RETURN labels(a) AS labels`
- **THEN** `a` is still a node binding

#### Scenario: Distinct scope

- **WHEN** a caller submits `MATCH (n:Program) WITH DISTINCT * RETURN count(*) AS total`
- **THEN** duplicate complete bindings are removed before the count

#### Scenario: Filter and paginate the scope

- **WHEN** a caller submits `MATCH (n:Program) WITH * WHERE n.cycles > 36 ORDER BY n.cycles LIMIT 2 RETURN n`
- **THEN** the filter, ordering, and limit apply to the preserved scope

#### Scenario: Mixing star with items is rejected

- **WHEN** a caller submits `MATCH (n:Program) WITH *, n.cycles AS cycles RETURN n`
- **THEN** the system raises a syntax error before execution

#### Scenario: WITH * cannot end a statement

- **WHEN** a statement ends with `WITH *` and has no following clause
- **THEN** the system raises a query error

### Requirement: Query expression subqueries

The dialect SHALL support read-only `EXISTS { ... }` and `COUNT { ... }` query expressions. The
braces SHALL contain a read-only sequence of query stages with at least one row source and no final
result clause. `EXISTS` SHALL return true when the inner query produces at least one row and false
otherwise; `COUNT` SHALL return the number of inner rows. Both SHALL be usable in scalar expression
positions in read stages, projections, `LET`, grouping keys, and ordering.

#### Scenario: Correlated EXISTS

- **WHEN** a caller submits `MATCH (n:Program) WHERE EXISTS { MATCH (n)-[:TRUSTS]->(m:Program) } RETURN n.designation AS name`
- **THEN** only programs with at least one outgoing `TRUSTS` relationship are returned

#### Scenario: Uncorrelated EXISTS

- **WHEN** a caller submits `MATCH (n:Program) WHERE EXISTS { MATCH (m:Program {designation: 'Tron'}) } RETURN n.designation AS name`
- **THEN** every program is returned when the inner graph has Tron

#### Scenario: Correlated COUNT

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, COUNT { MATCH (n)-[:TRUSTS]->(m:Program) } AS trusts`
- **THEN** `trusts` is the number of matching inner rows for each program

#### Scenario: Uncorrelated COUNT

- **WHEN** a caller submits `MATCH (n:Program) RETURN COUNT { MATCH (m:Program) } AS programs`
- **THEN** every row has the same total program count

#### Scenario: No inner match

- **WHEN** a caller evaluates `EXISTS` or `COUNT` for an inner query that matches no rows
- **THEN** the result is false or 0 respectively

#### Scenario: Inner query needs a row source

- **WHEN** a caller submits `MATCH (n:Program) RETURN EXISTS { RETURN 1 } AS found`
- **THEN** the system raises a query error before execution

#### Scenario: Write inside a subquery is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN EXISTS { INSERT (m:Program) } AS found`
- **THEN** the system raises a semantic query error and changes nothing

#### Scenario: Result clause inside a subquery is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN EXISTS { MATCH (m:Program) RETURN m } AS found`
- **THEN** the system raises a query error before execution

### Requirement: Subquery scope and correlation

An outer variable referenced inside a subquery SHALL refer to the outer binding. A name introduced
inside the subquery SHALL be local and SHALL NOT leak to the outer scope. A subquery that introduces
a name already bound by `LET` or `WITH` in the same inner scope SHALL be rejected. An uncorrelated
subquery SHALL evaluate independently of the current row; a correlated subquery SHALL evaluate
against the current row.

#### Scenario: Outer variable is visible

- **WHEN** a subquery matches from an outer `n` binding
- **THEN** the inner pattern uses the outer node rather than a new node

#### Scenario: Inner variable is local

- **WHEN** a caller references an inner `m` binding after the subquery
- **THEN** the system raises a semantic query error for the unbound variable

#### Scenario: Shadowing is rejected

- **WHEN** a subquery defines a `LET m = ...` when `m` is already an inner binding
- **THEN** the system raises a semantic query error

#### Scenario: Correlated result varies by row

- **WHEN** a caller evaluates a correlated `COUNT` for several outer rows
- **THEN** each row can return a different count

#### Scenario: Uncorrelated result is constant

- **WHEN** a caller evaluates an uncorrelated `EXISTS` for several outer rows
- **THEN** every row receives the same boolean result

### Requirement: Subquery budget and snapshot

A subquery SHALL share the enclosing statement's query budget, transaction, and consistent
snapshot. Relationship expansions and intermediate rows inside a subquery SHALL count against the
same budget. A budget failure SHALL raise the same query execution error and SHALL NOT produce a
partial result, and a subquery SHALL NOT start a transaction.

#### Scenario: Subquery expansions use the budget

- **WHEN** a subquery expands relationships beyond the enclosing expansion limit
- **THEN** the system raises a query execution error naming the expansion limit

#### Scenario: Subquery rows use the budget

- **WHEN** a subquery produces more intermediate rows than the enclosing row limit
- **THEN** the system raises a query execution error naming the row limit

#### Scenario: No partial result

- **WHEN** a subquery exceeds the budget after producing some rows
- **THEN** the statement raises and returns no rows

#### Scenario: Shared snapshot

- **WHEN** a statement with a subquery runs while another connection changes a row
- **THEN** the outer query and subquery observe the same execution snapshot

### Requirement: Set operations

The dialect SHALL support compound queries built from two or more read-only linear statements with
`UNION`, `UNION ALL`, `INTERSECT`, `INTERSECT ALL`, `EXCEPT`, and `EXCEPT ALL`, and SHALL accept
an explicit `DISTINCT` quantifier on `UNION`, `INTERSECT`, and `EXCEPT`. Operators SHALL be
left-associative and SHALL combine the final `RETURN` tables of their operands. A compound query
SHALL NOT contain a write, `FINISH`, or `RETURN NO BINDINGS`.

#### Scenario: UNION ALL preserves rows

- **WHEN** a caller combines two program queries with `UNION ALL`
- **THEN** every row from both operands appears, including duplicates

#### Scenario: UNION removes duplicates

- **WHEN** a caller combines two queries with `UNION`
- **THEN** each distinct row appears once

#### Scenario: INTERSECT keeps common rows

- **WHEN** a caller combines two queries with `INTERSECT`
- **THEN** only rows present in both operands are returned

#### Scenario: EXCEPT removes the second operand

- **WHEN** a caller combines two queries with `EXCEPT`
- **THEN** rows present only in the first operand are returned

#### Scenario: Operators are left-associative

- **WHEN** a caller writes three operands without grouping
- **THEN** the left pair is combined first

#### Scenario: Write operand is rejected

- **WHEN** a caller combines a `CREATE` statement with a read query
- **THEN** the system raises a semantic query error and changes nothing

#### Scenario: Result-less forms are rejected

- **WHEN** a caller uses `FINISH` or `RETURN NO BINDINGS` as a set operand
- **THEN** the system raises a query error before execution

### Requirement: Set quantifiers

A set operator SHALL accept an optional `ALL` or `DISTINCT` quantifier. The bare operator and
`DISTINCT` SHALL use set semantics and emit each distinct row once. `INTERSECT ALL` SHALL emit
`min(left_count, right_count)` copies of each row; `EXCEPT ALL` SHALL emit
`max(left_count - right_count, 0)` copies. Duplicate counts SHALL use the dialect's canonical row
equality.

#### Scenario: Explicit DISTINCT is the default

- **WHEN** a caller combines two queries with `UNION DISTINCT`
- **THEN** the result is the same as `UNION`, with each distinct row appearing once

#### Scenario: INTERSECT ALL keeps the smaller count

- **WHEN** the left operand has three copies of a row and the right operand has two
- **THEN** `INTERSECT ALL` returns two copies

#### Scenario: EXCEPT ALL subtracts counts

- **WHEN** the left operand has three copies of a row and the right operand has two
- **THEN** `EXCEPT ALL` returns one copy

#### Scenario: EXCEPT ALL keeps unmatched duplicates

- **WHEN** the right operand has no copy of a row
- **THEN** `EXCEPT ALL` returns every copy from the left operand

#### Scenario: Canonical equality counts duplicates

- **WHEN** one operand returns the integer 36 and another returns the float 36.0
- **THEN** `INTERSECT ALL` and `EXCEPT ALL` treat them as the same row

#### Scenario: Quantifiers apply per operator

- **WHEN** a compound mixes `UNION ALL` and `INTERSECT ALL`
- **THEN** each operator applies its own quantifier left to right

### Requirement: Set operation columns

Every operand of a set operation SHALL produce the same number of columns in the same order with the
same names. The first operand SHALL define the result column names. A mismatch SHALL raise a
semantic query error before execution. Column values SHALL use the dialect's value model; no
implicit type coercion SHALL occur, and duplicate detection SHALL use dialect equality.

#### Scenario: Column count mismatch

- **WHEN** one operand returns one column and another returns two
- **THEN** the system raises a semantic query error

#### Scenario: Column name mismatch

- **WHEN** operands return the same number of columns with different names
- **THEN** the system raises a semantic query error

#### Scenario: First operand names the result

- **WHEN** the first operand returns `name` and the second returns the same column under the same name
- **THEN** the result columns are `name`

#### Scenario: Heterogeneous values are not coerced

- **WHEN** the same column contains an integer in one operand and a string in another
- **THEN** both values remain in the result without coercion

#### Scenario: Numeric duplicates use dialect equality

- **WHEN** one operand returns the integer 36 and another returns the float 36.0
- **THEN** `UNION` treats them as the same value

### Requirement: Set operation ordering and pagination

`ORDER BY`, `OFFSET`, and `LIMIT` after a compound query SHALL apply to the combined result.
Compound ordering keys SHALL be output column names from the first operand. Ordering and pagination
clauses inside an operand's final `RETURN` SHALL be rejected; intermediate `RETURN` clauses in a
`NEXT` segment MAY still carry them.

#### Scenario: Order the combined result

- **WHEN** a caller writes `UNION` followed by `ORDER BY name`
- **THEN** the combined rows are sorted by the output `name` column

#### Scenario: Paginate the combined result

- **WHEN** a caller writes `UNION` followed by `OFFSET` and `LIMIT`
- **THEN** pagination applies after duplicate removal and ordering

#### Scenario: Operand ordering is rejected

- **WHEN** an operand's final `RETURN` carries `ORDER BY`, `OFFSET`, or `LIMIT`
- **THEN** the system raises a syntax error before execution

#### Scenario: Sort expression must be a column

- **WHEN** a compound query orders by an expression that is not an output column
- **THEN** the system raises a semantic query error

#### Scenario: Null ordering is preserved

- **WHEN** a compound query orders an output column with `NULLS FIRST` or `NULLS LAST`
- **THEN** null placement follows the requested rule

### Requirement: Set operation execution

A compound query SHALL execute all operands in one transaction and one snapshot under one budget.
Each operand SHALL be read-only and evaluated in source order; a budget failure SHALL raise and
return no partial result. The result SHALL expose the first operand's columns and a zero mutation
summary.

#### Scenario: One snapshot

- **WHEN** a compound query runs while another connection changes a row between operands
- **THEN** every operand observes the state at execution start

#### Scenario: Shared budget

- **WHEN** the combined operands exceed the row or expansion budget
- **THEN** the system raises a query execution error naming the counter

#### Scenario: Zero mutation summary

- **WHEN** a compound query succeeds
- **THEN** every mutation count in its summary is zero

#### Scenario: No partial rows on failure

- **WHEN** a later operand exceeds the budget
- **THEN** the call raises and returns no rows
