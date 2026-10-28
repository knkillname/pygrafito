# Spec Delta

## MODIFIED Requirements

### Requirement: Element identity

The system SHALL assign unique integer ids to live nodes and relationships. An id SHALL NOT be reused after the element is deleted.

#### Scenario: Distinct live ids

- **WHEN** a caller creates several nodes and relationships
- **THEN** every live element has a distinct id

#### Scenario: Deleted id is not reused

- **WHEN** a caller deletes an element and then creates another element of the same kind
- **THEN** the new element receives an id that no deleted element ever used

### Requirement: Lookup by label and property

The system SHALL find nodes carrying all specified labels and matching exact property values, and SHALL find relationships carrying all specified labels, optionally restricted by direction, and matching exact property values. Property matching SHALL be type-sensitive and SHALL respect list order.

#### Scenario: Find nodes by label and property

- **WHEN** a caller looks up nodes labeled Person with an integer age of 36
- **THEN** only nodes carrying that label and that integer value are returned

#### Scenario: Type-sensitive lookup

- **WHEN** a node stores the string "36" and the caller looks up integer 36
- **THEN** the node is not returned

#### Scenario: List order matters

- **WHEN** a node stores the list [1, 2] and the caller looks up [2, 1]
- **THEN** the node is not returned

#### Scenario: Find relationships by label

- **WHEN** a caller looks up relationships carrying labels ALLIES_WITH and TRUSTS
- **THEN** only relationships carrying both labels are returned

#### Scenario: Find relationships by direction

- **WHEN** a caller looks up directed relationships
- **THEN** relationships stored as undirected are not returned

#### Scenario: Unlabeled relationship

- **WHEN** a caller looks up relationships without a label filter
- **THEN** labeled and unlabeled relationships are both eligible

### Requirement: Deletion rules

The system SHALL delete relationships directly. It SHALL refuse to delete a node that still has an incident relationship, whether that relationship is directed or undirected, unless detaching deletion is requested, in which case incident relationships are removed first.

#### Scenario: Connected node refused

- **WHEN** a caller deletes a node with an incident relationship without detaching
- **THEN** the system raises a connected-node error and changes nothing

#### Scenario: Detach and delete

- **WHEN** a caller deletes a connected node with detaching enabled
- **THEN** the node and all incident relationships are removed

#### Scenario: Undirected edge blocks deletion

- **WHEN** a caller deletes a node that is an endpoint of an undirected relationship without detaching
- **THEN** the system raises a connected-node error and changes nothing

#### Scenario: Detach removes undirected edges

- **WHEN** a caller deletes a node with detaching enabled and the node is an endpoint of an undirected relationship
- **THEN** that relationship is removed with the node

## REMOVED Requirements

### Requirement: Directed typed relationships

**Reason**: Replaced by the GQL element model, where an edge carries a label set and may be undirected.

**Migration**: Use `Graph.add_relationship(..., labels=..., directed=...)`. There is no in-place migration from a version 1 database before 1.0; create a new database with the current release.

### Requirement: Layout-only schema version

**Reason**: Version 2 is a hard layout break; an older layout is refused instead of upgraded.

**Migration**: Create a new database with the current release. A version 1 database or snapshot is not converted.

## ADDED Requirements

### Requirement: Labeled directed and undirected relationships

The system SHALL create relationships with zero or more non-empty string labels, two existing endpoint nodes, a directed flag, and properties. Duplicate labels SHALL be deduplicated. Empty labels and missing endpoints SHALL be rejected. A directed relationship SHALL preserve its start and end endpoints; an undirected relationship SHALL expose both endpoints without a source or destination meaning.

#### Scenario: Create a labeled relationship

- **WHEN** a caller connects two existing nodes with labels ALLIES_WITH and TRUSTS and a property
- **THEN** the relationship is returned with both labels, both endpoints, the directed flag, and the property

#### Scenario: Create an unlabeled relationship

- **WHEN** a caller connects two existing nodes without labels
- **THEN** the relationship is stored and read back with an empty label set

#### Scenario: Duplicate labels

- **WHEN** a caller supplies the same label twice for one relationship
- **THEN** the relationship carries that label once

#### Scenario: Empty label rejected

- **WHEN** a caller supplies an empty label
- **THEN** the system raises a validation error and creates no relationship

#### Scenario: Directed endpoints

- **WHEN** a caller creates a directed relationship
- **THEN** reads report the same start and end endpoints that were supplied

#### Scenario: Undirected endpoints

- **WHEN** a caller creates an undirected relationship
- **THEN** reads report both endpoints and no source or destination meaning

#### Scenario: Missing endpoint

- **WHEN** a caller creates a relationship referencing an absent node id
- **THEN** the system raises a not-found error and creates no relationship

#### Scenario: Self-loop

- **WHEN** a caller creates a directed or undirected relationship whose endpoints are the same node
- **THEN** the relationship is stored and can be read back

#### Scenario: Snapshot exposes labels and direction

- **WHEN** a caller reads a relationship after creating it with labels and a direction
- **THEN** the snapshot reports the sorted labels and the directed flag

### Requirement: Relationship label mutation

The system SHALL add and remove labels on an existing relationship. Adding a label the relationship already carries SHALL be a no-op; removing an absent label SHALL be a no-op. A missing relationship SHALL raise a not-found error. A snapshot SHALL report labels in sorted order.

#### Scenario: Add a label

- **WHEN** a caller adds a label to an existing relationship
- **THEN** later reads report the added label with the existing labels

#### Scenario: Remove a label

- **WHEN** a caller removes one label from a relationship carrying several labels
- **THEN** later reads report the remaining labels

#### Scenario: Repeated addition is a no-op

- **WHEN** a caller adds a label the relationship already carries
- **THEN** the relationship is unchanged and no error is raised

#### Scenario: Missing relationship

- **WHEN** a caller adds or removes a label on a relationship id that does not exist
- **THEN** the system raises a not-found error and changes nothing

#### Scenario: Undirected relationship labels

- **WHEN** a caller adds a label to an undirected relationship
- **THEN** the relationship keeps its undirected flag and reports the new label

### Requirement: Layout version compatibility

The recorded schema version SHALL change only when the stored layout becomes incompatible, and SHALL NOT change when additive objects are declared or removed. An uninitialized database SHALL be bootstrapped to the current version. A database that records a version other than zero or the current version SHALL be refused.

#### Scenario: Additive objects keep the version

- **WHEN** a caller declares or removes constraints or indexes
- **THEN** the recorded schema version is unchanged

#### Scenario: Newer layout refused

- **WHEN** a caller opens a database that records a newer layout than the library supports
- **THEN** the system raises an unsupported-runtime error before accepting any write

#### Scenario: Older layout refused

- **WHEN** a caller opens a database that records schema version 1
- **THEN** the system raises an unsupported-runtime error and leaves the file unchanged

#### Scenario: Read-only older layout refused

- **WHEN** a caller opens a version 1 database read-only
- **THEN** the system raises an unsupported-runtime error and makes no change

#### Scenario: Uninitialized database bootstrapped

- **WHEN** a caller opens a new or empty database
- **THEN** the current layout is created and the recorded version is the current version
