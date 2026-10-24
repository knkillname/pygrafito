# property-graph Specification

## Purpose

Defines the persisted property-graph model and lifecycle: nodes, labels, directed typed relationships, strict property values, lookups, deletion rules, immutable snapshots, and transactional durability in an embedded SQLite-backed store.

## Requirements

### Requirement: Embedded graph lifecycle

The system SHALL provide a graph handle that opens or creates a database at a filesystem path or in memory, and SHALL persist graph content across close and reopen.

#### Scenario: Reopen a file database

- **WHEN** a caller creates a file-backed graph, adds a node, closes the graph, and opens the same path again
- **THEN** the node is present with the same id, labels, and properties

#### Scenario: In-memory graph

- **WHEN** a caller opens an in-memory graph
- **THEN** the graph is usable without creating a filesystem database file

### Requirement: Closed graph handle operations

The system SHALL reject reads, writes, and traversal starts on a closed graph handle with a
`GraphClosedError`.

#### Scenario: Read after close

- **WHEN** a caller closes a graph and then reads a node or relationship
- **THEN** the system raises `GraphClosedError`

#### Scenario: Write after close

- **WHEN** a caller closes a graph and then attempts a convenience write
- **THEN** the system raises `GraphClosedError` before executing SQL

#### Scenario: Traversal after close

- **WHEN** a caller closes a graph and then starts `traverse`, `shortest_path`, or `paths`
- **THEN** the system raises `GraphClosedError`

### Requirement: Single-writer concurrency

The system SHALL use one database connection per graph handle, and a handle SHALL belong to the thread that opened it. Several handles MAY open the same file and SHALL observe each other's committed writes. At most one writer SHALL run at a time; a writer SHALL wait up to the configured busy timeout and SHALL raise a lock-timeout error when that wait is exhausted. Using a handle from another thread SHALL raise a handle-affinity error rather than a driver error.

#### Scenario: Cross-thread use

- **WHEN** a graph handle created in one thread is used from another thread
- **THEN** the system raises a handle-affinity error instead of sharing the connection silently

#### Scenario: Several handles in one process

- **WHEN** two handles open the same file in one process
- **THEN** a write committed by one handle is visible to a later read on the other

#### Scenario: Several processes

- **WHEN** two processes hold handles on the same file
- **THEN** a write committed in one process is visible to a later read in the other

#### Scenario: Writers take turns

- **WHEN** one handle holds a write transaction and another begins a write
- **THEN** the second waits and proceeds after the first commits

#### Scenario: Lock wait exhausted

- **WHEN** another writer holds the lock for longer than the busy timeout
- **THEN** the waiting write raises a lock-timeout error and changes nothing

### Requirement: Read snapshot

Each public read call SHALL observe one committed state, even when another handle commits while
the call runs. A read that runs inside an explicit transaction SHALL observe that transaction's
own writes.

#### Scenario: Multi-statement read

- **WHEN** a caller reads a node while another handle commits a change to it
- **THEN** the returned labels and properties come from the same committed state

#### Scenario: Traversal during a commit

- **WHEN** a traversal runs while another handle commits a change inside the traversed region
- **THEN** every reached node and relationship comes from one committed state

#### Scenario: Read inside a transaction

- **WHEN** a caller reads inside an explicit transaction that already wrote
- **THEN** the read observes the transaction's own uncommitted writes

### Requirement: Effective journal mode

The system SHALL prefer write-ahead logging for file-backed graphs and SHALL report the journal
mode in effect. When the platform cannot provide write-ahead logging, the graph SHALL still open
and remain consistent, and concurrent reading during a commit SHALL NOT be guaranteed.

#### Scenario: File reports its mode

- **WHEN** a caller opens a file-backed graph on a platform that supports write-ahead logging
- **THEN** the reported journal mode is the write-ahead mode

#### Scenario: Platform without write-ahead logging

- **WHEN** a caller opens a file-backed graph where the write-ahead mode cannot be enabled
- **THEN** the graph opens, reports the mode it did obtain, and reads and writes continue to work

#### Scenario: In-memory graph

- **WHEN** a caller opens an in-memory graph
- **THEN** the reported journal mode is the in-memory mode and no file is created

### Requirement: Layout-only schema version

The recorded schema version SHALL change only when the stored layout becomes incompatible, and
SHALL NOT change when additive objects are declared or removed. A database that records a newer
layout SHALL be refused.

#### Scenario: Additive objects keep the version

- **WHEN** a caller declares or removes constraints or indexes
- **THEN** the recorded schema version is unchanged

#### Scenario: Newer layout refused

- **WHEN** a caller opens a database that records a newer layout than the library supports
- **THEN** the system raises an unsupported-runtime error before accepting any write

#### Scenario: Older layout upgraded

- **WHEN** a caller opens a write-capable handle on a database with an older layout
- **THEN** the layout is upgraded on open and the recorded version becomes the current one

### Requirement: Foreign database refusal

The system SHALL refuse to open an existing SQLite database as a graph when that database records
no graph layout and contains at least one unrelated table, and SHALL leave it unchanged. Views
SHALL NOT count as unrelated tables.

#### Scenario: Unrelated database refused

- **WHEN** a caller opens a write-capable handle on a SQLite database that holds only unrelated
  tables
- **THEN** the system raises an unsupported-runtime error and the database keeps its original
  tables and version

#### Scenario: Fresh file accepted

- **WHEN** a caller opens a path that does not exist, or an empty database file
- **THEN** the graph schema is created

#### Scenario: Added table accepted

- **WHEN** a caller opens a graph database to which an external tool added a table
- **THEN** the graph opens and the added table is left untouched

#### Scenario: Views do not make a file foreign

- **WHEN** a caller opens a graph database that contains externally visible views
- **THEN** the graph opens normally

### Requirement: Portable database file

Closing the last handle of a file-backed graph SHALL leave a single self-contained database file.
Copying a database file while a handle holds it open SHALL be outside the contract.

#### Scenario: Clean close leaves one file

- **WHEN** the last handle of a file-backed graph is closed
- **THEN** the database is one file with no log or shared-memory sidecar

#### Scenario: Copy while open

- **WHEN** a caller needs a copy while a handle is open
- **THEN** the backup operation produces a consistent database file

#### Scenario: Read-only media

- **WHEN** a cleanly closed database is opened read-only from read-only media
- **THEN** reads succeed

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

### Requirement: Active transaction write guard

The system SHALL reject a convenience write while an explicit transaction is active, raising a
`TransactionError` before executing SQL. The active transaction SHALL remain usable when the caller
handles that error.

#### Scenario: Convenience write rejected

- **WHEN** a caller starts an explicit transaction and invokes a convenience write on the graph
- **THEN** the system raises `TransactionError` and executes no SQL for that convenience write

#### Scenario: Active transaction survives

- **WHEN** a caller handles the `TransactionError` inside an explicit transaction and then writes
  through the transaction
- **THEN** the transaction remains active and commits its writes normally

### Requirement: Database compatibility

The system SHALL verify at open time that the SQLite runtime provides the JSON functions required for property storage, and SHALL refuse to operate otherwise.

#### Scenario: Unsupported runtime

- **WHEN** a graph is opened on a SQLite runtime without the required JSON support
- **THEN** the system raises an unsupported-runtime error before accepting writes

### Requirement: Read-only graph handles

The system SHALL open an existing file-backed graph in read-only mode. A read-only handle SHALL
allow reads, queries, traversal, and maintenance reads, and SHALL reject every write with
`ReadOnlyError` before executing SQL. A read-only open SHALL NOT create a missing file and SHALL
reject an in-memory location.

#### Scenario: Read from a read-only handle

- **WHEN** a caller reads nodes, relationships, and query results through a read-only handle
- **THEN** every read returns the same data as a read-write handle

#### Scenario: Convenience write rejected

- **WHEN** a caller attempts a convenience write such as adding a node on a read-only handle
- **THEN** the system raises `ReadOnlyError` and stores nothing

#### Scenario: Query write rejected

- **WHEN** a caller executes a statement with a write clause on a read-only handle
- **THEN** the system raises `ReadOnlyError` and stores nothing

#### Scenario: Transaction rejected

- **WHEN** a caller requests an explicit transaction on a read-only handle
- **THEN** the system raises `ReadOnlyError`

#### Scenario: Missing file is not created

- **WHEN** a caller opens a path that does not exist in read-only mode
- **THEN** the system raises a not-found error and no file is created

#### Scenario: In-memory read-only rejected

- **WHEN** a caller requests a read-only in-memory graph
- **THEN** the system raises a validation error

### Requirement: Manual transaction control

An explicit transaction SHALL also be controllable through `begin`, `commit`, and `rollback`
operations. `begin` SHALL start one `BEGIN IMMEDIATE` transaction, `commit` and `rollback` SHALL
finish it, and the context-manager form SHALL remain equivalent.

#### Scenario: Manual commit

- **WHEN** a caller begins a transaction, writes, and commits
- **THEN** the writes are persisted

#### Scenario: Manual rollback

- **WHEN** a caller begins a transaction, writes, and rolls back
- **THEN** the writes are discarded

#### Scenario: Begin twice

- **WHEN** a caller begins an already active transaction
- **THEN** the system raises `TransactionError` and the active transaction remains usable

#### Scenario: Finish without begin

- **WHEN** a caller commits or rolls back a transaction that was never begun
- **THEN** the system raises `TransactionError`

#### Scenario: Finish twice

- **WHEN** a caller commits or rolls back a transaction that has already finished
- **THEN** the system raises `TransactionError`

#### Scenario: Context manager remains equivalent

- **WHEN** a caller writes inside a transaction context block that completes successfully
- **THEN** the writes are committed as before, and an exception still rolls them back

### Requirement: Database backup

The system SHALL write a consistent copy of the open database to a destination path while the
database is live. It SHALL refuse a destination that already exists and SHALL refuse to run while
an explicit transaction is active. A read-only handle SHALL support backup.

#### Scenario: Backup copies content

- **WHEN** a caller backs up a live database to a new path
- **THEN** the copy opens as a database with the same nodes, labels, relationships, and properties

#### Scenario: Existing destination refused

- **WHEN** the destination path already exists
- **THEN** the system raises a validation error and leaves the existing file unchanged

#### Scenario: Active transaction refused

- **WHEN** a caller requests a backup while an explicit transaction is active
- **THEN** the system raises `TransactionError` and the transaction remains usable

#### Scenario: Read-only source

- **WHEN** a caller backs up a read-only graph handle
- **THEN** the copy is written

### Requirement: Integrity check

The system SHALL report structural integrity problems of the open database, including storage
integrity failures and foreign-key violations, and SHALL return an empty result when the store is
healthy.

#### Scenario: Healthy store

- **WHEN** a caller checks the integrity of a healthy database
- **THEN** the result is empty

#### Scenario: Foreign-key violation reported

- **WHEN** the database contains a foreign-key violation
- **THEN** the reported problems identify the violation

#### Scenario: Read-only handle

- **WHEN** a caller checks the integrity of a read-only handle
- **THEN** the report is returned, or empty when the store is healthy
