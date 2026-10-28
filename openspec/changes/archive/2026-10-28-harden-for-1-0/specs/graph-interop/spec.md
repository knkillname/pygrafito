# Spec Delta

## ADDED Requirements

### Requirement: Frozen v2 snapshot and view version

Snapshot format version 2 SHALL be frozen for 1.0, and the published view version SHALL remain the
frozen 1.0 version. A version 2 snapshot written by 0.9 or 1.0 SHALL restore. A snapshot with any
other version SHALL be refused with a message naming version 2. Golden fixtures SHALL prove
version 2 compatibility.

#### Scenario: A version 2 snapshot restores

- **WHEN** a caller restores a version 2 snapshot written by 0.9
- **THEN** the graph content is complete and matches the source

#### Scenario: A future snapshot is refused

- **WHEN** a caller restores a snapshot whose header declares a version newer than 2
- **THEN** the error names version 2 as supported and restores nothing

#### Scenario: Golden fixture compatibility

- **WHEN** the compatibility test restores the checked-in golden snapshot
- **THEN** the restored graph matches the expected content

#### Scenario: Canonical export is stable

- **WHEN** the restored graph is exported again
- **THEN** the bytes match the golden snapshot

#### Scenario: View version is frozen

- **WHEN** a 1.0 database is opened
- **THEN** the published view version is the frozen 1.0 version

### Requirement: Crash-safe restore

A process termination during restore SHALL leave the target at its previous committed state and
SHALL NOT leave a partial graph. Reopening SHALL pass an integrity check.

#### Scenario: Empty target after termination

- **WHEN** a process is terminated during a restore into an empty target
- **THEN** reopening shows an empty graph

#### Scenario: Replaced target after termination

- **WHEN** a process is terminated during a restore that replaces an existing graph
- **THEN** reopening shows the original graph unchanged

#### Scenario: Integrity after termination

- **WHEN** a database is reopened after a terminated restore
- **THEN** the integrity check reports no problems

#### Scenario: No partial graph

- **WHEN** a restore is terminated after some records were read
- **THEN** no partially restored node or relationship is visible
