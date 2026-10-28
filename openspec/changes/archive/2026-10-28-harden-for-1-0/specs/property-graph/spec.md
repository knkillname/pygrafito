# Spec Delta

## MODIFIED Requirements

### Requirement: Transactions and durability

The system SHALL group writes in ACID transactions. A committed transaction SHALL survive process
termination, and an uncommitted transaction SHALL leave no partial state. An explicit transaction
SHALL commit all writes on success and roll back all writes on failure. Each convenience write
SHALL be atomic on its own.

#### Scenario: Commit

- **WHEN** a caller performs several writes inside a transaction that completes successfully
- **THEN** all writes are visible afterward

#### Scenario: Rollback

- **WHEN** writes are performed inside a transaction and an error occurs before completion
- **THEN** none of those writes are visible

#### Scenario: Atomic convenience write

- **WHEN** a single convenience write fails validation
- **THEN** no partial change is persisted

#### Scenario: Committed write survives termination

- **WHEN** a process commits a write transaction and is then terminated
- **THEN** reopening the database shows the committed write

#### Scenario: Uncommitted write is absent

- **WHEN** a process is terminated in the middle of a write transaction
- **THEN** reopening the database shows none of that transaction's writes

#### Scenario: Write-ahead log recovery

- **WHEN** a file-backed database is reopened after an abrupt process termination
- **THEN** committed data is present and the integrity check reports no problems

#### Scenario: Convenience write survives termination

- **WHEN** a convenience write commits and the process is then terminated
- **THEN** reopening the database shows the write

## ADDED Requirements

### Requirement: Frozen v2 layout and migration policy

Schema layout version 2 SHALL be frozen for 1.0. A version 2 database written by 0.9 or 1.0 SHALL
open. A database from any other version SHALL be refused with a message naming the supported
version and an export path. The library SHALL NOT migrate a database automatically.

#### Scenario: A version 2 database opens

- **WHEN** a caller opens a database written by 0.9
- **THEN** it opens read-write without a migration step

#### Scenario: A future layout is refused

- **WHEN** a caller opens a database that records a version newer than 2
- **THEN** the error names version 2 as supported and leaves the file unchanged

#### Scenario: A read-only future layout is refused

- **WHEN** a caller opens a future-version database read-only
- **THEN** the error names version 2 as supported and makes no change

#### Scenario: No automatic migration

- **WHEN** a caller opens a database from another version
- **THEN** the library refuses it and points to exporting with the matching release

### Requirement: Crash-safe backup

A process termination during backup SHALL leave the source database unchanged and SHALL NOT leave a
partial destination file. A read-only source SHALL have the same guarantee.

#### Scenario: Source unchanged

- **WHEN** a process is terminated during a backup
- **THEN** the source database opens and passes the integrity check

#### Scenario: No partial destination

- **WHEN** a process is terminated during a backup
- **THEN** the destination is absent or is a complete valid copy

#### Scenario: Read-only source

- **WHEN** a process is terminated during a backup from a read-only handle
- **THEN** the source database is unchanged
