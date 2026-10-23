# graph-traversal Specification

## Purpose

Defines direction-aware graph traversal: distinct reachable nodes, relationship-unique path enumeration, and shortest paths over the persisted property graph.

## Requirements

### Requirement: Direction and type filtering

The system SHALL traverse relationships in outgoing, incoming, or both directions, optionally restricted to a set of relationship types. An empty or absent type set SHALL mean all types.

#### Scenario: Outgoing traversal

- **WHEN** a caller traverses outgoing from a node
- **THEN** only relationships whose start is the current node are followed

#### Scenario: Incoming traversal

- **WHEN** a caller traverses incoming from a node
- **THEN** only relationships whose end is the current node are followed

#### Scenario: Both directions

- **WHEN** a caller traverses in both directions
- **THEN** relationships are followed regardless of which endpoint is the current node

#### Scenario: Type filter

- **WHEN** a caller restricts traversal to type KNOWS
- **THEN** relationships of other types are not followed

### Requirement: Distinct reachable nodes

The system SHALL provide neighborhood traversal that yields every node reachable within a maximum number of hops exactly once, together with its shortest depth. The start node SHALL NOT be yielded.

#### Scenario: Diamond

- **WHEN** two two-hop routes lead from the start to the same node
- **THEN** that node is yielded once with depth 2

#### Scenario: Cycle does not duplicate nodes

- **WHEN** the graph contains a cycle back to an already visited node
- **THEN** each reachable node is yielded at most once

#### Scenario: Start excluded

- **WHEN** a caller traverses from a node with a positive maximum depth
- **THEN** the start node is not part of the yielded results

#### Scenario: Depth bound

- **WHEN** the maximum depth is 2
- **THEN** nodes at distance 3 or more are not yielded

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

- **WHEN** two separate relationships of the same type connect the same pair of nodes
- **THEN** they can produce distinct paths

#### Scenario: Depth range

- **WHEN** the minimum depth is 2 and the maximum depth is 3
- **THEN** only paths with two or three relationships are returned

### Requirement: Shortest path

The system SHALL return one path with the fewest relationships between two nodes, or no path when none exists. A node SHALL have a zero-length path to itself.

#### Scenario: Shortest route

- **WHEN** several routes connect the start and end nodes
- **THEN** the returned path has the minimum number of relationships

#### Scenario: Unreachable

- **WHEN** no route connects the two nodes within the allowed direction, types, and depth
- **THEN** the system returns no path

#### Scenario: Same node

- **WHEN** the start and end node are the same
- **THEN** the system returns a path containing that node and no relationships

### Requirement: Path shape

The system SHALL expose a path as an ordered sequence of nodes and an ordered sequence of relationships, with its length equal to the number of relationships. The node sequence SHALL follow the path from start to end even when relationships are traversed against their stored direction.

#### Scenario: Path contents

- **WHEN** a path is returned
- **THEN** its nodes are ordered from start to end and its relationships are in traversal order

#### Scenario: Incoming path

- **WHEN** a path is built by traversing relationships in the incoming direction
- **THEN** the node sequence still runs from the start node to the end node

### Requirement: Bounded and lazy enumeration

The system SHALL require a maximum depth for path enumeration and SHALL yield paths lazily so a caller can stop early. An optional result limit SHALL cap the number of paths produced.

#### Scenario: Maximum depth required

- **WHEN** a caller omits the maximum depth for path enumeration
- **THEN** the system rejects the request

#### Scenario: Result limit

- **WHEN** a caller sets a limit of 10 and more than 10 paths exist
- **THEN** at most 10 paths are produced

#### Scenario: Early stop

- **WHEN** a caller stops iterating before exhausting the results
- **THEN** no further paths are computed

### Requirement: Traversal input validation

The system SHALL reject negative depths, a minimum depth greater than the maximum depth, and traversal from or to a missing node.

#### Scenario: Invalid depth range

- **WHEN** the minimum depth exceeds the maximum depth
- **THEN** the system raises a validation error

#### Scenario: Missing start node

- **WHEN** a caller traverses from a node id that does not exist
- **THEN** the system raises a not-found error

### Requirement: Consistent traversal snapshot

The system SHALL evaluate a traversal against a consistent graph snapshot so that writes made after the traversal starts do not change its results.

#### Scenario: Snapshot isolation

- **WHEN** another write changes the graph while a traversal is being iterated
- **THEN** the traversal continues to reflect the graph state at the start of the traversal
