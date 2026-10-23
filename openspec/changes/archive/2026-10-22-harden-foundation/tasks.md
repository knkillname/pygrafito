# Tasks

## 1. Baseline

- [x] 1.1 Commit the pending metadata, license, `CHANGELOG.md`, and `AGENTS.md` edits (plus this
  change's planning artifacts if they are ready for review) so implementation starts from a clean
  tree; verify with `git status --short` that only intended files remain.
- [x] 1.2 Confirm the TRON fixture mapping in `design.md` matches the existing test groups and note
  any test-only files that should keep generic values; verify the list covers every graph-building
  test module under `tests/`.

## 2. Closed Graph Handles

- [x] 2.1 Add `GraphClosedError(PygrafitoError)` to `model.py`, export it from
  `pygrafito.__init__` and `pygrafito.model.__all__`, and add tests for the hierarchy and public
  export; verify with `hatch test tests/test_model.py tests/test_package.py`.
- [x] 2.2 Add `Database.ensure_open()` and call it at the start of every public `Graph` read, write,
  and traversal method, including `Graph.transaction()`; add tests for node/relationship reads,
  convenience writes, and `traverse`/`shortest_path`/`paths` after close; verify with
  `hatch test tests/test_graph.py tests/test_transaction.py`.
- [x] 2.3 Add `[Unreleased]` changelog entries for `GraphClosedError` and closed-handle behavior,
  including the exception-type change for callers that catch SQLite errors; verify the entries are
  present under the correct Keep a Changelog category.

## 3. Active Transaction Guard

- [x] 3.1 Add a `Connection.in_transaction` guard in `Transaction.__enter__` that raises a clear
  `TransactionError` before `BEGIN IMMEDIATE`; add tests showing a convenience `add_node` inside an
  active transaction fails before SQL and that the active transaction can still commit when the
  error is caught; verify with `hatch test tests/test_transaction.py tests/test_graph.py`.
- [x] 3.2 Add the transaction-guard change to `CHANGELOG.md` under `[Unreleased]`; verify the entry
  describes the new error timing and that the active transaction remains usable.

## 4. README Snippet Execution

- [x] 4.1 Add `tests/test_readme.py` that extracts fenced `python` blocks from `README.md`, runs
  each in a fresh namespace with an isolated working directory and captured stdout, and skips
  `console` blocks; verify with `hatch test tests/test_readme.py`.
- [x] 4.2 Add a short `README.md` note that the examples are executed by the test suite; verify the
  note does not break the snippet test.

## 5. TRON Fixtures and Naming Guard

- [x] 5.1 Rename graph fixtures in `tests/storage/`, `tests/test_graph.py`,
  `tests/test_transaction.py`, and `tests/test_integration.py` using the design mapping, keeping
  pure model/codec values generic where no graph is built; verify with
  `hatch test tests/storage tests/test_graph.py tests/test_transaction.py tests/test_integration.py`.
- [x] 5.2 Rename traversal fixtures in `tests/engine/` to TRON characters and places, preserving
  each fixture's diamond, cycle, parallel-edge, and self-loop shape; verify with
  `hatch test tests/engine`.
- [x] 5.3 Rename `README.md` examples to TRON names, labels, properties, and relationship types;
  verify with `hatch test tests/test_readme.py`.
- [x] 5.4 Add `tests/test_naming_convention.py` with an AST string-constant scan for the banned
  placeholder names, an exclude for the guard file, and a unit test proving the scanner detects a
  violation in a temporary file; verify with `hatch test tests/test_naming_convention.py`.
- [x] 5.5 Update `AGENTS.md` to reference the naming guard and README execution test as enforced
  conventions; verify the testing section names both mechanisms.

## 6. CI and Packaging Verification

- [x] 6.1 Add `.github/workflows/ci.yml` with a quality job that installs uv and Hatch, runs
  `hatch check`, and runs `hatch test` on Python 3.14; verify locally with `hatch check` and
  `hatch test`, then push a branch and confirm the quality job passes.
- [x] 6.2 Add a package job that runs `uv build`, installs the wheel in a clean environment, runs an
  in-memory graph smoke script, and verifies `py.typed` and `LICENSE.txt` are in the wheel; if the
  license is missing, declare `license-files = ["LICENSE.txt"]` in `pyproject.toml` and re-verify
  the package job locally with `uv build` and a clean install.
- [x] 6.3 Add `[Unreleased]` changelog and `AGENTS.md` entries for the CI quality gate, wheel smoke
  test, and README snippet test; verify the workflow file and both documents describe the same
  commands.

## 7. Final Gates

- [x] 7.1 Run `hatch check --fix` and `hatch test`; confirm lint, formatting, Pyrefly, all tests,
  and coverage of at least 80% pass.
- [x] 7.2 Run `openspec validate harden-foundation --strict` and `openspec validate --specs
  --strict`; confirm both pass.
- [x] 7.3 Review `git diff --stat` and `git status --short` for accidental changes; confirm only the
  intended source, test, documentation, workflow, and planning files are present.

## Workflow follow-up

- Review the implemented change and archive it with `/opsx-archive` after the gates pass.
- Move the `[Unreleased]` entries into the next version section when a release is cut; do not bump
  the version in this change.
