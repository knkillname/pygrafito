# Spec Delta

## MODIFIED Requirements

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

### Requirement: Variable-length relationship patterns

A relationship pattern MAY carry a quantifier. The canonical closed forms SHALL be `{n}` for exactly `n` hops, `{m,n}` for a bounded range, and `{,n}` for at most `n` hops. The legacy forms `*n`, `*n..m`, and `*0..m` SHALL remain a compatibility construct. Every hop SHALL apply the pattern's labels, direction, property map, and predicate. Bounds SHALL be non-negative integers with a lower bound not greater than the upper bound.

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

#### Scenario: Unbounded quantifier is rejected

- **WHEN** a caller writes `MATCH (a)-[*]->(b) RETURN b`, `MATCH (a)-[*1..]->(b) RETURN b`, or `MATCH (a)-[:ALLIES_WITH{1,}]->(b) RETURN b`
- **THEN** the system raises a deferred-construct error naming the change that implements unbounded traversal, and executes nothing

#### Scenario: Invalid bounds are rejected

- **WHEN** a caller writes a negative bound or a lower bound greater than the upper bound
- **THEN** the system raises a query error before execution

#### Scenario: Canonical quantifier is gated

- **WHEN** a caller writes `MATCH (a)-[:ALLIES_WITH{1,3}]->(b) RETURN b`
- **THEN** the closed canonical form is accepted and traversed under its resolved path mode; only the open-ended canonical form `{1,}` remains gated as deferred

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

### Requirement: Gated construct diagnostics

A construct the profile lists as gated SHALL raise a semantic query error that names the construct and the follow-up change that implements it. The error SHALL NOT be reported as an unexpected token, and the statement SHALL NOT execute or partially execute.

#### Scenario: Quantifier gate

- **WHEN** a caller uses an open-ended upper bound (`*`, `+`, `*n..`, or `{m,}`)
- **THEN** the error names the construct and `add-gql-unbounded-traversal`

#### Scenario: Composition gate

- **WHEN** a caller uses `LET`, `NEXT`, or `GROUP BY`
- **THEN** the error names the construct and `add-gql-composition`

#### Scenario: Statement does not execute

- **WHEN** a gated construct appears in a statement that also contains a write clause
- **THEN** the statement changes no data

## ADDED Requirements

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

### Requirement: Deferred open-ended traversal

An open-ended upper bound SHALL be out of scope for this release. The forms `*`, `+`, `*n..`, and `{m,}` SHALL be rejected with a deferred-construct error that names the follow-up change, and the rejection SHALL happen before execution.

#### Scenario: Open-ended forms are rejected

- **WHEN** a caller writes `*`, `+`, `*1..`, or `{1,}` as a quantifier
- **THEN** the system raises a deferred-construct error before execution

#### Scenario: Closed forms are accepted

- **WHEN** a caller writes `{1}`, `{1,3}`, `{,3}`, `*1`, `*1..3`, or `*0..3`
- **THEN** the statement is accepted and matched under its resolved path mode
