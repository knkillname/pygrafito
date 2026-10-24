# Spec Delta

## ADDED Requirements

### Requirement: Import command

`.import PATH --statement TEXT` SHALL read a CSV or JSONL file and execute the statement once per batch with `$rows` bound. It SHALL accept `--format csv|jsonl`, `--batch N`, and `--atomic`, SHALL print an import summary, and SHALL refuse to run while an explicit transaction is active. The statement argument SHALL support shell-style quoting.

#### Scenario: Import a JSONL file

- **WHEN** a caller submits `.import grid.jsonl --statement "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})"`
- **THEN** every row is merged and a summary line is printed

#### Scenario: Explicit CSV format

- **WHEN** a caller submits `.import data.txt --format csv --statement "..."`
- **THEN** the file is parsed as CSV instead of by its suffix

#### Scenario: Summary output

- **WHEN** an import creates two nodes and reads three rows in one batch
- **THEN** the summary reports the row count, batch count, and created elements

#### Scenario: Refused during a transaction

- **WHEN** a caller submits `.import` while an explicit transaction is active
- **THEN** the command is refused and the transaction and file are unchanged

#### Scenario: Read-only session

- **WHEN** a caller submits `.import` in a read-only session
- **THEN** the session reports an error, stores nothing, and remains usable

#### Scenario: Failure leaves the session usable

- **WHEN** an import fails on a malformed row
- **THEN** the error is reported, earlier batches keep their commits unless `--atomic` was used, and the prompt returns

#### Scenario: Missing statement

- **WHEN** a caller submits `.import PATH` without `--statement`
- **THEN** the command reports its usage and stores nothing

#### Scenario: Invalid batch size

- **WHEN** a caller submits `--batch 0` or a negative value
- **THEN** the command reports a validation error and stores nothing
