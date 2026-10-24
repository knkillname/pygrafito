# Tasks

## 1. Snapshot format primitives

- [x] 1.1 Add `InteropSummary` and the snapshot header and record value types to
  `engine/interop.py`, export `InteropSummary` from the package, and verify the new import and
  `__all__` entry with `hatch test tests/test_package.py`.
- [x] 1.2 Implement strict header decoding and encoding with the format name, version, and
  non-negative counts; verify unit tests reject a missing header, an unknown version, unknown
  fields, and invalid counts.
- [x] 1.3 Implement node and relationship record decoding with exact field sets, positive ids,
  label arrays, relationship endpoints, and duplicate-key rejection; verify unit tests for
  unknown fields, missing fields, and duplicate keys.
- [x] 1.4 Validate labels, relationship types, property keys, and property values through
  `PropertyCodec`, including nulls, nested maps and lists, non-finite numbers, and 64-bit
  overflow; verify the strict value-matrix tests.
- [x] 1.5 Implement canonical record encoding with ordered nodes and relationships, sorted
  labels, canonical properties, compact JSON, and a trailing newline; verify golden output and
  byte-for-byte determinism tests.
- [x] 1.6 Write the format contract in `docs/interop.md` and add the `CHANGELOG.md` entry for the
  snapshot format; verify the documented grammar and examples match the golden files.

## 2. Export

- [x] 2.1 Implement the read-snapshot exporter with counts, streamed nodes and labels, and
  streamed relationships; verify a golden snapshot for a TRON graph covering typed values,
  multiple labels, parallel relationships, a self-loop, an unlabeled node, and an empty graph.
- [x] 2.2 Add `Graph.export_jsonl(path, *, overwrite=False)` with closed-handle and
  active-transaction preconditions, read-only support, and an `InteropSummary` return; verify the
  API, read-only, and active-transaction tests.
- [x] 2.3 Add the destination guards and atomic publication: refuse an existing destination
  unless overwrite is requested, refuse the live database path and its sidecars, and write
  through a sibling temporary file; verify the guard, overwrite, and failed-write tests.
- [x] 2.4 Document export in `docs/interop.md`, add a runnable README example, and add the
  `CHANGELOG.md` entry; verify with `hatch test tests/test_readme.py`.

## 3. Restore

- [x] 3.1 Add `Graph.restore_jsonl(path, *, replace=False)` with writable, closed-handle, and
  active-transaction preconditions and header-first parsing; verify the refusal tests prove the
  file is not read and nothing is written.
- [x] 3.2 Implement loading into an empty target with node-id remapping, relationship endpoint
  resolution, and header-count verification at EOF; verify round-trip, unknown-endpoint,
  duplicate-node-id, and count-mismatch tests.
- [x] 3.3 Implement atomic replace by deleting relationships and nodes and restoring in one
  `BEGIN IMMEDIATE` transaction; verify replace success, replace rollback, and constraint
  enforcement tests.
- [x] 3.4 Add line-numbered failure notes and whole-transaction rollback for malformed,
  truncated, and phase-violating files; verify the no-partial-graph and error-context tests.
- [x] 3.5 Document restore, `replace`, id remapping, and atomicity in `docs/interop.md`, extend
  the README example to an export/restore round-trip, and add the `CHANGELOG.md` entry; verify
  with `hatch test tests/test_readme.py`.

## 4. Read-only views

- [x] 4.1 Add `storage/views.py` with `graph_nodes`, `graph_node_labels`, `graph_relationships`,
  and `graph_meta`; verify column names and types with `PRAGMA table_info` and direct reads on a
  fresh writable graph.
- [x] 4.2 Implement `Views.ensure` publication on write-capable open, including creating missing
  views, replacing older versions, leaving newer versions untouched, and refusing table or
  unidentified-view collisions; verify the publication, drift, and collision tests.
- [x] 4.3 Implement read-only tolerance and `Graph.view_version`; verify that a pre-view
  database opens read-only, reports version `0`, keeps working, and is published by the next
  writable open.
- [x] 4.4 Verify the external-reader contract through a separate read-only `sqlite3` connection:
  label JSON, canonical properties, `graph_meta`, refused updates and deletes, and graph reads
  and export with the views dropped.
- [x] 4.5 Document the view schema, version, publication rule, and external-reader JSON rules in
  `docs/interop.md`, link it from `docs/embedding.md`, and add the `CHANGELOG.md` entry; verify
  the documented SQL examples against a test database.

## 5. Shell commands

- [x] 5.1 Implement `.export PATH [--format jsonl] [--overwrite]` with argument parsing, usage
  messages, destination guards, and a count summary; verify success, explicit format, existing
  path, overwrite, live-database-path, read-only, and active-transaction command tests.
- [x] 5.2 Implement `.restore PATH [--replace]` with argument parsing, usage messages,
  preconditions, and a count summary; verify empty-target, non-empty refusal, replace, replace
  failure, read-only, and active-transaction command tests.
- [x] 5.3 Add `.help` descriptions and usage-error handling for missing paths, unsupported
  options, unsupported formats, and quoted paths; verify the usage and error-isolation tests.
- [x] 5.4 Update `docs/cli.md` and add the `CHANGELOG.md` entry for the shell commands; verify
  the documented commands with a shell test.

## 6. Integration and release checks

- [x] 6.1 Add an end-to-end test that builds a TRON graph, exports it from a read-only handle,
  restores it into a fresh file, opens a separate read-only SQLite connection, and queries all
  four views; verify the test passes.
- [x] 6.2 Add a shell round-trip test that runs `.export` and then `.restore --replace` in one
  session and queries a view; verify the test passes.
- [x] 6.3 Run `openspec validate add-data-interop --strict`, `hatch check --fix`, and
  `hatch test`; verify every command passes and the coverage gate remains at or above 80%.
- [x] 6.4 Review `README.md`, `docs/interop.md`, `docs/cli.md`, and `CHANGELOG.md` for the new
  surfaces; verify `tests/test_readme.py` and `tests/test_naming_convention.py` pass.

## Workflow follow-up

- Archive `add-data-interop` after review and the project's archive checks pass.
- Verify the archived specs with `openspec validate --specs --strict`.
