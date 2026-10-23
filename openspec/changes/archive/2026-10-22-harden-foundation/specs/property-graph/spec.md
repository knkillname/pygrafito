# Spec Delta

## ADDED Requirements

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
