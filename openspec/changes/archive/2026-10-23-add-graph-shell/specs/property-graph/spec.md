# Spec Delta

## ADDED Requirements

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
