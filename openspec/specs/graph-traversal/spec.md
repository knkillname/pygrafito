# graph-traversal Specification

## Purpose

Defines direction-aware graph traversal: distinct reachable nodes, relationship-unique path enumeration, and shortest paths over the persisted property graph.

## Requirements

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

The system SHALL evaluate a traversal against a consistent region materialized when the call is made, so that writes made after the traversal starts do not change its results. The materialized region SHALL contain every node and relationship the traversal can reach under its direction, type, and depth bounds.

#### Scenario: Snapshot isolation

- **WHEN** another write changes the graph while a traversal is being iterated
- **THEN** the traversal continues to reflect the graph state at the start of the traversal

#### Scenario: Bounded region is complete

- **WHEN** a traversal is bounded by a maximum depth
- **THEN** every result within the bound is produced even though elements outside the bound are not loaded


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


### Requirement: Bounded shortest-path search

The system SHALL search for a shortest path by expanding frontiers from both endpoints, stopping when the frontiers meet or the maximum depth is exhausted. It SHALL NOT read elements outside the explored region.

#### Scenario: Frontiers meet early

- **WHEN** a short route connects the endpoints in a graph with a large disconnected remainder
- **THEN** the shortest path is returned without reading the disconnected remainder

#### Scenario: No route within the bound

- **WHEN** no route exists within the maximum depth
- **THEN** the system returns no path and stops expanding at the bound

#### Scenario: Missing endpoint

- **WHEN** either endpoint does not exist
- **THEN** the system raises a not-found error before expanding a frontier

#### Scenario: Same node

- **WHEN** the start and end node are the same
- **THEN** the system returns a zero-length path without reading any relationship


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
