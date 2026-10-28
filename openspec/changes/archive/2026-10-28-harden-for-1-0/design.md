# Design

## Context

`pygrafito` shipped 0.9.0 on 2026-10-27 with a complete GQL profile and 21 archived changes. The
remaining 1.0 work is evidence and contracts, not language surface. The current constraints that
shape this design:

- `requires-python` is `>=3.14`, the Hatch test matrix is `["3.14"]`, and CI runs only
  `ubuntu-latest` with Python 3.14.
- The source uses PEP 695 generics, `type` aliases, `typing.override`, and `Self`, all of which are
  3.12 or older. It does not use a 3.13- or 3.14-only API.
- Many annotations rely on 3.14's deferred evaluation (PEP 649). The first three import failures on
  3.13 are `ListLiteral.items: tuple[Expression, ...]` and similar class-body references in
  `engine/query/ast.py`, `QueryExecutor.__init__(executor: QueryExecutor)` in
  `engine/query/executor.py`, and `Commands.__init__(shell: Shell)` where `Shell` is imported only
  under `TYPE_CHECKING`. Ruff's `py313` target flags 34 eager forward references in total.
- The query boundary leaks two built-in exceptions: deep nesting raises `RecursionError`, and an
  oversized integer literal raises `ValueError` from Python's integer conversion limit.
- `QueryResult` is a frozen, fully materialized tuple of rows. `QueryBudget.max_rows` defaults to
  100,000 intermediate bindings.
- Schema version 2, snapshot version 2, and the interop view version are the current formats. 0.9
  already writes version 2, so a frozen version 2 is an identity migration from 0.9.
- Seven concurrency tests hard-code `multiprocessing.get_context("fork")`.
- The repository is public, so standard GitHub-hosted runners are free. The current CI workflow
  completes in about 48 seconds.
- Hypothesis is not a dependency, but `.hypothesis/` is already ignored.

## Goals / Non-Goals

**Goals:**

- Make Python 3.13 and 3.14 a supported, tested platform on Linux.
- Freeze the Python API, the schema layout, the snapshot format, and the view version for 1.x.
- Make the query, import, and codec boundaries total: every failure is a `PygrafitoError`.
- Prove crash durability, format compatibility, and adversarial-input behavior with automated
  tests.
- Keep the runtime standard library only and the public surface small.

**Non-Goals:**

- New GQL constructs, profile changes, or Cypher extensions.
- A public streaming result API.
- Automatic database migration.
- Claiming macOS or Windows support before the nightly signal is green.
- Python 3.12 support.
- A `MERGE` or ingestion fast path.
- Server, driver, or multi-tenant features.

## Decisions

### 1. Python floor 3.13, with quoted forward annotations

Set `requires-python = ">=3.13"`, keep classifiers for 3.13 and 3.14, set Ruff `target-version` to
`py313`, Pyrefly `python-version` to `3.13`, and the Hatch matrix to `["3.13", "3.14"]`.

The eager forward annotations are quoted rather than reordered or deferred with
`from __future__ import annotations`. A union that contains a forward reference is quoted as a
whole (for example `"Expression | None"`), because `"Expression" | None` is evaluated as a string
union on 3.13. Quoting is the smallest change, works on both 3.13 and 3.14, and does not violate
the project rule against future imports. Reordering the definitions would churn the AST and
executor modules for no user benefit.

Alternatives:

- **3.14-only:** rejected because it excludes Google Colab and most current users, and because the
  only blockers are three quotes.
- **3.12 floor:** technically possible, but it would require the same annotation fixes plus a
  broader compatibility test matrix, and it gives up PEP 702. The user chose 3.13 as the floor.

### 2. Linux gate plus nightly portability

The blocking CI is Linux only:

```text
ci.yml
  quality   ubuntu-latest, Python 3.14, hatch check
  test      ubuntu-latest, Python 3.13 and 3.14, hatch test -py ...
  package   ubuntu-latest, wheel build and smoke on 3.13 and 3.14
  docs      ubuntu-latest, sphinx -W

nightly.yml
  schedule  03:00 UTC
  test      macos-latest, windows-latest x Python 3.13, 3.14
  failure   GitHub scheduled-workflow notification; no release block
```

Linux is the support claim because it is the only platform the maintainer can debug locally, and
because the library is embedded and file-backed. The nightly job keeps the code portable without
overclaiming. Full cross-platform gating was rejected as unnecessary for 1.0; Linux-only was
rejected because the nightly signal is free on a public repository.

The nightly job runs the suite without coverage (`--no-cov`) so coverage stays a Linux-gate
concern and platform skips cannot fail the 80% threshold. The quality job runs once, not per
matrix entry.

### 3. Materialized results, no streaming API

`QueryResult` remains fully materialized. The contract is documented in the embedding and query
references: the intermediate row budget bounds the result, the default is 100,000 rows, and a
caller can lower it for memory-sensitive embeddings.

The engine already streams internally (`RowStream`) and materializes at the public boundary. A
public streaming API would be a second way to consume results and would need to define transaction
lifetime, budget accounting across lazy rows, behavior when iteration stops early, and handle
affinity. That complexity is not justified for 1.0.

Alternative: a context-managed streaming iterator. Rejected for 1.0; it can be added additively in
1.1 without changing `QueryResult`.

### 4. Frozen formats, refusal, and no automatic migration

Freeze schema version 2, snapshot version 2, and the current view version. 0.9 and 1.0 files are
therefore mutually readable. A file from another version is refused with a message naming the
supported version and an export path. Additive schema objects such as indexes and constraints do not
change the layout version, which the existing requirement already guarantees.

Golden fixtures prove compatibility: a small version 2 database and a canonical version 2 JSONL
snapshot are checked in. Tests open the database, restore the snapshot, export again, and compare
bytes. Tests also create version 3 headers and assert the refusal.

Alternatives:

- **Automatic migration on open:** rejected. It needs migration code for every past version, cannot
  run on a read-only handle, and risks silent data rewriting. It is the opposite of the SQLite
  model of stable formats.
- **Explicit migration command now:** deferred until a format bump actually needs it. There is no
  format change in this release.

### 5. Total query input error contract

Add a parser depth guard and catch integer conversion failures at the lexer boundary. The guard
uses a documented maximum nesting depth (initially 64) and raises a positioned `QuerySyntaxError`
before Python's stack limit is reached. A `RecursionError` backstop maps any remaining stack
failure to the same query error. Integer tokens are converted with a bounded conversion that raises
a positioned `QuerySemanticError` instead of relying on Python's global `int` digit limit, which
must not be changed.

Alternatives:

- Raising the recursion limit or the integer digit limit: rejected. It moves the failure and makes
  memory use unpredictable.
- Accepting arbitrary nesting and literals: rejected. The parser is recursive and the query value
  surface does not need unbounded literals.

### 6. Hypothesis for property tests

Add Hypothesis as a test-only dependency. Use two profiles:

- **Gate:** deterministic, `max_examples` around 50, `deadline=None`, example database off.
- **Nightly:** longer `max_examples` around 500, on Linux only; portability is the separate
  macOS/Windows job.

Invariants cover the lexer and parser (only `QueryError` escapes), the codec (valid values round
trip; invalid values raise `ValidationError`), SQL predicate generation (`json_type` and
`json_extract` stay paired; quoted paths survive quotes, newlines, unicode, and `$`), import
(arbitrary CSV/JSONL raises a library error; atomic mode leaves no graph), snapshot (export,
restore, export is byte-stable; truncated and extra records are rejected), and the budget (counters
never go negative; exhaustion raises `QueryBudgetExceededError`).

The two known leaks become explicit `@example` regression tests. Hypothesis was chosen over seeded
`random` because shrinking turns a failure into a minimal, reviewable repro. `pytest-bdd` is not an
alternative: it is a scenario-formatting tool, not an input generator, and the conformance corpus
already owns acceptance-style coverage.

### 7. Crash and recovery tests

Run each crash scenario in a subprocess that opens a file-backed graph, performs the operation, and
signals readiness. The parent kills it with `SIGKILL` on POSIX and `Process.kill()` on Windows, then
reopens the file.

Covered scenarios:

- Commit survives termination; a mid-transaction kill leaves no partial write.
- WAL recovery and `check_integrity` after abrupt termination.
- Backup termination leaves the source unchanged and no partial destination.
- Restore termination leaves the target at its previous committed state.
- Import termination leaves either the committed batches (non-atomic) or none (atomic), never a
  corrupt graph.

The SQLite default `synchronous = FULL` in WAL mode is the durability baseline; it is documented,
not changed. Import keeps `atomic=False` as the default for performance, with the trade-off
documented and both modes tested.

Alternative: injecting failures in-process. Rejected because it does not exercise SQLite's WAL
recovery or the operating system's file semantics.

### 8. Golden public API snapshot

A new `tests/test_public_api.py` records `__all__`, the public methods and properties of `Graph`,
`Transaction`, and `PreparedQuery`, public dataclass fields, and the exception MRO, and compares
them with a checked-in snapshot. A signature or name change fails the test until the snapshot is
updated deliberately.

The deprecation policy is documented and implemented with `DeprecationWarning`; on Python 3.13,
`warnings.deprecated` (PEP 702) provides static visibility. Removal waits for a major release.

Alternatives: docs-only policy (too easy to drift), or a runtime deprecation registry (more
machinery than a 1.x library needs).

### 9. Documentation and performance

The apply run updates the Sphinx site for every behavior and configuration change: Python support,
Colab setup, result memory, format freeze and migration, API stability and deprecation, the error
contract, known limitations, a production checklist, and file-backed performance.

The benchmark harness gains file-backed runs for queries, traversal, and ingestion. The existing
in-memory numbers stay. The ~484 rows/s ingestion figure is documented as a known limitation; the
single-node `MERGE` fast path remains deferred to a separate change.

## Risks / Trade-offs

- **3.13 eager evaluation exposes more annotation issues** → the three known annotations are fixed
  first; the full suite runs on 3.13; Pyrefly targets 3.13 so new forward references are caught.
- **OpenSSL 4.0.3 on Ubuntu 26.10 breaks the local pyenv build** → CI uses prebuilt
  `setup-python`; locally, install `libsqlite3-dev` and `libffi-dev` first and verify `_ssl` after
  the build. Fall back to a container or 3.13.16 if necessary.
- **The Windows nightly starts red because of the seven `fork` tests** → convert them to `spawn`
  before enabling the nightly, or track the initial failure as a known issue rather than noise.
- **Hypothesis makes CI slower or flaky** → bounded gate profile, deterministic seed, no network or
  wall-clock assertions, and the example database is not shared between jobs.
- **A parser depth guard changes accepted input** → the limit is documented and generous; existing
  queries are far below it; the conformance corpus proves no regression.
- **Freezing formats too early constrains 1.x** → version 2 is already the 0.9 format; additive
  schema objects keep the version; breaking changes require 2.0 and a migration.
- **Coverage fails on a platform job** → coverage is owned by the Linux gate; the nightly runs
  `--no-cov`.
- **Scheduled workflows disable after 60 days of repository inactivity** → documented; a commit or
  manual run re-enables it.
- **Windows line endings break goldens or formatting** → add `.gitattributes` with `eol=lf`.

## Migration Plan

There is no data migration: schema version 2 and snapshot version 2 do not change, and 0.9 files
open in 1.0.

Rollout order:

1. Metadata and annotation fixes (`requires-python`, targets, three quotes).
2. Linux CI gate with 3.13 and 3.14.
3. Error-contract fixes and Hypothesis suites.
4. Crash/recovery suites and golden fixtures.
5. Public API snapshot and deprecation docs.
6. Documentation, benchmarks, and changelog.
7. Enable the nightly cross-platform job.
8. Release 1.0 is a separate change.

Rollback is a revert of metadata, CI, tests, and docs; no user data changes.

## Open Questions

- The initial parser depth limit is 64. It can be tuned after measuring the conformance corpus and
  the fuzz profile; the value is documented either way.
- The nightly failure notification starts with GitHub's scheduled-workflow email. If that proves
  easy to miss, a later change can open an issue automatically. This does not affect the specs or
  the approach.
