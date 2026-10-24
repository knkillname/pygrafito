# Command-line shell

`pygrafito` includes a shell for inspecting, querying, and maintaining a graph database without
writing Python. The `pygrafito` command and `python -m pygrafito` start the same shell.

## Invocation

```console
$ pygrafito grid.db
$ pygrafito grid.db -c "MATCH (n:Program) RETURN count(*) AS programs;"
$ pygrafito grid.db -f seed.txt
$ cat query.txt | pygrafito grid.db --format json
$ pygrafito --readonly grid.db
```

| Option | Meaning |
| --- | --- |
| `DATABASE` | Database file. Omit it to open a transient in-memory graph. |
| `-c TEXT` | Run the given statements and exit. |
| `-f PATH` | Run a script file and exit. |
| `--format MODE` | One of `table`, `json`, `jsonl`, `csv`, `line`. Defaults to `table`. |
| `--param NAME=JSON` | Bind a query parameter. Repeat for several parameters. |
| `--readonly` | Open an existing database without write access. |
| `-q`, `--quiet` | Suppress the banner and interactive footers. |

A database argument opens the file and creates it when it does not exist. With no argument the
session uses a transient in-memory graph. `--readonly` never creates a file and reports an error
when the database is missing.

The shell is interactive only when no command or script is supplied and standard input is a
terminal. Interactive sessions print a banner and prompts on standard error; scripts print
neither, so standard output stays clean for piping.

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

## Input and statements

Statements end with a semicolon and may span lines. A semicolon inside a string, a backtick-quoted
identifier, a `//` line comment, or a `/* ... */` block comment does not end the statement. An
unterminated statement at the end of a script or interactive input is executed as if it ended with
a semicolon.

```console
grid.db> MATCH (a:Program)-[:ALLIES_WITH]->(b)
   ...> WHERE a.cycles > 35
   ...> RETURN a.designation AS source, b.designation AS target;
```

Several statements can appear in one input and run in source order:

```console
grid.db> CREATE (a:Program {designation: 'Kevin Flynn'});
        CREATE (b:Program {designation: 'Quorra'});
        CREATE (a)-[:ALLIES_WITH]->(b);
```

A line whose first non-whitespace character is `.` is a shell command when no statement is being
accumulated. Command names are case-sensitive; an unknown command reports an error and leaves the
session usable. A dot line inside a statement is statement text.

## Output modes

`.mode` selects how results render, and `--format` selects the startup mode. The examples
below use `MATCH (n:Program {designation: 'Quorra'}) RETURN n.designation AS name, n.cycles AS
cycles;`.

```console
grid.db> .mode table
+--------+--------+
| name   | cycles |
+--------+--------+
| Quorra | 37     |
+--------+--------+

grid.db> .mode json
[
  {
    "name": "Quorra",
    "cycles": 37
  }
]

grid.db> .mode jsonl
{"name":"Quorra","cycles":37}

grid.db> .mode csv
name,cycles
Quorra,37

grid.db> .mode line
name = Quorra
cycles = 37
```

`table` is the default and uses an ASCII border. `json` is an indented array of objects, `jsonl`
writes one compact object per row, and `csv` quotes fields when they contain a comma, quote, or
newline. `line` writes one field per line and a blank line between rows.

Values render the same way in every text mode: `NULL` for null in table and line, an empty field in
CSV, and `null` in JSON; `true` and `false` for booleans; JSON text for lists and maps. Table and
line modes escape newlines and tabs so a value cannot break the row layout; CSV relies on normal
quoting and JSON encodes them.

Graph values use graph-shaped text in the text modes and tagged objects in JSON:

```console
grid.db> MATCH (n:Program {designation: 'Quorra'}) RETURN n;
+-------------------------------------------------------+
| n                                                     |
+-------------------------------------------------------+
| (:Program {id: 2, cycles: 37, designation: "Quorra"}) |
+-------------------------------------------------------+

grid.db> MATCH (a:Program)-[r:ALLIES_WITH]->(b) RETURN r;
+----------------------------------------------------+
| r                                                  |
+----------------------------------------------------+
| (1)-[:ALLIES_WITH {id: 1, since_cycle: 2020}]->(2) |
+----------------------------------------------------+
```

In JSON modes a node becomes
`{"kind": "node", "id": 1, "labels": [...], "properties": {...}}`, a relationship adds
`"type"`, `"start"`, and `"end"`, and a path contains `"nodes"` and `"relationships"`.

`.headers off` hides the table and CSV header row. A result with no rows prints the header only in
table mode, the header in CSV mode, `[]` in JSON mode, and nothing in JSONL and line modes.

## Timing and footers

An interactive session reports the number of rows a statement produced and, with `.timer on`, its
elapsed time. A statement without a projection reports its mutation counts instead. Footers go to
standard error and are suppressed in scripts and with `-q`.

```console
grid.db> .timer on
grid.db> MATCH (n:Program) RETURN n;
...
3 rows, 1.4 ms
```

## Redirection

`.output PATH` sends results to a file until another target is chosen. `.output off` restores
standard output, and a bare `.output` prints the current target. `.once PATH` redirects only the
next output.

```console
grid.db> .output out.txt
grid.db> MATCH (n:Program) RETURN n.designation;
grid.db> .output off
```

A redirection that cannot open its path reports an error and keeps the previous target.


## Session commands

| Command | Purpose |
| --- | --- |
| `.help [COMMAND]` | List commands, or describe one. |
| `.quit`, `.exit` | Leave the session. |
| `.open PATH` | Close the current database and open another. |
| `.close` | Close the current database; the session stays open. |
| `.read PATH` | Run a script file in the current session. |
| `.mode MODE` | Select `table`, `json`, `jsonl`, `csv`, or `line`. |
| `.headers on\|off` | Show or hide table and CSV headers. |
| `.timer on\|off` | Report statement timing. |
| `.output PATH\|off` | Redirect results, or restore standard output. |
| `.once PATH` | Redirect the next output only. |
| `.param NAME=JSON` | Bind a parameter; bare `.param` lists them. |
| `.begin`, `.commit`, `.rollback` | Control an explicit transaction. |
| `.schema`, `.labels`, `.reltypes`, `.indexes` | Report graph metadata. |
| `.node ID`, `.rel ID` | Inspect one element. |
| `.expand ID [DEPTH]` | Render a neighborhood tree. |
| `.path START END [DIRECTION]` | Render the shortest path. |
| `.explain STATEMENT` | Show a plan without executing it. |
| `.check` | Report structural integrity. |
| `.backup PATH` | Write a consistent copy of the database. |

With no database open, statements and graph commands report `no database is open`; `.open`
recovers the session.

## Transactions

`.begin` starts an explicit transaction. Statements run inside it until `.commit` or `.rollback`,
and the prompt marks the state with `*`:

```console
grid.db> .begin
grid.db*> CREATE (n:Program {designation: 'Clu', cycles: 41});
grid.db*> .rollback
```

Starting a second transaction, or committing or rolling back without one, reports an error and
leaves the session usable. `.open` and `.close` are refused while a transaction is active. Ending
the session with an open transaction rolls it back and reports that on standard error.

## Introspection

`.schema` summarizes labels with node counts and property keys, relationship types with
relationship counts, and declared indexes. `.labels`, `.reltypes`, and `.indexes` report each part
separately.

```console
grid.db> .schema
Labels
  ISO               1 node   cycles, designation
  Program           3 nodes   cycles, designation
  SystemMonitor     1 node   designation
Relationship types
  ALLIES_WITH       2 relationships
  GUARDS            1 relationship
Indexes
  node cycles
```

`.node` shows labels, properties, and incident relationships with direction and neighbor. `.rel`
shows one relationship's type, endpoints, and properties.

```console
grid.db> .node 3
Node 3
  labels: Program
  properties: {cycles=40, designation="Tron"}
  relationships
    <- ALLIES_WITH (:ISO:Program {id: 2, cycles: 37, designation: "Quorra"}) id=2
    -> GUARDS (:Program {id: 3, cycles: 40, designation: "Tron"}) id=3

grid.db> .rel 1
Relationship 1
  type: ALLIES_WITH
  start: 1
  end: 2
  properties: {since_cycle=2020}
```

`.expand` walks the neighborhood breadth first, defaults to one level, and shows each node once, so
cycles and self-loops terminate. `.path` uses both directions unless a direction is given.

```console
grid.db> .expand 1 2
(:Program {id: 1, cycles: 36, designation: "Kevin Flynn"})
+-[:ALLIES_WITH]-> (:ISO:Program {id: 2, cycles: 37, designation: "Quorra"})
  +-[:ALLIES_WITH]-> (:Program {id: 3, cycles: 40, designation: "Tron"})

grid.db> .path 1 3
(1)-[:ALLIES_WITH]->(2)-[:ALLIES_WITH]->(3)

grid.db> .path 3 1 OUTGOING
no path from 3 to 1
```

`.explain` prints the plan for a read statement and changes nothing:

```console
grid.db> .explain MATCH (n:Program) WHERE n.cycles = 36 RETURN n
SEARCH n0 USING COVERING INDEX pygrafito_idx_node_6379636c6573 (<expr>=? AND <expr>=?)
SEARCH label_0 EXISTS USING COVERING INDEX node_labels_by_label (label=? AND node_id=?)
```

## Read-only sessions

`--readonly` opens an existing database without write access. Reads, queries, `.check`, `.backup`,
and `.explain` work; write statements, mutation commands, and `.begin` report an error that leaves
the session usable. A read-only session never creates a file, and a missing path exits with code 1.

```console
$ pygrafito --readonly grid.db
pygrafito 0.6.0 | grid.db (read-only) | type ".help" for commands
grid.db> CREATE (n:Program {designation: 'Clu'});
error: graph handle is read-only
```

## Backup and integrity

`.check` prints `ok` or the structural problems it finds. `.backup PATH` writes a consistent copy
while the database is open, refuses a path that already exists, and is refused while a transaction
is active.

```console
grid.db> .check
ok
grid.db> .backup backup.db
backup written to backup.db
```

## Scripting and exit codes

`-c`, `-f`, `.read`, and piped input run without prompts. A script stops at the first failing
statement and reports its position; dot-commands are recognized at the start of a statement.

```console
$ pygrafito grid.db -c "MATCH (n:Program) RETURN n.designation AS name;" --format json
[
  {
    "name": "Kevin Flynn"
  },
  {
    "name": "Quorra"
  },
  {
    "name": "Tron"
  }
]
$ pygrafito grid.db -f seed.txt
error: statement 2: unexpected token (line 1, column 8)
$ echo "MATCH (n:Program) RETURN count(*) AS total;" | pygrafito grid.db
+-------+
| total |
+-------+
| 3     |
+-------+
```

Parameters are JSON values, decoded from `--param NAME=JSON` or `.param NAME=JSON`. JSON objects
decode to mappings, which are valid query values but are still rejected as stored properties.

```console
$ pygrafito grid.db --param 'name="Quorra"' -c 'MATCH (n:Program {designation: $name}) RETURN n;'
```

| Exit code | Meaning |
| --- | --- |
| `0` | Every statement and command succeeded. |
| `1` | A statement, command, or file failed at runtime. |
| `2` | Invalid arguments or parameters. |

Standard output carries results, reports, and plans. Prompts, banners, footers, and errors go to
standard error, so redirecting the shell's output yields only data.
