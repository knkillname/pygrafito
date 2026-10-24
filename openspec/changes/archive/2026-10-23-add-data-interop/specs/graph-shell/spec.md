# Spec Delta

## ADDED Requirements

### Requirement: Export command

`.export PATH [--format jsonl] [--overwrite]` SHALL write a JSONL snapshot of the open graph to
PATH. It SHALL accept `jsonl` as the only format, SHALL refuse an existing path unless
`--overwrite` is given, SHALL refuse the open database path and its sidecars, SHALL work in a
read-only session, and SHALL refuse while an explicit transaction is active.

#### Scenario: Export a graph

- **WHEN** a caller submits `.export grid.jsonl`
- **THEN** a snapshot is written and a summary reports the node and relationship counts

#### Scenario: Explicit format

- **WHEN** a caller submits `.export grid.txt --format jsonl`
- **THEN** the file is written as JSONL

#### Scenario: Existing destination

- **WHEN** the path exists and `--overwrite` is absent
- **THEN** the command reports an error, leaves the file unchanged, and keeps the session usable

#### Scenario: Overwrite

- **WHEN** `--overwrite` is given and the path exists
- **THEN** the file is replaced

#### Scenario: Live database path

- **WHEN** the path is the open database or a sidecar
- **THEN** the command is refused even when `--overwrite` is given

#### Scenario: Read-only session

- **WHEN** a caller exports in a read-only session
- **THEN** the snapshot is written

#### Scenario: Active transaction

- **WHEN** a caller exports during an explicit transaction
- **THEN** the command is refused and the transaction remains active

#### Scenario: Quoted path

- **WHEN** a caller quotes a path that contains spaces
- **THEN** the path is parsed as one argument

### Requirement: Restore command

`.restore PATH [--replace]` SHALL restore a JSONL snapshot into the open graph. It SHALL refuse a
read-only session, an active transaction, and a non-empty graph unless `--replace` is given. With
`--replace`, it SHALL clear and restore in one transaction, so a failure leaves the original graph
intact.

#### Scenario: Restore into empty

- **WHEN** a caller restores a snapshot into an empty graph
- **THEN** the elements are created and a summary reports the counts

#### Scenario: Non-empty without replace

- **WHEN** the graph has elements and `--replace` is absent
- **THEN** the command reports an error and changes nothing

#### Scenario: Replace

- **WHEN** the graph has elements and `--replace` is given
- **THEN** the old graph is replaced

#### Scenario: Replace failure

- **WHEN** a record fails during `--replace`
- **THEN** the original graph remains

#### Scenario: Read-only session

- **WHEN** a caller restores in a read-only session
- **THEN** the command reports an error and changes nothing

#### Scenario: Active transaction

- **WHEN** a caller restores during an explicit transaction
- **THEN** the command is refused and the transaction remains active

#### Scenario: Malformed snapshot

- **WHEN** the snapshot header is invalid
- **THEN** the error is reported and the prompt returns

#### Scenario: Quoted path

- **WHEN** a caller quotes a path that contains spaces
- **THEN** the path is parsed as one argument

### Requirement: Interop command usage and output

`.export` and `.restore` SHALL report their node and relationship counts on the command output
stream, SHALL report errors on the diagnostic stream without ending the session, and SHALL use the
existing usage-error exit code for a missing path or an unsupported option.

#### Scenario: Summary wording

- **WHEN** an export or restore succeeds
- **THEN** the summary names the counts and the path

#### Scenario: Missing path

- **WHEN** a caller omits the path
- **THEN** the command reports its usage and stores nothing

#### Scenario: Unsupported option

- **WHEN** a caller supplies an unsupported option or format
- **THEN** the command reports a usage error and stores nothing

#### Scenario: Error isolation

- **WHEN** an interop command fails
- **THEN** the session remains usable and later commands run normally
