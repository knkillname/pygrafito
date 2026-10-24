# Proposal

## Why

`pygrafito` is an embedded, single-file property graph with a complete engine but no operator
surface: inspecting a graph, seeding a fixture, checking a file, or demonstrating the query
language all require writing Python. An embedded database is only as useful as the tools that can
open it, and the project's own framing - a file-backed store with no service to operate - depends
on a shell the way the SQLite ecosystem depends on its command-line shell. Building that shell now
also forces the library's gaps into the open: it is the first consumer that exercises the public
API from outside the package.

## What Changes

- Add `graph-shell`: an interactive and scripted command line for a graph database, available as
  the `pygrafito` console command and as `python -m pygrafito`.
- Read statements and dot-commands from a terminal, `-c`, `-f`, or piped input. Statements may span
  lines and a `;` terminator is recognized outside strings, quoted identifiers, and comments.
  Several statements may be submitted in one input.
- Render results as `table`, `json`, `jsonl`, `csv`, or `line`, with a headers toggle, per-statement
  timing, and `.output` / `.once` redirection. Results go to stdout; prompts, banners, timing, and
  errors go to stderr.
- Add session dot-commands for help, opening and closing a database, scripts, parameters, and
  output control.
- Add graph-aware introspection: `.schema`, `.labels`, `.reltypes`, `.indexes`, `.node`, `.rel`,
  `.expand`, `.path`, and `.explain`.
- Add explicit transaction commands `.begin`, `.commit`, and `.rollback`, with the prompt reporting
  an active transaction and a rollback when the session ends with one open.
- Add maintenance commands `.check` for an integrity report and `.backup PATH` for a consistent
  copy of a live database.
- Open a session read-only with `--readonly`; reject writes and mutation commands while keeping
  reads, `.check`, and `.backup` usable.
- Extend the library to support the shell: read-only graph handles with a dedicated error, manual
  transaction control, and backup and integrity-check operations. These additions are additive and
  do not change the stored schema, the query dialect, or existing behavior.
- Package a console entry point and a `__main__` module, and document the shell in `docs/cli.md`
  and the README.

## Capabilities

### New Capabilities

- `graph-shell`: the command-line shell's invocation and modes, statement input and boundaries,
  dot-commands, output modes and streams, exit codes, read-only sessions, transactions, graph
  introspection, and maintenance commands.

### Modified Capabilities

- `property-graph`: adds read-only graph handles, manual transaction control in addition to the
  context-manager form, and database maintenance operations for backup and integrity checking.

## Impact

- Affected code: new `src/pygrafito/cli/` package (application, session, statement reader,
  commands, formatting) and `src/pygrafito/__main__.py`; additive changes to
  `src/pygrafito/model.py`, `src/pygrafito/engine/graph.py`,
  `src/pygrafito/engine/transaction.py`, `src/pygrafito/engine/query/executor.py`, and
  `src/pygrafito/storage/connection.py`; `src/pygrafito/__init__.py` exports.
- Public API: `Graph.open(..., readonly=True)`, `Graph.backup_to`, `Graph.check_integrity`,
  `Transaction.begin`, `Transaction.commit`, `Transaction.rollback`, and `ReadOnlyError`.
- Packaging: `[project.scripts]` entry point; the wheel gains the `pygrafito` command. No runtime
  dependency is added; the shell uses the standard library only.
- Data: no schema version change and no file-format change.
- Documentation: `docs/cli.md`, a README section, `CHANGELOG.md`, and the command list in
  `AGENTS.md`.
- Tests: a new `tests/cli/` suite plus library tests for the new operations; CLI tests build
  graphs with the project's themed fixture names.
