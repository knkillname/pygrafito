# graph-import Specification

## Purpose

Imports row-shaped data from CSV, JSONL, or in-memory mappings into a graph by binding each batch to a caller-supplied write statement, with explicit transaction boundaries and row-level failure reporting.

## Requirements

### Requirement: Import entry points

`Graph.import_rows` SHALL import an iterable of row mappings, and `Graph.import_file` SHALL import a CSV or JSONL file. Both SHALL take a write statement, bind each batch of rows to the `$rows` parameter, and return an import summary. A statement with no write clause or no reference to `$rows` SHALL be rejected before any row is processed.

#### Scenario: Import in-memory rows

- **WHEN** a caller imports two mappings with a `MERGE` statement that references `$rows`
- **THEN** the matching elements are created or matched and the summary reports two rows

#### Scenario: Import a JSONL file

- **WHEN** a caller imports a JSONL file whose lines are row objects
- **THEN** every row is processed by the statement in file order

#### Scenario: Statement is not a write

- **WHEN** the import statement contains only `MATCH` and `RETURN`
- **THEN** the system raises a validation error before processing any row

#### Scenario: Statement does not reference rows

- **WHEN** the import statement never references `$rows`
- **THEN** the system raises a validation error before reading the file

#### Scenario: Read-only graph

- **WHEN** a caller imports into a read-only graph handle
- **THEN** the system raises `ReadOnlyError` before reading any row

#### Scenario: Closed graph

- **WHEN** a caller imports through a closed graph handle
- **THEN** the system raises `GraphClosedError`

### Requirement: Row shape and value mapping

Each row SHALL be a mapping with string keys. JSONL and in-memory input SHALL preserve scalar, list, and mapping values. CSV SHALL produce string values. The statement SHALL map row fields to properties, and a value the property model rejects SHALL fail the batch with a query error.

#### Scenario: Typed JSONL values

- **WHEN** a JSONL row carries an integer, a boolean, and a list
- **THEN** the created element stores each value with its JSON type

#### Scenario: CSV string conversion

- **WHEN** a CSV field contains `36` and the statement uses `toInteger(row.cycles)`
- **THEN** the stored property is the integer 36

#### Scenario: Field access

- **WHEN** the statement references `row.designation`
- **THEN** the value is read from the current row mapping

#### Scenario: Rejected property value

- **WHEN** a row supplies a nested list or a non-finite number as a property value
- **THEN** the batch fails with a query error and no partial batch commits

### Requirement: CSV format

CSV input SHALL require a header row and SHALL treat each following non-blank record as one row. It SHALL reject duplicate header names and records whose field count differs from the header. Quoted fields, escaped quotes, and embedded newlines SHALL follow the standard CSV rules.

#### Scenario: Header names become fields

- **WHEN** a CSV file starts with `designation,cycles`
- **THEN** each row exposes `row.designation` and `row.cycles`

#### Scenario: Duplicate header

- **WHEN** two header columns share a name
- **THEN** the system raises a validation error before processing rows

#### Scenario: Field count mismatch

- **WHEN** a record has fewer or more fields than the header
- **THEN** the system raises a validation error naming the row

#### Scenario: Quoted and embedded newline

- **WHEN** a quoted field contains a comma, an escaped quote, or a newline
- **THEN** the field is read as one value

#### Scenario: Header only

- **WHEN** a CSV file contains only a header row
- **THEN** the import reports zero rows and changes nothing

### Requirement: JSONL format

JSONL input SHALL decode one JSON object per non-blank line and SHALL skip blank lines. A line that is not a JSON object SHALL be rejected with its line number. NaN and infinity SHALL be rejected.

#### Scenario: One object per line

- **WHEN** a JSONL file contains two object lines
- **THEN** the import processes two rows in order

#### Scenario: Blank lines skipped

- **WHEN** the file contains blank lines between objects
- **THEN** the blank lines contribute no rows

#### Scenario: Non-object line

- **WHEN** a line decodes to an array or a scalar
- **THEN** the system raises a validation error naming the line

#### Scenario: Invalid JSON

- **WHEN** a line is not valid JSON
- **THEN** the system raises a validation error naming the line

#### Scenario: Non-finite number

- **WHEN** a line contains `NaN` or `Infinity`
- **THEN** the system raises a validation error

### Requirement: Format selection

`import_file` SHALL select the format from an explicit `format` argument when supplied, otherwise from the file suffix `.csv`, `.jsonl`, or `.ndjson`. An unknown suffix or format SHALL raise a validation error before reading the file.

#### Scenario: Explicit format

- **WHEN** a caller imports a `.txt` file with `format="csv"`
- **THEN** the file is parsed as CSV

#### Scenario: NDJSON suffix

- **WHEN** a caller imports a file ending in `.ndjson` without an explicit format
- **THEN** the file is parsed as JSONL

#### Scenario: Unknown suffix

- **WHEN** a caller imports a `.data` file without an explicit format
- **THEN** the system raises a validation error before reading the file

### Requirement: Batching and atomicity

Import SHALL process rows in batches whose size defaults to 1000 and SHALL require a positive batch size. Each batch SHALL commit in its own transaction by default. With `atomic` enabled, the entire import SHALL commit in one transaction or roll back entirely. A failed batch SHALL roll back only that batch unless `atomic` is enabled.

#### Scenario: Default batch commit

- **WHEN** an import of 2500 rows uses the default batch size
- **THEN** three batches run and each commits independently

#### Scenario: Atomic failure

- **WHEN** a row fails in the second batch of an atomic import
- **THEN** the first batch is rolled back and no row remains

#### Scenario: Non-atomic failure

- **WHEN** a row fails in the second batch of a non-atomic import
- **THEN** the first batch remains committed and the import stops

#### Scenario: Invalid batch size

- **WHEN** a caller supplies a batch size of zero or a negative number
- **THEN** the system raises a validation error before reading rows

#### Scenario: Empty input

- **WHEN** an import receives no rows
- **THEN** it executes no statement and returns a summary with zero rows and zero batches

### Requirement: Import summary

The import summary SHALL report the number of rows read, the number of batches executed, and the aggregate mutation counts of created and deleted elements and property and label changes.

#### Scenario: Counts after a merge import

- **WHEN** an import creates three nodes and one relationship
- **THEN** the summary reports three created nodes, one created relationship, and the rows read

#### Scenario: Duplicate keys

- **WHEN** two input rows merge the same key
- **THEN** the summary reports one created node and two rows read

#### Scenario: Empty summary

- **WHEN** no row is read
- **THEN** every summary count is zero

### Requirement: Row-level failure reporting

An import failure SHALL report the source, the one-based row number, the batch number, and the original query error, and SHALL stop the import. The failing batch SHALL not commit.

#### Scenario: File row reported

- **WHEN** the third row of a file fails during execution
- **THEN** the error reports the file path, row three, and the batch number

#### Scenario: In-memory row reported

- **WHEN** the second in-memory mapping fails during execution
- **THEN** the error reports the row index and identifies the source as in-memory input

#### Scenario: Original error preserved

- **WHEN** a batch fails with a query error
- **THEN** the raised error keeps its type and carries the import context as a note
