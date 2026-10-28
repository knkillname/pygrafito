# Tasks

## 1. Python floor and local compatibility

- [x] 1.1 Install a local Python 3.13 interpreter after adding `libsqlite3-dev`, `libffi-dev`, `libbz2-dev`, `liblzma-dev`, `libreadline-dev`, `pkg-config`, and the remaining pyenv build packages; verify `python3.13 -c "import sqlite3, ssl, ctypes, bz2, lzma, readline"` succeeds.
- [x] 1.2 Update `pyproject.toml`: set `requires-python = ">=3.13"`, add the 3.13 classifier, set Ruff `target-version = "py313"`, Pyrefly `python-version = "3.13"`, and the Hatch matrix to `["3.13", "3.14"]`; verify `hatch test -s` lists `hatch-test.py3.13` and `hatch-test.py3.14` and `hatch check` passes.
- [x] 1.3 Quote every eager forward reference flagged by Ruff under `py313` (the 28 in `engine/query/ast.py`, plus `executor.py`, `formatting.py`, `commands.py`, `semantic.py`, and the transaction test helpers), including the `pattern`, `executor`, and `shell` blockers; verify `PYTHONPATH=src python3.13 -c "import pygrafito"` and `hatch test -py 3.13` pass.
- [x] 1.4 Replace the seven `multiprocessing.get_context("fork")` calls in `tests/test_concurrency.py` with a spawn-safe context; verify the concurrency tests pass on Linux and the module imports under `spawn`.
- [x] 1.5 Add `.gitattributes` with `* text=auto eol=lf` and explicit `*.py`/`*.jsonl` rules; verify `git check-attr eol -- tests/conformance/cases.json` reports `lf`.
- [x] 1.6 Document Python 3.13/3.14 support, the Linux support claim, SQLite 3.38, and Google Colab setup in `docs/getting-started/quickstart.md` and `README.md`; add an `[Unreleased]` changelog entry for Python 3.13 support; verify `hatch run docs:build` and `hatch test tests/test_readme.py`.

## 2. CI gate and nightly portability

- [x] 2.1 Split `.github/workflows/ci.yml` into a quality job (`ubuntu-latest`, Python 3.14, `hatch check`), a Linux test matrix (`ubuntu-latest`, 3.13 and 3.14, `hatch test -py ${{ matrix.python }}`), a package job (wheel build and smoke on 3.13 and 3.14), and a docs job (`sphinx -W`); verify the workflow YAML parses and the matrix values match the Hatch matrix.
- [x] 2.2 Add `.github/workflows/nightly.yml` with a `schedule` and `workflow_dispatch`, macOS and Windows runners, Python 3.13 and 3.14, `hatch test -py ... -- --no-cov`, and a failure notification; verify the YAML parses and a `workflow_dispatch` run can be started.
- [x] 2.3 Set Linux cache keys and paths for Hatch/uv and include the Python version in the key; skip caching on the nightly jobs; verify the cache key contains `${{ matrix.python }}` and the nightly jobs contain no cache step.
- [x] 2.4 Add a short support page or section describing the Linux gate and the non-blocking nightly signal; add it to the docs `toctree`; verify `hatch run docs:build`.

## 3. Public API freeze and error hierarchy

- [x] 3.1 Add `tests/test_public_api.py` and a checked-in snapshot of `__all__`, the public methods and properties of `Graph`, `Transaction`, and `PreparedQuery`, the public dataclass fields, and the exception MRO; verify the test passes and a temporary signature change fails it.
- [x] 3.2 Add `docs/reference/api-stability.md` describing the frozen surface, additive minor releases, the `DeprecationWarning` policy, the one-minor minimum, removal only in 2.0, and PEP 702; add it to the API toctree and add an `[Unreleased]` changelog entry; verify `hatch run docs:build`.
- [x] 3.3 Audit and document the exception hierarchy in `docs/api/errors.md`, and add a test that every exported exception inherits `PygrafitoError` and matches the snapshot; verify the test and docs build.

## 4. Query error contract, property tests, and result memory

- [x] 4.1 Add a parser depth guard (initially 64) and a `RecursionError` backstop that raises a positioned `QuerySyntaxError`; add tests for deeply nested parentheses, lists, and maps; document the limit in `docs/reference/query-language.md`; verify the tests pass and the docs build.
- [x] 4.2 Catch oversized integer literal conversion and raise a positioned `QuerySemanticError`; add boundary tests for the conversion limit and a 5000-digit literal; verify no `ValueError` escapes.
- [x] 4.3 Add Hypothesis to the test environment with a deterministic gate profile and a longer nightly profile; add lexer/parser property tests and `@example` regressions for the two known leaks; verify the gate profile passes and the nightly profile is documented.
- [x] 4.4 Add SQL predicate generation property tests that keep `json_type` paired with `json_extract` and exercise quoted JSON paths with quotes, newlines, tabs, unicode, and `$`; verify with and without declared indexes.
- [x] 4.5 Add result-memory tests (fully materialized result, `max_rows` bound, no streaming API) and document the contract in `docs/reference/query-language.md` and `docs/reference/embedding-contract.md`; add an `[Unreleased]` changelog entry; verify the tests pass and the docs build.
- [x] 4.6 Add value and key property tests for the query value surface: valid scalars round-trip, invalid values raise `ValidationError`, and property keys with quotes, newlines, tabs, unicode, dots, and `$` match through predicates; verify the tests pass.

## 5. Crash and recovery

- [x] 5.1 Add a subprocess crash harness using `SIGKILL` on POSIX and `Process.kill()` on Windows, with tests for commit durability, mid-transaction absence, WAL recovery, and integrity after reopen; verify the tests pass on Linux and the harness is platform-guarded.
- [x] 5.2 Add backup crash tests: the source remains unchanged, no partial destination is left, and a read-only source has the same guarantee; verify the tests pass.
- [x] 5.3 Add restore crash tests for an empty target, a replaced target, integrity after reopen, and no partial graph; verify the tests pass.
- [x] 5.4 Add import crash tests for atomic and non-atomic imports; verify a terminated import leaves either the committed batches or none, never a corrupt graph.
- [x] 5.5 Document durability, WAL recovery, backup and restore crash behavior, and import atomicity in `docs/reference/embedding-contract.md`, `docs/guides/embedding.md`, and `docs/reference/snapshot-format.md`; verify `hatch run docs:build`.

## 6. Format freeze and golden fixtures

- [x] 6.1 Create a small TRON-themed golden version 2 database and a canonical version 2 JSONL snapshot under `tests/fixtures/`; add tests that open the database, restore the snapshot, export again, and compare bytes; verify the tests pass.
- [x] 6.2 Add refusal tests for version 1 and version 3 databases and snapshots, asserting the error names version 2 and the export path, and that the file is unchanged; verify the tests pass.
- [x] 6.3 Freeze the view version and add tests for `graph_meta` and `Graph.view_version`; verify the tests pass.
- [x] 6.4 Document the frozen schema, snapshot, and view versions, 0.9/1.0 compatibility, the refusal policy, and the absence of automatic migration in `docs/reference/snapshot-format.md` and `docs/reference/embedding-contract.md`; add an `[Unreleased]` changelog entry; verify `hatch run docs:build`.

## 7. Import and codec property tests

- [x] 7.1 Add Hypothesis tests for CSV, JSONL, and in-memory import: arbitrary input raises a library error, row and batch numbers are reported, and atomic versus non-atomic behavior leaves the expected graph; verify the tests pass.
- [x] 7.2 Add Hypothesis tests for the snapshot codec: canonical bytes, header counts, truncated and extra records, and round-trip stability; verify the tests pass.
- [x] 7.3 Document import atomicity, including the non-atomic default and the recommendation to enable `atomic` for bulk loads, in `docs/guides/importing.md`; verify `hatch run docs:build`.

## 8. Benchmarks, documentation, and integration

- [x] 8.1 Add file-backed benchmark scenarios for queries, traversal, and ingestion and record the results in `docs/reference/performance.md`; verify the benchmark command runs and the page builds.
- [x] 8.2 Add known limitations and a production checklist covering materialized results, Linux support, SQLite 3.38, ingestion throughput, no streaming, no automatic migration, and Colab `/content` storage; add them to the docs toctree; verify `hatch run docs:build`.
- [x] 8.3 Update `README.md` install and Python support guidance; verify `hatch test tests/test_readme.py`.
- [x] 8.4 Review `CHANGELOG.md` under `[Unreleased]` for end-user wording and the required categories; verify the entries describe outcomes without internal names or SQL details.
- [x] 8.5 Run the full gate: `hatch check --fix`, `hatch test`, `hatch run docs:build`, `openspec validate "harden-for-1-0" --strict`, `openspec validate --specs --strict`, `uv build`, and a clean wheel smoke test on 3.13 and 3.14; verify coverage is at least 80% and `py.typed` and `LICENSE.txt` are packaged.
- [x] 8.6 Run the Linux gate on both supported Python versions and confirm the 3.14 quality, package, and docs jobs pass; verify the 3.13 and 3.14 test jobs are green.

## Workflow follow-up

- Run `/opsx-apply` to implement this change; do not start implementation from the proposal step.
- After implementation is complete and verified, sync the delta specs to the main specs, archive the change, and create the Git commit required by `AGENTS.md`.
- Trigger the nightly workflow manually once after merge and record any macOS or Windows failures as follow-up issues rather than release blockers.
