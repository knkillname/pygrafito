# Proposal

## Why

The portability nightlies fail on macOS and Windows for Python 3.13 and 3.14. The same
finite floats fail in every run, and the failure reproduces with SQLite 3.50.4, whose
JSON number parser rounds those literals to a neighboring binary value. Property equality
still compares SQLite's re-parsed float, so a node that stores
`2.7710821668887726e-173` is no longer found by `find_nodes`, by a GQL `WHERE`
predicate, or by a uniqueness check that uses the same value. Local runs pass because
SQLite 3.45.1 and 3.53.4 parse those literals correctly.

The Windows run also exposes platform-specific gaps: shell commands lose backslashes in
native paths, CSV embedded newlines depend on how the file was written, crash-recovery
subprocess tests misreport Windows lock or recovery errors as missing JSON1, the SQL
view example uses a URI that is not portable, and tests for POSIX-only developer
scripts try to execute shell files directly.

## What Changes

- Match real property values by the exact canonical JSON number text already stored in
  the database, not by the float that SQLite reconstructs from it.
- Apply the exact match to node and relationship property filters, GQL numeric equality
  and `IN`, and uniqueness-constraint checks and triggers.
- Preserve GQL's integer/float numeric family by matching the canonical text of every
  equivalent numeric representation, and keep integer, boolean, string, and list
  equality on the existing indexed SQL path.
- Make shell dot-command argument parsing preserve native Windows paths, including
  backslashes and drive letters, for import, export, restore, and backup commands.
- Keep redirected shell output and CSV embedded newlines deterministic across platforms.
- Distinguish missing JSON1 support from transient Windows lock or recovery failures and
  make crash-recovery tests wait for process and file state to settle.
- Make the SQL view documentation example use a read-only connection form that works on
  Windows as well as Linux and macOS.
- Run or skip POSIX-only developer tooling tests appropriately on Windows, and document
  which local scripts require a POSIX shell.
- Add deterministic regression coverage for every failing Windows group and document the
  behavior where it is user-visible.

Out of scope: arithmetic, ordering (`<`, `<=`, `>`, `>=`), storage format changes, and
changes to external readers' use of `json_extract`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `property-graph`: Strict property values and type-sensitive filters must find a real
  value by its exact stored value even when the SQLite JSON parser rounds it.
- `graph-query-language`: Numeric equality and membership must compare the stored real
  value exactly while preserving integer/float numeric-family semantics.
- `graph-constraints`: Type-sensitive uniqueness must treat two equal real values as
  duplicates even when the SQLite JSON parser rounds them.
- `graph-indexes`: Index transparency must hold for real values on affected SQLite
  versions: declaring an index must not change whether the stored value matches.
- `graph-shell`: Native Windows path arguments must survive dot-command parsing, and
  redirected output must use consistent newlines across platforms.
- `graph-import`: Embedded CSV newlines must be preserved independently of the host
  platform's text-mode newline translation.
- `platform-support`: The nightly portability signal must state which Windows failures
  apply to the library and how POSIX-only developer tooling is handled.

## Impact

- `src/pygrafito/storage/codec.py`: exact equality expression and bind value.
- `src/pygrafito/storage/nodes.py` and `relationships.py`: property filter predicates.
- `src/pygrafito/engine/query/compiler.py`: GQL equality and membership predicates.
- `src/pygrafito/storage/constraints.py`: holder lookup, conflict scan, and triggers.
- `src/pygrafito/cli/commands.py`, `session.py`, and `reader.py`: Windows path parsing
  and deterministic text output.
- `src/pygrafito/engine/importing.py` and `src/pygrafito/storage/schema.py`: newline
  handling and JSON1 error classification.
- Tests under `tests/cli`, `tests/engine/query`, `tests/storage`, `tests/`, and
  `tests/conformance`, including fixed values and Windows-specific regressions.
- Sphinx documentation for property filters, uniqueness constraints, index behavior,
  shell commands, imports, SQL views, and local verification scripts.
- `.github/workflows/nightly.yml` only if the Windows signal needs an explicit
  POSIX-tooling exclusion.
- `CHANGELOG.md` under `[Unreleased]`.
