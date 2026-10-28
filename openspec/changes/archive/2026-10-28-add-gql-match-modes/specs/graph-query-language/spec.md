# Spec Delta: graph-query-language

## ADDED Requirements

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
