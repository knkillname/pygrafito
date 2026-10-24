# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
