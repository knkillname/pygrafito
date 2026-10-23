# Proposal

## Why

The MVP is complete and correct, but its foundation has three gaps that will slow every future
change: graph lifecycle errors are inconsistent, convenience writes inside an explicit transaction
are a silent footgun, and CI, packaging, README examples, and the new TRON fixture convention are
not verified automatically. With thousands of elements and read-heavy traversal, regression
confidence is more valuable right now than additional graph features.

## What Changes

- Establish a clean baseline by committing the pending metadata, license, and `AGENTS.md` edits
  before implementation starts.
- Add a `GraphClosedError` domain error. Reads, writes, and traversal starts on a closed `Graph`
  raise it consistently instead of leaking `sqlite3.ProgrammingError` or a generic
  `TransactionError`.
- Guard convenience writes while an explicit transaction is active. `Graph.add_node`,
  `add_relationship`, `set_properties`, `remove_properties`, `add_labels`, `remove_labels`, and
  `delete` raise a clear `TransactionError` before issuing SQL, and the active transaction remains
  usable when the caller handles the error.
- Rename test-graph fixtures and README examples to TRON characters, programs, and places. Add a
  lightweight source-scanning guard that rejects generic placeholder fixture names in tests.
- Add a README snippet test that executes every fenced `python` block so documentation cannot drift
  from the API.
- Add a CI workflow that runs `hatch check` and `hatch test`, builds the wheel, installs it in a
  clean environment, and verifies that `py.typed` and the license file are packaged.
- Record the lifecycle and workflow changes in `CHANGELOG.md` and `AGENTS.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `property-graph`: closed-handle lifecycle errors and an active-transaction guard for convenience
  writes.

## Impact

- Affected code: `src/pygrafito/model.py`, `src/pygrafito/engine/graph.py`,
  `src/pygrafito/storage/connection.py`, `src/pygrafito/__init__.py`, the test suite, `README.md`,
  `AGENTS.md`, `CHANGELOG.md`, and a new `.github/workflows/ci.yml`.
- Public API: new `GraphClosedError`. **BREAKING** for callers that currently catch
  `sqlite3.ProgrammingError` from reads on a closed handle; writes on a closed handle change from
  `TransactionError` to `GraphClosedError`.
- Dependencies: runtime remains standard-library only. CI uses uv and Hatch; no new runtime
  dependency.
- Out of scope: query operators, adjacency API, property indexes, snapshot redesign, path
  analytics, and import/export. Those are separate changes.
