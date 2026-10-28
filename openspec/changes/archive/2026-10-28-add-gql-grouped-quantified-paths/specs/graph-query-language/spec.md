# Spec Delta: graph-query-language

## ADDED Requirements

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
