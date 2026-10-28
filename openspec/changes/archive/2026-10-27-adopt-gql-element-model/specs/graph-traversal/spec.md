# Spec Delta

## MODIFIED Requirements

### Requirement: Relationship-unique path enumeration

The system SHALL enumerate paths between two nodes whose length is within an inclusive minimum and maximum depth. Within one path a relationship SHALL NOT be used more than once, while nodes MAY repeat.

#### Scenario: Two routes produce two paths

- **WHEN** two distinct two-hop routes connect the start and end nodes
- **THEN** two paths are returned

#### Scenario: Node may repeat

- **WHEN** a valid path returns to a previously visited node without reusing a relationship
- **THEN** the path is included

#### Scenario: Relationship may not repeat

- **WHEN** continuing a path would reuse a relationship already in that path
- **THEN** that extension is not returned

#### Scenario: Parallel relationships are distinct

- **WHEN** two separate relationships of the same label connect the same pair of nodes
- **THEN** they can produce distinct paths

#### Scenario: Undirected relationship may be traversed either way

- **WHEN** an undirected relationship connects two nodes on a path
- **THEN** the path may traverse it from either endpoint

#### Scenario: Undirected relationship may not repeat

- **WHEN** continuing a path would reuse an undirected relationship already in that path
- **THEN** that extension is not returned

#### Scenario: Depth range

- **WHEN** the minimum depth is 2 and the maximum depth is 3
- **THEN** only paths with two or three relationships are returned

### Requirement: Shortest path

The system SHALL return one path with the fewest relationships between two nodes, or no path when none exists. A node SHALL have a zero-length path to itself.

#### Scenario: Shortest route

- **WHEN** several routes connect the start and end nodes
- **THEN** the returned path has the minimum number of relationships

#### Scenario: Unreachable

- **WHEN** no route connects the two nodes within the allowed direction, labels, and depth
- **THEN** the system returns no path

#### Scenario: Same node

- **WHEN** the start and end node are the same
- **THEN** the system returns a path containing that node and no relationships

#### Scenario: Undirected route

- **WHEN** the only route uses an undirected relationship
- **THEN** the shortest path includes it

### Requirement: Path shape

The system SHALL expose a path as an ordered sequence of nodes and an ordered sequence of relationships, with its length equal to the number of relationships. The node sequence SHALL follow the path from start to end even when relationships are traversed against their stored direction or are undirected.

#### Scenario: Path contents

- **WHEN** a path is returned
- **THEN** its nodes are ordered from start to end and its relationships are in traversal order

#### Scenario: Incoming path

- **WHEN** a path is built by traversing relationships in the incoming direction
- **THEN** the node sequence still runs from the start node to the end node

#### Scenario: Undirected path

- **WHEN** a path includes an undirected relationship
- **THEN** the node sequence still runs from the start node to the end node

### Requirement: Proportional traversal work

The system SHALL perform traversal work proportional to the region explored within the caller's direction, label, and depth bounds and SHALL NOT read elements outside that region. Starting a traversal SHALL NOT require reading the whole graph.

#### Scenario: One-hop neighborhood on a large graph

- **WHEN** a caller traverses one hop from a node in a graph with many unconnected elements
- **THEN** only the start node and the nodes one hop away are read

#### Scenario: Disconnected component is not read

- **WHEN** the graph contains a component that cannot be reached within the bounds
- **THEN** no element of that component is read

#### Scenario: Depth bound is respected

- **WHEN** the maximum depth is 2
- **THEN** nodes and relationships that first become reachable at depth 3 are not read

#### Scenario: Isolated start node

- **WHEN** a caller traverses from a node with no incident relationship
- **THEN** only the start node is read and no step is produced

#### Scenario: Type filter narrows the read set

- **WHEN** a caller restricts traversal to one relationship label
- **THEN** relationships that do not carry that label at the same level are not followed and not captured

#### Scenario: Undirected edge is inside the region

- **WHEN** an undirected relationship is incident to a node inside the depth bound
- **THEN** the relationship and its other endpoint are captured as part of the region

## REMOVED Requirements

### Requirement: Direction and type filtering

**Reason**: Traversal filters use relationship labels, not a single relationship type, and undirected relationships must be traversable from either endpoint.

**Migration**: Use the replacement requirement, `Direction and label filtering`, which keeps the outgoing, incoming, and both directions and applies a label set filter.

## ADDED Requirements

### Requirement: Direction and label filtering

The system SHALL traverse in outgoing, incoming, or both directions, optionally restricted to relationship labels. An empty label set SHALL mean all labels; a relationship SHALL match when it carries any listed label. Outgoing SHALL follow directed relationships from the current node and undirected relationships incident to it. Incoming SHALL follow directed relationships to the current node and undirected relationships incident to it. Both SHALL follow every incident relationship.

#### Scenario: Outgoing traversal

- **WHEN** a caller traverses outgoing from a node
- **THEN** directed relationships whose start is the current node and undirected relationships incident to it are followed

#### Scenario: Incoming traversal

- **WHEN** a caller traverses incoming from a node
- **THEN** directed relationships whose end is the current node and undirected relationships incident to it are followed

#### Scenario: Both directions

- **WHEN** a caller traverses in both directions
- **THEN** relationships are followed regardless of which endpoint is the current node

#### Scenario: Label filter

- **WHEN** a caller restricts traversal to label KNOWS
- **THEN** relationships that do not carry that label are not followed

#### Scenario: Multi-label relationship

- **WHEN** a caller restricts traversal to labels KNOWS and TRUSTS and a relationship carries one of them
- **THEN** the relationship is followed

#### Scenario: Undirected edge from either endpoint

- **WHEN** a caller traverses outgoing or incoming from either endpoint of an undirected relationship
- **THEN** the relationship is followed

#### Scenario: Empty label set

- **WHEN** a caller supplies no label filter
- **THEN** relationships of every label set are eligible
