# graph-shell Specification

## Purpose

Defines the command-line shell for a graph database: invocation and input modes, statement and
dot-command handling, result rendering and output streams, exit codes, read-only sessions,
explicit transactions, graph introspection, and maintenance commands.

## Requirements

### Requirement: Shell entry points and startup

The system SHALL provide a `pygrafito` console command and an equivalent `python -m pygrafito`
entry point. With no database argument, the session SHALL use a transient in-memory graph. A
database argument SHALL select a file, creating it when missing unless the session is read-only.

#### Scenario: Equivalent entry points

- **WHEN** a caller runs the console command and the module entry point with the same database path and input
- **THEN** both sessions produce the same output and exit code

#### Scenario: Transient in-memory graph

- **WHEN** a caller starts the shell with no database argument
- **THEN** the session uses an in-memory graph and creates no file

#### Scenario: Missing file is created

- **WHEN** a caller starts a session on a path that does not exist
- **THEN** the database file is created and the session is usable

#### Scenario: Read-only session on a missing file

- **WHEN** a caller starts a session with read-only access to a path that does not exist
- **THEN** the session reports an error, exits with code 1, and creates no file

### Requirement: Interactive and non-interactive modes

The session SHALL be interactive only when no command or script is supplied and standard input is
a terminal. An interactive session SHALL print a startup banner and prompts to standard error. A
non-interactive session SHALL print neither.

#### Scenario: Interactive banner and prompts

- **WHEN** a caller starts a session from a terminal
- **THEN** the banner and each prompt are written to standard error, not standard output

#### Scenario: Piped input

- **WHEN** standard input is a pipe or a file
- **THEN** no banner and no prompts are printed

#### Scenario: Quiet startup

- **WHEN** a caller supplies the quiet option
- **THEN** the banner and interactive footers are suppressed and results are unchanged

### Requirement: Statement input and terminators

The session SHALL read statements terminated by a semicolon, SHALL allow a statement to span
lines, and SHALL recognize a terminator only outside string literals, quoted identifiers, line
comments, and block comments. Several statements in one input SHALL execute in order. Input that
contains only whitespace or comments SHALL execute nothing.

#### Scenario: Multi-line statement

- **WHEN** a caller submits a statement split across several lines
- **THEN** the session executes it as one statement after the terminating semicolon

#### Scenario: Semicolon inside a string

- **WHEN** a statement contains a semicolon inside a string literal or a quoted identifier
- **THEN** that semicolon does not terminate the statement

#### Scenario: Semicolon inside a comment

- **WHEN** a statement contains a semicolon inside a line comment or a block comment
- **THEN** that semicolon does not terminate the statement

#### Scenario: Several statements in one input

- **WHEN** a caller submits several terminated statements in one input
- **THEN** all of them execute in source order

#### Scenario: Blank and comment-only input

- **WHEN** a caller submits only whitespace or a comment
- **THEN** nothing executes and no error is reported

#### Scenario: Continuation prompt

- **WHEN** an interactive statement is not yet terminated
- **THEN** the session shows a continuation prompt and executes the statement only after the terminator

#### Scenario: Final unterminated statement

- **WHEN** a script or an interactive session reaches the end of input with a non-empty unterminated statement
- **THEN** the session executes that statement as if it were terminated

### Requirement: Dot-command recognition

A line whose first non-whitespace character is `.` SHALL be a dot-command when no statement is
being accumulated. Dot-command names SHALL be case-sensitive. An unknown command SHALL report an
error and leave the session usable. Dot-commands SHALL NOT be recognized inside an accumulated
statement.

#### Scenario: Command at the prompt

- **WHEN** a caller submits a `.`-prefixed line while no statement is pending
- **THEN** the session executes it as a dot-command

#### Scenario: Unknown command

- **WHEN** a caller submits an unrecognized dot-command
- **THEN** the session reports an error on standard error and remains usable

#### Scenario: Dot line inside a statement

- **WHEN** a `.`-prefixed line appears while a statement is pending
- **THEN** the line is treated as statement text rather than as a command

### Requirement: Script execution

`-c TEXT` SHALL execute the given statements and exit, `-f PATH` SHALL execute a file and exit,
and piped input SHALL execute as a script. An unreadable script file SHALL report an error and
exit with code 1.

#### Scenario: Command text

- **WHEN** a caller supplies statements with `-c`
- **THEN** the statements execute and the session exits without prompting

#### Scenario: Script file

- **WHEN** a caller supplies a file with `-f`
- **THEN** every statement in the file executes in order and the session exits

#### Scenario: Piped script

- **WHEN** statements arrive on standard input from a pipe
- **THEN** the session executes them with no prompts

#### Scenario: Unreadable script file

- **WHEN** the path given to `-f` cannot be read
- **THEN** the session reports an error and exits with code 1

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

### Requirement: Exit codes and output streams

The session SHALL exit with code 0 on success, 1 on a runtime or statement failure, and 2 on a
usage error. Results, introspection reports, and query plans SHALL be written to the current output
target. Prompts, banners, row counts, timings, and errors SHALL be written to standard error.

#### Scenario: Success exit code

- **WHEN** every statement in a scripted session succeeds
- **THEN** the session exits with code 0

#### Scenario: Failure exit code

- **WHEN** a statement in a scripted session fails
- **THEN** the session exits with code 1

#### Scenario: Usage error exit code

- **WHEN** a caller supplies an unknown option or a malformed parameter
- **THEN** the session exits with code 2

#### Scenario: Stream separation

- **WHEN** a caller captures standard output while the session runs
- **THEN** only results, reports, and plans appear there, and diagnostics appear on standard error

### Requirement: Result rendering modes

The session SHALL render results as `table`, `json`, `jsonl`, `csv`, or `line`, selectable by
option and by `.mode`. Columns SHALL appear in projection order. Headers SHALL be shown by default
and toggled by `.headers`. Nulls, lists, maps, and graph entities SHALL have a defined rendering in
every mode.

#### Scenario: Table rendering

- **WHEN** a result renders as a table
- **THEN** a header row names the columns and each value is aligned under its column

#### Scenario: Headers disabled

- **WHEN** headers are disabled
- **THEN** the header row is omitted and rows are unchanged

#### Scenario: JSON rendering

- **WHEN** a result renders as JSON
- **THEN** the output is an array of one object per row, with keys in projection order

#### Scenario: JSON lines rendering

- **WHEN** a result renders as JSON lines
- **THEN** each row is printed as one JSON object on its own line

#### Scenario: CSV quoting

- **WHEN** a value contains a comma, a double quote, or a newline in CSV mode
- **THEN** the field is quoted according to CSV rules so the row parses back unchanged

#### Scenario: Graph entity rendering

- **WHEN** a result contains a node, relationship, or path value
- **THEN** table and line modes show a graph-shaped form and JSON modes emit a tagged object with the entity's id, labels, properties, and, for a relationship, its endpoints

#### Scenario: Null rendering

- **WHEN** a value is null
- **THEN** JSON modes emit `null`, and table, line, and CSV modes mark it distinctly from the empty string

### Requirement: Timing and result footers

An interactive session SHALL report the number of rows a statement produced. It SHALL also report
elapsed time for each statement when timing is enabled with `.timer`. Footers SHALL be written to
standard error and SHALL be absent in non-interactive sessions and when the quiet option is set.

#### Scenario: Row count footer

- **WHEN** an interactive statement returns rows
- **THEN** the row count is reported on standard error

#### Scenario: Timing toggle

- **WHEN** timing is enabled
- **THEN** each statement reports its elapsed time on standard error

#### Scenario: Footers suppressed

- **WHEN** the session is non-interactive or quiet
- **THEN** no row count or timing is reported

### Requirement: Output redirection

`.output PATH` SHALL send subsequent output to a file until another target is set or redirection is
cleared. `.once PATH` SHALL redirect only the next result. A failed redirection SHALL report an
error and preserve the previous output target.

#### Scenario: Redirect to a file

- **WHEN** a caller sets `.output` to a path and then executes statements
- **THEN** their results are written to that file

#### Scenario: Clear redirection

- **WHEN** a caller clears the output redirection
- **THEN** subsequent results return to standard output

#### Scenario: One-shot redirection

- **WHEN** a caller sets `.once` to a path
- **THEN** only the next result is written there and following results return to the previous target

#### Scenario: Redirection failure

- **WHEN** the requested output path cannot be opened
- **THEN** the session reports an error and keeps the previous output target

### Requirement: Session and database commands

The session SHALL provide `.help`, `.quit`, `.exit`, `.open PATH`, `.close`, `.read PATH`, and
`.param NAME=JSON`. `.help` SHALL list the supported commands and `.help COMMAND` SHALL describe
one. `.read` SHALL execute a script file within the current session, and `.quit` and `.exit` SHALL
end the session with exit code 0.

#### Scenario: Help listing

- **WHEN** a caller submits `.help`
- **THEN** the supported commands are listed

#### Scenario: Help for one command

- **WHEN** a caller submits `.help` with a command name
- **THEN** that command's purpose and arguments are described

#### Scenario: Open another database

- **WHEN** a caller submits `.open` with a path
- **THEN** the current database is closed and the session continues on the new database

#### Scenario: Close the database

- **WHEN** a caller submits `.close`
- **THEN** the database is closed and later statements report that no database is open while the session remains usable

#### Scenario: Read a script file

- **WHEN** a caller submits `.read` with a readable file
- **THEN** every statement in the file executes within the current session, including inside an active transaction

#### Scenario: Set a parameter

- **WHEN** a caller submits `.param` with a name and a JSON value
- **THEN** later statements bind that value, and a malformed value reports an error without changing existing parameters

#### Scenario: Quit the session

- **WHEN** a caller submits `.quit` or `.exit`
- **THEN** the session ends with exit code 0

### Requirement: Parameters

`--param NAME=JSON` SHALL bind a query parameter to the JSON-decoded value and SHALL be repeatable
for several parameters. Malformed JSON or a missing name SHALL be a usage error. Bound parameters
SHALL apply to every statement the session executes.

#### Scenario: Bind parameter values

- **WHEN** a caller binds a string, a number, or a list with `--param`
- **THEN** statements bind those values with their JSON types

#### Scenario: Several parameters

- **WHEN** a caller repeats the parameter option
- **THEN** all named values are available to statements

#### Scenario: Malformed parameter

- **WHEN** a parameter value is not valid JSON
- **THEN** the session exits with a usage error and executes nothing

#### Scenario: Parameters across statements

- **WHEN** a script contains several statements that reference a bound parameter
- **THEN** every statement receives the bound value

### Requirement: Explicit transactions

`.begin` SHALL start an explicit write transaction, and subsequent statements SHALL execute inside
it until `.commit` or `.rollback` finishes it. The prompt SHALL indicate an active transaction.
Starting a second transaction, or finishing one when none is active, SHALL report an error and
leave the session usable. Ending the session with an active transaction SHALL roll it back.

#### Scenario: Commit a transaction

- **WHEN** a caller starts a transaction, writes, and commits
- **THEN** the writes are visible to later statements

#### Scenario: Roll back a transaction

- **WHEN** a caller starts a transaction, writes, and rolls back
- **THEN** none of those writes are visible afterwards

#### Scenario: Prompt reports the transaction

- **WHEN** a transaction is active
- **THEN** the prompt indicates it until the transaction finishes

#### Scenario: Transaction state errors

- **WHEN** a caller starts a second transaction, or commits or rolls back without an active one
- **THEN** the session reports an error and remains usable

#### Scenario: Quit with an open transaction

- **WHEN** a caller ends the session while a transaction is active
- **THEN** the transaction is rolled back and a notice is written to standard error

#### Scenario: Database switch with an open transaction

- **WHEN** a caller attempts `.open` or `.close` while a transaction is active
- **THEN** the command is refused and the transaction remains active

### Requirement: Read-only sessions

A read-only session SHALL open an existing database without write access. Write statements,
transaction commands, and mutation commands SHALL be rejected with an error that leaves the
session usable. Reads, `.check`, `.backup`, and query plans SHALL remain available.

#### Scenario: Read in a read-only session

- **WHEN** a caller executes a read statement in a read-only session
- **THEN** the result is returned normally

#### Scenario: Write rejected

- **WHEN** a caller executes a write statement in a read-only session
- **THEN** the session reports an error and stores nothing

#### Scenario: Transaction rejected

- **WHEN** a caller submits `.begin` in a read-only session
- **THEN** the session reports an error and no transaction starts

#### Scenario: Maintenance remains available

- **WHEN** a caller submits `.check` or `.backup` in a read-only session
- **THEN** the command runs against the read-only database

### Requirement: Graph introspection commands

The session SHALL provide `.schema`, `.labels`, `.reltypes`, `.indexes`, `.node ID`, `.rel ID`,
`.expand ID [DEPTH]`, `.path START END`, and `.explain STATEMENT`. These commands SHALL report
metadata and neighborhood information without modifying the graph.

#### Scenario: Schema summary

- **WHEN** a caller submits `.schema`
- **THEN** labels with node counts and property keys, relationship types with relationship counts, and declared indexes are reported in sorted order

#### Scenario: Node details

- **WHEN** a caller submits `.node` with an existing id
- **THEN** its sorted labels, its properties, and its incident relationships with direction and neighbor are shown

#### Scenario: Relationship details

- **WHEN** a caller submits `.rel` with an existing id
- **THEN** its type, start node, end node, and properties are shown

#### Scenario: Expand a neighborhood

- **WHEN** a caller submits `.expand` with an id and an optional depth
- **THEN** a tree of reachable relationships is rendered, the depth defaults to one, each node appears at most once, and a negative or non-integer depth is rejected

#### Scenario: Shortest path

- **WHEN** a caller submits `.path` with two node ids
- **THEN** the shortest path is rendered, or the session reports that no path exists

#### Scenario: Explain without executing

- **WHEN** a caller submits `.explain` with a valid statement
- **THEN** the plan lines are printed and the graph is unchanged

#### Scenario: Missing element

- **WHEN** a caller refers to a node or relationship id that does not exist
- **THEN** the session reports a not-found error and remains usable

### Requirement: Maintenance commands

`.check` SHALL report the store's structural integrity and SHALL print `ok` when no problem is
found. `.backup PATH` SHALL write a consistent copy of the open database to PATH, SHALL refuse a
path that already exists, and SHALL refuse to run while a transaction is active.

#### Scenario: Healthy store

- **WHEN** a caller submits `.check` on a healthy database
- **THEN** the session prints `ok`

#### Scenario: Reported problem

- **WHEN** the store has an integrity or foreign-key problem
- **THEN** `.check` prints the problem lines instead of `ok`

#### Scenario: Backup a live database

- **WHEN** a caller submits `.backup` with a new path
- **THEN** a copy is written that opens as a database with the same nodes and relationships

#### Scenario: Existing backup target

- **WHEN** the backup path already exists
- **THEN** the command is refused and the existing file is unchanged

#### Scenario: Backup during a transaction

- **WHEN** a caller submits `.backup` while a transaction is active
- **THEN** the command is refused and the transaction remains active

### Requirement: Interruption and end of input

Interrupting an interactive prompt SHALL discard the pending buffer and return to the prompt
without ending the session. Interrupting a running statement SHALL report the interruption, leave
the session usable, and leave no transaction open. End of input SHALL end an interactive session
with exit code 0.

#### Scenario: Interrupt at the prompt

- **WHEN** a caller interrupts an interactive prompt with a pending buffer
- **THEN** the buffer is discarded and a new prompt is shown

#### Scenario: Interrupt during a statement

- **WHEN** a running statement is interrupted
- **THEN** the interruption is reported and the session accepts further input

#### Scenario: End of input

- **WHEN** an interactive session receives end of input
- **THEN** the session ends with exit code 0

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
