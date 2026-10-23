# Design

## Context

See `proposal.md` for motivation. The current tree already has the full property-graph MVP:
`Graph` delegates writes to `Transaction`, repositories own SQL, and traversals materialize an
`AdjacencySnapshot`. `Database` tracks `_closed` but does not expose it. `Transaction.__enter__`
issues `BEGIN IMMEDIATE` and wraps failures in `TransactionError`. Tests run through `hatch test`,
and the project has no CI workflow.

The target workload is thousands of elements with read-heavy traversal. This change deliberately
stays on the foundation; it does not alter the storage layout, traversal algorithms, or public
graph semantics beyond lifecycle errors.

## Goals / Non-Goals

**Goals:**

- Make closed-handle use fail with one predictable domain error.
- Make a convenience write inside an explicit transaction fail before SQL, with a clear message,
  without silently joining the transaction.
- Apply the TRON fixture convention to the existing corpus and keep it from regressing.
- Make README examples executable and make CI verify lint, types, tests, packaging, and the
  installed wheel.

**Non-Goals:**

- Query operators, adjacency APIs, property indexes, snapshot redesign, or path analytics.
- Nested/savepoint transactions or automatic transaction joining.
- A text query language or import/export.
- Changing the database schema or schema version.

## Decisions

### D1: Commit the baseline before implementation

The working tree currently has the metadata, license, `CHANGELOG.md`, and `AGENTS.md` edits
uncommitted. Commit those edits (and this change's planning artifacts, if desired) before the first
implementation task so the foundation diff stays reviewable. If planning artifacts need separate
review, commit only the pre-existing edits and leave `openspec/changes/harden-foundation/`
untracked until implementation.

### D2: `GraphClosedError` and a single lifecycle check

Add `GraphClosedError(PygrafitoError)` to `model.py` and export it from `pygrafito.__init__` and
`pygrafito.model.__all__`. Add `Database.ensure_open()` that raises it when `_closed` is true.

`Graph` calls `self._database.ensure_open()` at the start of every public read, write, and traversal
method. `Graph.transaction()` checks as well, so convenience writes fail before constructing a
transaction. `Graph.close()` remains idempotent and does not check.

Alternatives considered:

- **Wrap `sqlite3.ProgrammingError` at the boundary.** Less direct, and some paths fail with
  `TransactionError` instead. An explicit guard produces one consistent error before SQL runs.
- **Make `GraphClosedError` inherit from `sqlite3.ProgrammingError`.** Preserves old `except`
  clauses, but couples the domain model to SQLite. The project is 0.1; document the exception change
  instead.

The `Transaction` object holds its own connection reference. Closing the graph while a transaction
is active remains misuse; `Database.close()` rolls back and closes the connection. This change does
not add per-transaction closed-state tracking.

### D3: Detect an active transaction in `Transaction.__enter__`

Before issuing `BEGIN IMMEDIATE`, check `self._connection.in_transaction`. If true, raise
`TransactionError("a graph transaction is already active; use the active transaction")`. This
covers `Graph` convenience writes and direct `Transaction` use, and it runs before any SQL.

The guard does not suppress the exception. If the caller does not catch it inside the outer
transaction, the outer block still rolls back. The spec only guarantees that the active transaction
is usable when the caller handles the error. Tests will cover the caught path and confirm the
transaction can still commit.

Alternative considered: make convenience writes join the active transaction automatically. Rejected
because it hides transaction boundaries, changes atomicity expectations, and would make a failed
convenience write part of the caller's unit of work without an explicit decision. Savepoints are a
larger design and stay out of scope.

### D4: TRON fixture mapping

Rename graph fixtures and README examples using the closest TRON role. Pure model, codec, package,
and schema tests that do not build a graph keep their generic values.

| Generic fixture | TRON replacement |
| --- | --- |
| `Ada` | `Kevin Flynn` |
| `Grace` | `Quorra` |
| `Bob` | `Sam Flynn` |
| `Alice` / `Carol` | `Tron` / `Yori` |
| `Person` | `User` for users, `Program` for programs, `ISO` for ISOs |
| `Employee` | `Program` |
| `Manager` | `SystemMonitor` |
| `KNOWS` | `ALLIES_WITH` |
| `LIKES` | `TRUSTS` |
| `ROUTE` | `GRID_LINK` |
| `start` / `middle` / `end` | `Grid` / `Arena` / `Portal` |
| `A` / `B` / `C` | `Tron` / `Clu` / `Rinzler` |
| `age` | `cycles` |
| `since` | `since_cycle` |
| `name` | `designation` |

Use places such as `Grid`, `Arena`, `Outlands`, `Portal`, and `Safehouse` for traversal fixtures.
Use roles such as `User`, `Program`, `ISO`, and `SystemMonitor` as labels. Keep variable names such
as `first`, `second`, and `node` unchanged; the convention applies to graph data, not Python
identifiers.

Add `tests/test_naming_convention.py`. It parses every `tests/**/*.py` file with `ast`, walks
string constants, and fails when a constant is exactly one of the banned placeholder names
(`Ada`, `Grace`, `Bob`, `Alice`, `Carol`, `Dave`, `Person`, `Employee`, `Manager`, `KNOWS`,
`LIKES`, `ROUTE`). Exact matching avoids flagging substrings. Exclude the guard file itself from
the scan.

Alternative considered: rely on review only. Rejected because the convention is new and the
existing corpus is large; a cheap guard prevents drift.

### D5: Execute README Python snippets in tests

Add `tests/test_readme.py`. It reads the repository `README.md`, extracts fenced blocks tagged
`python` with a regular expression, and executes each block with `exec` in a fresh namespace. Use
`monkeypatch.chdir(tmp_path)` and redirect stdout so a snippet cannot write into the repository or
pollute test output. Blocks tagged `console` are skipped.

The snippets already use temporary directories or `:memory:`, so the test needs no network or
persistent files. Executing each block in isolation matches the way a reader copies one example at
a time.

Alternative considered: convert README blocks to doctests. Rejected because the examples use
multi-line `with` blocks and comments with expected output; fenced-block execution checks the same
contract with less churn.

### D6: CI quality and packaging jobs

Add `.github/workflows/ci.yml` on push and pull request with two jobs:

```text
quality
  checkout
  setup Python 3.14
  install uv and Hatch
  hatch check          # lint, format check, Pyrefly
  hatch test           # pytest, coverage gate, README snippets

package (needs quality)
  checkout
  setup Python 3.14
  install uv
  uv build
  create a clean virtual environment
  install the built wheel
  run an in-memory graph smoke script
  verify the wheel contains py.typed and LICENSE.txt
```

Use `uv tool install hatch` and add `$HOME/.local/bin` to `GITHUB_PATH`; cache uv and Hatch
directories. If `setup-python` does not yet provide a stable 3.14 on the runner, use
`uv python install 3.14` and `uv python pin 3.14` instead. The wheel check uses a short stdlib
`zipfile` script so it does not add a dependency. If the license file is missing from the wheel,
declare `license-files = ["LICENSE.txt"]` in `pyproject.toml`.

`hatch check` runs without `--fix` in CI so formatting or lint drift fails the build. The existing
coverage gate remains inside `hatch test`.

### D7: Documentation and changelog updates

Update `README.md` examples to TRON names and note that the snippets are executed by the test
suite. Update `AGENTS.md` with the CI gate, the README snippet test, and the fixture guard. Add
`CHANGELOG.md` entries under `[Unreleased]` for `GraphClosedError`, the transaction guard, and the
development workflow changes.

## Risks / Trade-offs

- **Exception-type change for closed handles** -> Document it as a breaking change for callers
  catching `sqlite3.ProgrammingError`; keep the new error in the domain hierarchy and cover it in
  the release notes.
- **Nested write guard still rolls back when uncaught** -> The guard improves diagnosis, not
  control flow. Test the caught path, document the transaction rule, and keep automatic joining out
  of scope.
- **Fixture rename is a large diff** -> Apply one mapping table consistently, run the full suite
  after each test module group, and let the guard test catch misses.
- **Source-scanning guard false positives** -> Scan AST string constants only, use exact matches,
  and exclude the guard file.
- **Executing README code** -> Only execute repository-owned `python` blocks, isolate the working
  directory, capture stdout, and keep examples on temporary or in-memory storage.
- **CI Python 3.14 availability** -> Prefer `setup-python`; fall back to `uv python install 3.14`.
- **Wheel contents drift** -> The package job fails if `py.typed` or `LICENSE.txt` is missing; fix
  the packaging configuration rather than weakening the check.

## Migration Plan

No data migration. The schema version stays at 1. The public API gains `GraphClosedError`; callers
that catch SQLite exceptions for closed handles must catch the new domain error. Release as a
normal `[Unreleased]` entry under the next version when the change is archived.
