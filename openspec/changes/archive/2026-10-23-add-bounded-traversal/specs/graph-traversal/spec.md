# Spec Delta

## MODIFIED Requirements

### Requirement: Consistent traversal snapshot

The system SHALL evaluate a traversal against a consistent region materialized when the call is made, so that writes made after the traversal starts do not change its results. The materialized region SHALL contain every node and relationship the traversal can reach under its direction, type, and depth bounds.

#### Scenario: Snapshot isolation

- **WHEN** another write changes the graph while a traversal is being iterated
- **THEN** the traversal continues to reflect the graph state at the start of the traversal

#### Scenario: Bounded region is complete

- **WHEN** a traversal is bounded by a maximum depth
- **THEN** every result within the bound is produced even though elements outside the bound are not loaded

## ADDED Requirements

### Requirement: Proportional traversal work

The system SHALL perform traversal work proportional to the region explored within the caller's direction, type, and depth bounds and SHALL NOT read elements outside that region. Starting a traversal SHALL NOT require reading the whole graph.

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

- **WHEN** a caller restricts traversal to one relationship type
- **THEN** relationships of other types at the same level are not followed and not captured

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
