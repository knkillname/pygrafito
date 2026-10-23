# Spec Delta

## Purpose

Defines the persisted property-graph model and lifecycle: nodes, labels, directed typed relationships, strict property values, lookups, deletion rules, immutable snapshots, and transactional durability in an embedded SQLite-backed store.

## ADDED Requirements

### Requirement: Embedded graph lifecycle

The system SHALL provide a graph handle that opens or creates a database at a filesystem path or in memory, and SHALL persist graph content across close and reopen.

#### Scenario: Reopen a file database

- **WHEN** a caller creates a file-backed graph, adds a node, closes the graph, and opens the same path again
- **THEN** the node is present with the same id, labels, and properties

#### Scenario: In-memory graph

- **WHEN** a caller opens an in-memory graph
- **THEN** the graph is usable without creating a filesystem database file

### Requirement: Single-writer concurrency

The system SHALL use one database connection per graph handle and SHALL NOT support concurrent use from multiple threads.

#### Scenario: Cross-thread use

- **WHEN** a graph handle created in one thread is used from another thread
- **THEN** the system raises an error instead of sharing the connection silently

### Requirement: Strict property values

The system SHALL accept property values that are booleans, signed 64-bit integers, finite floats, strings, or homogeneous lists of those scalar values. It SHALL reject maps, nested lists, non-finite floats, out-of-range integers, and stored null.

#### Scenario: Accepted scalars round-trip

- **WHEN** a caller stores a boolean, an in-range integer, a finite float, and a string
- **THEN** each read returns the same value and Python type

#### Scenario: Map rejected

- **WHEN** a caller attempts to store a mapping as a property value
- **THEN** the system raises a validation error and stores nothing

#### Scenario: Mixed list rejected

- **WHEN** a caller attempts to store a list mixing integers and strings
- **THEN** the system raises a validation error

#### Scenario: Out-of-range integer rejected

- **WHEN** a caller attempts to store an integer outside the signed 64-bit range
- **THEN** the system raises a validation error

#### Scenario: Non-finite float rejected

- **WHEN** a caller attempts to store NaN or an infinity
- **THEN** the system raises a validation error

#### Scenario: Null removes a property

- **WHEN** a caller assigns null to an existing property
- **THEN** the property is removed and later reads do not report it

### Requirement: Type distinction

The system SHALL preserve the distinction between booleans, integers, and floats in stored values and in property filters.

#### Scenario: Boolean does not match integer

- **WHEN** a node stores a boolean property and a caller filters on integer 1
- **THEN** the node does not match

#### Scenario: Integer does not match float

- **WHEN** a node stores integer 1 and a caller filters on float 1.0
- **THEN** the node does not match

### Requirement: Nodes, labels, and properties

The system SHALL create nodes with a unique integer id, zero or more non-empty string labels, and unique non-empty string property keys. It SHALL support reading by id, adding and removing labels, and setting and removing properties.

#### Scenario: Node with multiple labels

- **WHEN** a caller creates a node with labels Person and Employee
- **THEN** the returned snapshot contains both labels

#### Scenario: Update labels and properties

- **WHEN** a caller adds one label, removes another, and changes a property
- **THEN** later reads observe exactly the updated labels and properties

#### Scenario: Arbitrary property key

- **WHEN** a caller stores a property whose key contains a dot or a space
- **THEN** the property is stored and read back under that exact key

#### Scenario: Missing node

- **WHEN** a caller requests a node id that does not exist
- **THEN** the system raises a not-found error

### Requirement: Immutable read snapshots

The system SHALL return immutable snapshots for node and relationship reads. A later write SHALL NOT change a snapshot that was already returned.

#### Scenario: Snapshot stays unchanged

- **WHEN** a caller reads a node, changes a property through the graph, and inspects the earlier snapshot
- **THEN** the earlier snapshot still reports the original property value

### Requirement: Directed typed relationships

The system SHALL create directed relationships with a non-empty string type, a start node, an end node, and properties. It SHALL reject relationships whose endpoints do not exist.

#### Scenario: Create a relationship

- **WHEN** a caller connects two existing nodes with type KNOWS and a property
- **THEN** the relationship is returned with the same type, endpoints, and properties

#### Scenario: Missing endpoint

- **WHEN** a caller creates a relationship referencing an absent node id
- **THEN** the system raises a not-found error and creates no relationship

#### Scenario: Self-loop

- **WHEN** a caller creates a relationship whose start and end are the same node
- **THEN** the relationship is stored and can be read back

### Requirement: Element identity

The system SHALL assign unique integer ids to live nodes and relationships. An id MAY be reused after the element is deleted.

#### Scenario: Distinct live ids

- **WHEN** a caller creates several nodes and relationships
- **THEN** every live element has a distinct id

### Requirement: Lookup by label and property

The system SHALL find nodes carrying all specified labels and matching exact property values, and SHALL find relationships by type and exact property values. Property matching SHALL be type-sensitive and SHALL respect list order.

#### Scenario: Find nodes by label and property

- **WHEN** a caller looks up nodes labeled Person with an integer age of 36
- **THEN** only nodes carrying that label and that integer value are returned

#### Scenario: Type-sensitive lookup

- **WHEN** a node stores the string "36" and the caller looks up integer 36
- **THEN** the node is not returned

#### Scenario: List order matters

- **WHEN** a node stores the list [1, 2] and the caller looks up [2, 1]
- **THEN** the node is not returned

### Requirement: Deletion rules

The system SHALL delete relationships directly. It SHALL refuse to delete a node that still has relationships unless detaching deletion is requested, in which case incident relationships are removed first.

#### Scenario: Connected node refused

- **WHEN** a caller deletes a node with an incident relationship without detaching
- **THEN** the system raises a connected-node error and changes nothing

#### Scenario: Detach and delete

- **WHEN** a caller deletes a connected node with detaching enabled
- **THEN** the node and all incident relationships are removed

### Requirement: Transactions and durability

The system SHALL group writes in ACID transactions. An explicit transaction SHALL commit all writes on success and roll back all writes on failure. Each convenience write SHALL be atomic on its own.

#### Scenario: Commit

- **WHEN** a caller performs several writes inside a transaction that completes successfully
- **THEN** all writes are visible afterward

#### Scenario: Rollback

- **WHEN** writes are performed inside a transaction and an error occurs before completion
- **THEN** none of those writes are visible

#### Scenario: Atomic convenience write

- **WHEN** a single convenience write fails validation
- **THEN** no partial change is persisted

### Requirement: Database compatibility

The system SHALL verify at open time that the SQLite runtime provides the JSON functions required for property storage, and SHALL refuse to operate otherwise.

#### Scenario: Unsupported runtime

- **WHEN** a graph is opened on a SQLite runtime without the required JSON support
- **THEN** the system raises an unsupported-runtime error before accepting writes
