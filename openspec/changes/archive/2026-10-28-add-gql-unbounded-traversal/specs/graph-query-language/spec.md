## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Deferred open-ended traversal

**Reason**: Open-ended quantifiers are implemented by this change.

**Migration**: Use the open-ended traversal requirement and the canonical open forms `{m,}`, `*`, and `+`; the legacy `*n..` form remains accepted with trail semantics.

### Requirement: Deferred construct diagnostics

**Reason**: The open bound was the only construct routed through the deferred diagnostic class, and it is now implemented. Remaining gated path constructs keep their positioned rejection until their own changes land.

**Migration**: None. A deferred or gated construct is still rejected before execution; the profile and the query-language reference state which change implements it.

### Requirement: Variable-length relationship patterns

**Reason**: Open-ended quantifiers are implemented by this change, so the requirement is replaced by a quantifier requirement that covers both closed and open forms.

**Migration**: Use `Relationship quantifiers`; the closed forms, legacy forms, and default-mode rules are unchanged.

## ADDED Requirements

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
