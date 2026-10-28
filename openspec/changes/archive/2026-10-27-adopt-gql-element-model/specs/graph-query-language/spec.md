# Spec Delta

## MODIFIED Requirements

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
