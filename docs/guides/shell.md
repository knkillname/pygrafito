# Use the shell

Use the `pygrafito` command when you want to inspect, query, or maintain a graph without writing
Python. The shell operates on one database file at a time, or on a transient in-memory graph when
no path is given.

This guide covers the common session workflows. The [CLI
reference](../reference/cli.md) owns every option, dot command, output rule, and exit code.

## Start a session

```console
$ pygrafito grid.db
pygrafito 0.6.0 | grid.db | type ".help" for commands
grid.db> CREATE (n:Program {designation: 'Tron', cycles: 40});
1 node created
grid.db> MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles;
+------+--------+
| name | cycles |
+------+--------+
| Tron | 40     |
+------+--------+
1 row
```

Statements end with a semicolon and may span lines. Use `.help` to list commands and `.quit` or
`.exit` to leave.

## Run one statement

`-c` runs a statement and exits. Results go to standard output; diagnostics go to standard error.

```console
$ pygrafito grid.db -c "MATCH (n:Program) RETURN n.designation AS name;" --format json
[
  {
    "name": "Tron"
  }
]
```

## Run a script or pipe input

`-f` runs a file, and non-terminal standard input is read as a script. Both modes suppress the
banner and prompts, which keeps pipelines clean.

```console
$ pygrafito grid.db -f seed.txt
$ cat query.txt | pygrafito grid.db --readonly
```

A script stops at the first failing statement and reports its position. Dot commands are
recognized at the start of a statement.

## Choose an output format

`--format` accepts `table`, `json`, `jsonl`, `csv`, and `line`. In an interactive session,
`.mode` changes the format without restarting.

```console
grid.db> .mode csv
grid.db> .headers on
grid.db> MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles;
name,cycles
Tron,40
```

Use `.output PATH` to redirect results until `.output off`, or `.once PATH` to redirect only the
next result. `.timer on` adds statement timing, and `.param NAME=JSON` binds a parameter.

## Inspect the graph

`.schema` summarizes labels, relationship types, indexes, constraints, and the journal mode.
`.labels`, `.reltypes`, `.indexes`, and `.constraints` report each part separately.

```console
grid.db> .schema
Labels
  Program           1 node   cycles, designation
Relationship types
Indexes
Constraints
Journal mode
  wal
```

`.node`, `.rel`, `.expand`, and `.path` inspect individual elements and neighborhoods:

```console
grid.db> .node 1
Node 1
  labels: Program
  properties: {cycles=40, designation="Tron"}
  relationships
grid.db> .path 1 3
(1)-[:ALLIES_WITH]->(2)-[:ALLIES_WITH]->(3)
grid.db> .explain MATCH (n:Program) WHERE n.cycles = 40 RETURN n
SEARCH n0 USING INDEX pygrafito_idx_node_cycles (<expr>=?)
```

## Move data in and out

`.import` maps CSV or JSONL rows through one write statement. `.export` and `.restore` use the
versioned JSONL snapshot format.

```console
grid.db> .import programs.jsonl --statement "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})"
imported 2 rows in 1 batches; created 2 nodes/0 relationships; deleted 0 nodes/0 relationships; 0 properties set, 0 removed, 0 labels added, 0 removed
grid.db> .export grid.jsonl
exported 2 nodes and 0 relationships to grid.jsonl
grid.db> .restore grid.jsonl --replace
restored 2 nodes and 0 relationships from grid.jsonl
```

The importer accepts `--format`, `--batch`, and `--atomic`. See [Importing data](importing.md)
for formats and failure behavior, and [Snapshot format](../reference/snapshot-format.md) for the
record grammar and SQL views.

## Use transactions

`.begin` starts an explicit transaction, and the prompt marks the state with `*`. Use `.commit` to
keep the writes or `.rollback` to discard them.

```console
grid.db> .begin
grid.db*> CREATE (n:Program {designation: 'Clu', cycles: 41});
grid.db*> .rollback
```

Starting a second transaction, or committing without one, reports an error and leaves the session
usable. Ending the session with an open transaction rolls it back.

## Open read-only

`--readonly` opens an existing file without write access. Reads, queries, `.check`, `.backup`, and
`.explain` work; writes and `.begin` are rejected without ending the session.

```console
$ pygrafito --readonly grid.db
pygrafito 0.6.0 | grid.db (read-only) | type ".help" for commands
grid.db> CREATE (n:Program {designation: 'Clu'});
error: graph handle is read-only
```

## Maintain the database

`.check` reports structural integrity problems. `.backup PATH` writes a consistent copy while the
database is open and refuses a destination that already exists.

```console
grid.db> .check
ok
grid.db> .backup backup.db
backup written to backup.db
```

## Go deeper

- [CLI reference](../reference/cli.md) for every option, dot command, output mode, and exit code.
- [Snapshot format](../reference/snapshot-format.md) for the JSONL contract.
- [`Graph`](../api/graph.md) for the same operations from Python.
