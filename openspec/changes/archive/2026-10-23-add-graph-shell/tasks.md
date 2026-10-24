# Tasks

## 1. Read-only graph handles

- [x] 1.1 Add `ReadOnlyError` to the domain errors, export it from `pygrafito`, and verify `tests/test_read_only.py` asserts it is a `PygrafitoError` and appears in `pygrafito.__all__`.
- [x] 1.2 Implement `Graph.open(..., readonly=True)` over a `mode=ro` connection with `PRAGMA query_only`, rejecting `:memory:`, a missing file, and a database that needs a schema write; verify `hatch test tests/test_read_only.py` covers each rejection and that a cleanly closed WAL database reopens read-only.
- [x] 1.3 Guard writes in `Graph.transaction`, `Graph._require_index_access`, and `QueryExecutor.execute_graph` through `Database.ensure_writable`; verify tests show `ReadOnlyError` for a convenience write, a query with a write clause, an index declaration, and a transaction request, with nothing stored.
- [x] 1.4 Document the read-only handle in the README persistence section with a runnable example and add the `[Unreleased]` changelog entry; verify `hatch test tests/test_readme.py` executes the example.

## 2. Manual transaction control

- [x] 2.1 Add `Transaction.begin`, `Transaction.commit`, and `Transaction.rollback` and delegate `__enter__`/`__exit__` to them; verify `hatch test tests/test_transaction.py` covers a manual commit, a manual rollback, and preservation of transaction state after a failed write.
- [x] 2.2 Reject out-of-order use with `TransactionError`: begin twice, commit or rollback without begin, and commit or rollback after finishing; verify each case is a separate test.
- [x] 2.3 Update the README transaction section and the `Transaction` docstrings, and add the `[Unreleased]` changelog entry; verify the README example still runs under `hatch test tests/test_readme.py`.

## 3. Maintenance operations

- [x] 3.1 Implement `Graph.backup_to` with a temporary sibling copy and atomic replace, refusing an existing destination or an active transaction; verify a test copies a live graph, reopens the copy with identical content, and confirms a refused destination is unchanged.
- [x] 3.2 Implement `Graph.check_integrity` over `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, returning an empty tuple for a healthy store; verify tests cover a healthy graph and a database with a foreign-key violation.
- [x] 3.3 Verify both operations work on a read-only handle and document them in the README persistence section and the `[Unreleased]` changelog; verify the documented snippets run.

## 4. Shell package, invocation, and packaging

- [x] 4.1 Create `src/pygrafito/cli/` with the `app`, `shell`, `session`, `reader`, `commands`, and `formatting` modules, each with the SPDX header, plus `src/pygrafito/__main__.py`; verify `tests/cli/test_package.py` imports every module and `tests/test_package.py` lists them.
- [x] 4.2 Implement `App` argument parsing for the database argument, `-c`, `-f`, `--format`, `--param`, `--readonly`, and `-q`; verify tests cover each option, mutual exclusion of `-c` and `-f`, `--help`, and exit code 2 for a usage error.
- [x] 4.3 Declare `[project.scripts] pygrafito = "pygrafito.cli.app:App.main"` and keep `App.main` a static method; verify a metadata test finds the entry point and a subprocess test runs `python -m pygrafito --help` with exit code 0.
- [x] 4.4 Extend the wheel smoke test in CI to run `pygrafito --help` and `python -m pygrafito --help`; verify by running the same commands after `uv build` and installing the wheel in a temporary environment.
- [x] 4.5 Document invocation, options, and startup behavior in `docs/cli.md` and add a "Command-line shell" section to the README; verify every documented command runs and `hatch test tests/test_readme.py` passes.

## 5. Statement input

- [x] 5.1 Implement the boundary scanner and splitter: `;` outside strings, backticks, line comments, and block comments; multiple statements per input; pending remainder; final statement flushed at end of input; empty and comment-only input ignored; verify `tests/cli/test_reader.py` covers each rule.
- [x] 5.2 Implement dot-command detection for a `.`-prefixed line at the start of a buffer only, including leading whitespace and ignoring `.` lines inside an accumulated statement; verify tests for a command, an unknown command, and a dot line inside a statement.
- [x] 5.3 Document the input rules, continuation prompt, and terminator behavior in `docs/cli.md`; verify the documented multi-line example runs.

## 6. Result formatting

- [x] 6.1 Implement text rendering for `table`, `line`, and `csv`, including display widths, control-character escaping, null and boolean rendering, and graph-shaped node, relationship, and path text; verify golden tests cover alignment, embedded newlines, and non-ASCII widths.
- [x] 6.2 Implement `json` and `jsonl` with tagged entity objects and projection-order keys; verify tests round-trip the output with `json.loads` and compare key order.
- [x] 6.3 Implement the headers toggle and empty-result rendering for every mode; verify tests show the header-only table, header-only CSV, `[]` for JSON, and empty output for JSONL and line.
- [x] 6.4 Document every mode with an example in `docs/cli.md`; verify each example by running it against a temporary database and comparing the shown output.

## 7. Session and interactive loop

- [x] 7.1 Implement `Session` state and execution routing through the active transaction or the graph, and the `Shell` read-route-execute loop with banner, prompt, continuation prompt, and end-of-input handling; verify `tests/cli/test_shell.py` drives it with injected streams and covers a multi-line statement and a bare `.quit`.
- [x] 7.2 Implement `.help`, `.help COMMAND`, `.quit`, `.exit`, `.open`, `.close`, and `.read`; verify tests cover help output, switching databases, closing and reopening, refusing statements with no open database, and `.read` executing a script inside an active transaction.
- [x] 7.3 Implement `.mode`, `.headers`, `.timer`, `.output`, and `.once`, including file closure and preserving the previous target when an output path fails; verify tests read the redirected files and check that `.once` applies to one result only.
- [x] 7.4 Implement `.begin`, `.commit`, and `.rollback` with a transaction prompt indicator, refusal of `.open` and `.close` while active, and rollback with a notice when the session ends; verify tests cover commit, rollback, each state error, and the quit path.
- [x] 7.5 Implement interactive footers: row counts, elapsed time when enabled, and mutation summary counts for statements without columns, all on standard error and suppressed by `-q`; verify tests capture stdout and stderr separately.
- [x] 7.6 Implement interruption handling: clear the pending buffer on Ctrl-C, report an interrupted statement, and keep the session usable; verify tests simulate `KeyboardInterrupt` and assert no transaction remains open.
- [x] 7.7 Document the interactive session, prompt states, and session commands in `docs/cli.md` and add the `[Unreleased]` changelog entry; verify the documented transcript runs.

## 8. Graph introspection commands

- [x] 8.1 Implement `.indexes`, `.labels`, `.reltypes`, and `.schema` with sorted output, node counts, relationship counts, and sorted property keys; verify tests build a themed graph and assert the exact report.
- [x] 8.2 Implement `.node` and `.rel` with sorted labels, properties, and incident relationships showing direction and neighbor; verify tests for a node with incoming and outgoing edges, a self-loop, and a missing id.
- [x] 8.3 Implement `.expand ID [DEPTH]` as a level-by-level breadth-first walk with a visited set, a depth default of one, and ASCII tree connectors; verify tests for depth one versus two, a cycle, a self-loop, and a rejected negative or non-integer depth.
- [x] 8.4 Implement `.path START END [DIRECTION]` over the shortest-path API, defaulting to both directions, and report when no path exists; verify tests for each direction, a symmetric pair, and a disconnected pair.
- [x] 8.5 Implement `.explain STATEMENT` printing plan lines to the output target without executing; verify a test confirms the graph is unchanged and the plan is non-empty.
- [x] 8.6 Document the introspection commands with examples in `docs/cli.md` and add the `[Unreleased]` changelog entry; verify the examples run.

## 9. Maintenance commands and read-only sessions

- [x] 9.1 Implement `.check` printing `ok` or the reported problem lines; verify tests for a healthy store and a store with a foreign-key violation.
- [x] 9.2 Implement `.backup PATH` with destination-exists and active-transaction refusals; verify a test opens the copy and compares node and relationship counts, and that a refused backup leaves the file unchanged.
- [x] 9.3 Implement `--readonly` session behavior: write statements, mutation commands, and `.begin` are rejected while reads, `.check`, and `.backup` work, and a missing file exits 1; verify one test per case.
- [x] 9.4 Document read-only sessions, backup, and integrity checking in `docs/cli.md` and add the `[Unreleased]` changelog entry; verify the documented commands run.

## 10. Scripting and process contract

- [x] 10.1 Implement `-c`, `-f`, and piped-standard-input execution with no prompts, fail-fast on the first failing statement, a reported failing statement position, and exit code 1 for an unreadable file; verify tests cover each input path and the stop-on-error behavior.
- [x] 10.2 Decode `--param NAME=JSON` and `.param NAME=JSON` with one shared decoder that rejects malformed names, malformed JSON, and the non-standard `NaN` and `Infinity` constants; verify tests for strings, numbers, lists, repeats, and each rejection as a usage error.
- [x] 10.3 Enforce the exit-code contract and stream separation across interactive and scripted sessions; verify tests assert 0, 1, and 2 and that captured stdout contains only results, reports, and plans.
- [x] 10.4 Render query errors with their message and line and column, continue an interactive session, and stop a script; verify tests for a syntax error with a position and a semantic error without one.
- [x] 10.5 Document scripting, parameters, exit codes, and agent-facing examples in `docs/cli.md`, the README, and the `AGENTS.md` command list, and add the `[Unreleased]` changelog entry; verify the documented script runs.

## 11. Integration verification

- [x] 11.1 Run `hatch check --fix` and `hatch test`; verify both pass and coverage reports at least 80 percent.
- [x] 11.2 Run `openspec validate add-graph-shell --strict` and `openspec validate --specs --strict`; verify both report the change and specs valid.
- [x] 11.3 Run the full documented transcript from `docs/cli.md` against a temporary database, including create, query, formats, expand, path, backup, reopen, and a read-only session; verify the output matches the documentation and the file is reusable after reopen.
- [x] 11.4 Map every scenario in both spec deltas to a test name and verify no scenario is uncovered.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Release the version that ships the shell and verify the wheel installs the `pygrafito` command.
