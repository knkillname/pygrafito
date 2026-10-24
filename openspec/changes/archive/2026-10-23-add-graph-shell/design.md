# Design

## Context

See `proposal.md` for motivation and `specs/graph-shell/spec.md` plus
`specs/property-graph/spec.md` for the behavior contract. This section records only the current
state that shapes the approach.

- The package has one public surface, `pygrafito`, and a one-way import chain
  `model <- storage <- engine <- __init__`. No console entry point exists, and
  `pyproject.toml` declares no scripts.
- `Graph.query` executes exactly one statement and raises `TransactionError` while an explicit
  transaction is active. `Transaction.query` is the only path that participates in a transaction.
- `Transaction` is context-manager-only: `BEGIN IMMEDIATE` in `__enter__`, commit or rollback in
  `__exit__`, then marked finished.
- `Graph.open` controls file creation with `create`, but there is no read-only mode. The
  connection is opened read-write with WAL, foreign keys, and a 5000 ms busy timeout.
- Property writes funnel through `Graph.transaction` or `QueryExecutor.execute_graph`; index
  changes bypass transactions through `Graph._require_index_access`.
- `pygrafito` is a package, so `python -m pygrafito` requires a package-level `__main__.py`.
- Project rules require every function to be a method, no module-level functions, SPDX headers,
  numpydoc docstrings, and stdlib-only runtime dependencies.
- `AGENTS.md` requires tests in the same task group as the code, TRON-themed fixtures for
  graph-building tests, a `[Unreleased]` changelog entry, and `hatch check --fix` plus
  `hatch test` before archive.

## Goals / Non-Goals

**Goals:**

- Keep the shell a presentation layer: it must not reimplement matching, mutation, traversal, or
  property semantics, and it must consume only the public `pygrafito` surface.
- Use one input pipeline for a terminal, `-c`, `-f`, and piped input, so scripted and interactive
  behavior cannot drift.
- Make the shell deterministic and testable without a terminal: injected streams, golden output,
  a scriptable exit-code contract.
- Keep every library addition additive: no behavior change for existing callers, no schema change,
  no runtime dependency.
- Preserve the existing error hierarchy and wrap storage failures at the existing boundaries.

**Non-Goals:**

- Raw SQL pass-through, a second query language, or any storage access from the CLI package.
- Data movement (`dump`, `import`, CSV/JSON loading), schema migrations, streaming result
  cursors, or result paging.
- A curses interface, a graphical or browser view, colorized output, or shell configuration
  files and plugins.
- Input history and line editing as a specified contract; `readline` integration is best-effort
  and untested behavior.
- Multi-database attach, a network mode, or background jobs inside one session.

## Decisions

### D1: The shell is a package that depends only on the public surface

```text
 model <- storage <- engine <- pygrafito/__init__ <- pygrafito.cli
                                                   \
                                                    <- pygrafito/__main__.py
```

```text
 src/pygrafito/cli/
   app.py         argument parsing, process wiring, exit code
   shell.py       read route execute loop, prompts, interruption, quit
   session.py     open database, transaction, output target, formatting state
   reader.py      statement boundaries, dot-command detection, pending buffer
   commands.py    dot-command registry and handlers
   formatting.py  value rendering and the table/json/jsonl/csv/line writers
 tests/cli/
   test_app.py  test_reader.py  test_formatting.py  test_commands.py  test_shell.py
```

`cli` imports `pygrafito` (the package under test), stdlib modules, and CamelCase types. It never
imports `engine`, `storage`, or their internals, which keeps the shell an honest consumer of the
public API. The alternative, letting the shell read `Graph._database` for counts or schema
details, was rejected: it would couple the shell to storage internals and hide API ergonomics
problems that this change exists to expose.

### D2: Entry points use a static method

`pyproject.toml` gains:

```toml
[project.scripts]
pygrafito = "pygrafito.cli.app:App.main"
```

`App.main` is a staticmethod returning an exit code, and `src/pygrafito/__main__.py` calls it
under a `__main__` guard. This satisfies the "every function is a method" rule without a
module-level function, and entry points support dotted attributes. The alternative, exporting a
module-level instance with `__call__`, was rejected as surprising. `python -m pygrafito` and the
console script are the same code path.

### D3: One statement scanner feeds every input mode

```text
 stdin line -> dot-command? (buffer empty) -> command
            -> otherwise append to buffer -> split on top-level ";"
                                             -> execute complete statements in order
                                             -> keep remainder as the pending buffer
```

The scanner walks characters and tracks four regions: `'...'` strings with backslash escapes,
`` `...` `` identifiers with doubled backticks, `//` line comments, and `/* */` block comments. A
`;` outside all four ends a statement. Whitespace-only and comment-only segments are discarded.
At end of input the remainder, if not empty, is treated as a final statement.

The scanner does not validate syntax; it only finds boundaries. It duplicates a small part of
`Lexer`, so the test suite includes boundary cases that the lexer also accepts: semicolons in
strings, backticks, comments, and escaped quotes. The alternative, splitting the token stream from
`Lexer.tokenize`, was rejected because interactive input is frequently incomplete (an open string
is exactly the state while the user is typing) and tokenization fails there; tokens also do not
help decide when to stop reading. Dot-commands are recognized only when the buffer is empty, so a
`.` line inside a statement remains statement text.

### D4: `Session` owns the mutable shell state and routes execution

```text
 Session
   graph        Graph | None
   transaction  Transaction | None
   target       graph or transaction      <- statements dispatch here
   format       table | json | jsonl | csv | line
   headers      bool
   timer        bool
   output       stream or file target
   parameters   mapping[str, QueryValue]
```

Every statement executes through `session.target.query(text, session.parameters)`. When a
transaction is active, that is `Transaction.query`, which already participates in the transaction
and reports uncommitted writes. Otherwise it is `Graph.query`. This mirrors the existing guard in
`Graph.query` and avoids a parallel execution path. `.explain` calls `Graph.explain` and never
executes, so it is allowed during a transaction. A session with no open database reports
`no database is open` for statements and graph commands until `.open`.

`.output PATH` opens a UTF-8 text file for the rest of the session, or `.output off` returns to
standard output; `.once PATH` sets a one-shot target consumed by the next result. Files opened by
the session are closed on `.output` replacement, `.once` consumption, `.close`, and session end.
A failed open reports an error and leaves the previous target in place.

### D5: Read-only handles are enforced at the connection and at the API

`Graph.open(path, *, create=True, readonly=False)` keeps its current meaning when `readonly` is
false. When `readonly` is true:

- `:memory:` is rejected with `ValidationError`; read-only protects a file.
- A missing path raises `NotFoundError` and creates nothing.
- The connection uses a `file:...?mode=ro` URI with `uri=True`, then `PRAGMA query_only = ON`.
- `Schema.bootstrap` runs against the read-only connection. On a current graph database the
  `CREATE TABLE IF NOT EXISTS` statements are no-ops and the version check passes. If SQLite
  reports that a write is required, the open raises `UnsupportedSqliteError` explaining that a
  read-only session needs an existing, current graph database.

`Database` gains `readonly` and `ensure_writable()`. The guard is called from exactly three
places: `Graph.transaction` (all convenience writes and explicit transactions), `Graph._require_index_access`
(index declarations and drops), and `QueryExecutor.execute_graph` when
`plan.analysis.is_write`. It raises a new `ReadOnlyError(PygrafitoError)`. Reads, traversal,
`explain`, `indexes`, `check_integrity`, and `backup_to` stay available.

The alternative, relying only on `PRAGMA query_only`, was rejected because it still creates a
missing file and leaves the connection read-write at the OS level. `mode=ro` plus `query_only` is
belt and braces and gives a deterministic `ReadOnlyError` instead of a SQLite operational error.
The WAL caveat is recorded under risks.

### D6: Manual transaction control is a small state machine

```text
          begin()                 commit() / rollback()
  new ------------> active ---------------------------> finished
                     |  ^
        begin() (err) |  | begin() (err)
                     +--+
  new or finished: commit() / rollback() raise TransactionError
```

`Transaction` gains `begin`, `commit`, and `rollback`. `begin` performs the current `BEGIN
IMMEDIATE` and returns `self`; `commit` and `rollback` perform the current finishing logic and set
`_active = False` and `_finished = True`; `__enter__` returns `begin()`; `__exit__` calls
`commit()` or `rollback()`. `_finished` preserves the existing rule that a used transaction cannot
be restarted. A failed `BEGIN` leaves the transaction unused and usable, as today.

`TransactionError` is already the right signal for out-of-order use, so no new error type is
needed. The alternative, exposing raw `BEGIN`/`COMMIT` statements through the dialect, was
rejected: transaction control is not part of the query language, and the existing language
rejects multiple statements.

### D7: Backup and integrity use the sqlite3 connection API

`Graph.backup_to(path) -> Path` uses `Connection.backup(destination_connection)`, which performs a
consistent page-level copy from a live database and works with a read-only source. The method:

1. calls `ensure_open`, then rejects an existing destination with `ValidationError`;
2. rejects `connection.in_transaction` with `TransactionError`;
3. copies to a sibling temporary path and `os.replace`s it into place, removing the temporary file
   on failure, so an interrupted copy never leaves a half-written destination.

`Graph.check_integrity() -> tuple[str, ...]` runs `PRAGMA integrity_check` and
`PRAGMA foreign_key_check`, returns an empty tuple when both are clean, and otherwise returns one
formatted line per problem. Both methods work on read-only handles.

`VACUUM INTO` was considered for backup and rejected: it is one statement, but it cannot run inside
a transaction, needs temporary space, and would need path quoting in SQL. `Connection.backup` is
the documented stdlib mechanism for exactly this case.

### D8: Formatting contract is explicit and shared by every mode

A single `ValueFormatter` renders one value per mode, and each writer composes rows from it.

```text
  table:  +-------------+--------+
          | name        | cycles |
          +-------------+--------+
          | Quorra      | 37     |
          +-------------+--------+

  line:   name = Quorra
          cycles = 37
          <blank line between rows>

  csv:    name,cycles
          Quorra,37

  json:   [ { "name": "Quorra", "cycles": 37 } ]      (2-space indent)

  jsonl:  {"name": "Quorra", "cycles": 37}            (one per line)
```

Rules:

- Columns render in projection order; JSON object keys use the same order.
- Null renders as `NULL` in table and line, an empty field in CSV, and `null` in JSON. Booleans
  render as `true`/`false` everywhere. Lists and maps render as compact JSON text in text modes.
- Entities use graph-shaped text: `(:Program {id: 1, designation: "Quorra"})`,
  `(1)-[:ALLIES_WITH {id: 3}]->(2)`, and `(1)-[:ALLIES_WITH]->(2)` for a path. JSON modes emit
  tagged objects: `{"kind": "node", "id": 1, "labels": [...], "properties": {...}}`,
  `{"kind": "relationship", "id": 3, "type": "...", "start": 1, "end": 2, "properties": {...}}`,
  and `{"kind": "path", "nodes": [...], "relationships": [...]}`.
- Table and line modes escape control characters (`\n`, `\t`, `\r`) so a value can never break
  the row layout; CSV relies on standard quoting and JSON encodes them. Display width uses
  `unicodedata.east_asian_width` plus zero width for combining marks; values are never truncated
  or wrapped.
- CSV uses `csv.writer` with minimal quoting and `newline=""`; JSON is stdlib `json`.
- Headers are printed for table and CSV when enabled; `line` and JSON modes do not use a header
  row. A result with no rows prints the header and borders in table mode, the header in CSV mode,
  `[]` in JSON mode, nothing in JSONL and line modes. A statement with no columns prints nothing
  in every mode.
- No ANSI color in this change; golden tests and redirected output stay byte-stable.

The table style is ASCII (`+`, `-`, `|`) for portability and consistency with the project's plain
documentation style.

### D9: Introspection commands are built on the public API

| Command | Implementation |
| --- | --- |
| `.node ID` | `graph.node(id)`, then `MATCH (n)-[r]-(m) WHERE id(n) = $id RETURN r, m` for incident edges |
| `.rel ID` | `graph.relationship(id)` |
| `.expand ID [DEPTH]` | level-by-level BFS: `MATCH (n)-[r]-(m) WHERE id(n) IN $ids RETURN r, m`, skipping already expanded nodes; default depth 1 |
| `.path START END [DIRECTION]` | `graph.shortest_path(start, end, direction=...)`; default `Direction.BOTH` for exploration, explicit token for the other directions |
| `.schema` | `MATCH (n) RETURN labels(n) AS labels, keys(n) AS keys` and `MATCH ()-[r]->() RETURN type(r) AS type` aggregated in Python, plus `graph.indexes()` |
| `.labels` / `.reltypes` | the same aggregations, without property keys |
| `.indexes` | `graph.indexes()` |
| `.explain STATEMENT` | `graph.explain(statement, session.parameters)`, printed to the output target |

`keys(n)` was verified to return sorted property keys, and `id(n) IN $ids` was verified with a list
parameter, so no new query functions are needed. `.expand` renders a tree with `+-` and `|` ASCII
connectors and never expands a node twice, so it terminates for cyclic graphs. `.schema` scans the
whole graph; that cost is documented rather than hidden behind storage-level SQL, because the
command exists to exercise the public surface.

### D10: Streams, footers, and exit codes

```text
  stdout: results, introspection tables, plan lines, help text
  stderr: banner, prompts, continuation prompts, row counts, timing, errors
```

Interactive means: no `-c` and no `-f`, and `sys.stdin.isatty()`. The banner, prompts, row count
footers, and error messages are stderr only. Footers are one line (`2 rows` or `2 rows · 1.4 ms`);
a statement without columns reports its mutation summary instead (`1 node created, 1 relationship
created`). Footers are suppressed by `-q` and in non-interactive sessions. Exit codes are 0 for
success, 1 for a runtime or statement failure, and 2 for an argument or parameter error; argparse
supplies 2 for usage errors, and `App.main` lets that `SystemExit` propagate. `Ctrl-C` at a prompt
clears the buffer and continues; `Ctrl-C` during a statement propagates as `KeyboardInterrupt`,
which the existing executor already converts into a rollback, and the shell reports it and
continues.

### D11: Parameters are JSON values

`--param NAME=JSON` splits on the first `=`, validates the name against the dialect's parameter
identifier form, and decodes the value with `json.loads`. Strings, numbers, booleans, nulls, and
lists therefore map directly to query values; objects decode to mappings, which are valid query
values but still rejected as stored properties by the existing rules. The decoder rejects the
non-standard `NaN` and `Infinity` constants, which `json.loads` accepts by default. A malformed
value or a missing name is a usage error (exit 2). `.param NAME=JSON` sets the same values
interactively; bare `.param` lists them.

The alternative, treating values as strings unless quoted, was rejected because it makes
`--param cycles=37` a string and surprises every caller.

### D12: Testing is terminal-free and fixture-consistent

`Shell` receives input, output, and error streams plus an argument list, so tests drive it with
`io.StringIO` and no subprocess. Subprocess tests cover only the process wiring: `python -m
pygrafito`, exit codes, and piped stdin. A metadata test asserts that the `pygrafito` console
script is declared, instead of depending on the installed script path. Golden files cover the five
formats and entity rendering. Graph-building tests use the project's themed names, as
`tests/test_naming_convention.py` already enforces for any file that mentions `Graph.open`.

## Risks / Trade-offs

- **[Read-only open of a WAL database]** SQLite can require the `-shm`/`-wal` files or a writable
  directory for a read-only WAL connection -> a cleanly closed `pygrafito` file has no WAL files,
  and the error is mapped to a clear message. The `.close` path keeps the current
  "last connection checkpoints" behavior. This is documented and covered by a test that reopens a
  closed file read-only.
- **[Ctrl-C cannot preempt one long SQLite call]** -> the executor catches `BaseException` and
  rolls back, and the shell reports the interruption; responsiveness is best-effort between stages
  and rows. A progress handler is deferred.
- **[Scanner and lexer drift]** -> the scanner only finds boundaries, and its tests use the same
  tricky literals the lexer accepts; parsing still happens in the engine.
- **[`.schema` and `.expand` cost]** -> `.schema` scans labels and keys, and `.expand` runs one
  query per level with a default depth of one and a visited set. Both are documented as
  exploratory commands, not batch tools.
- **[JSON entity shape becomes a contract]** -> the shapes are documented in `docs/cli.md` and
  covered by golden tests, and future changes are additive.
- **[Wide or many-column output]** -> widths are computed, never truncated; users redirect with
  `.output` or switch to JSON for machine use.
- **[New public API surface before 1.0]** -> additions are narrow (`ReadOnlyError`, three `Graph`
  methods, three `Transaction` methods) and each maps to a spec requirement; no existing behavior
  changes.

## Migration Plan

Purely additive: no schema version bump, no file-format change, no required user action. Existing
callers keep the current `Graph.open` and context-manager behavior. Rollout is a normal release:
the wheel gains the `pygrafito` console script, `python -m pygrafito` starts working, and the
README and `docs/cli.md` document the shell. Rollback is reverting the release; databases written
by the new version remain readable by the previous one because the schema is unchanged.

## Open Questions

- Whether a short binary alias should also be installed; it affects packaging and documentation
  only, not the specified behavior.
- Whether a later change should add TTY color output for entities and labels.
- Whether result streaming is worth adding once a shell use case needs very large projections.
- Whether `.dump`/`.import` belong in a follow-up data-movement change; the current design keeps
  them out so backup does not need an id-remapping format.
