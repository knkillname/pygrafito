# Tasks

## 1. Open, bootstrap, and the file

- [x] 1.1 Retry the journal-mode switch in `Database._configure` with a small bounded backoff, and verify with a multiprocess test that several processes opening one fresh file do not fail with `database is locked`
- [x] 1.2 Read back the mode the pragma obtained, expose it as `Graph.journal_mode`, and verify an in-memory graph reports the memory mode while a file graph reports the write-ahead mode
- [x] 1.3 Move bootstrap DDL and the version write into one `BEGIN IMMEDIATE` transaction that re-reads the version inside it, skipping the transaction on a read-only handle, and verify the existing schema tests and a new version-race test pass
- [x] 1.4 Refuse an existing SQLite file that records no graph layout and holds unrelated tables on both open paths, leaving it untouched, and verify a test shows the foreign tables and version survive while a fresh file, an empty file, and a graph file with an added table still open
- [x] 1.5 Document open, journal mode, and the refusal rule in `docs/embedding.md`, and add the `Unreleased` changelog entries for this group

## 2. Handles, threads, and lock waits

- [x] 2.1 Add `HandleAffinityError` and check the owning thread in the shared entry points including `Transaction`, and verify by updating `tests/test_graph.py::test_cross_thread_use_rejected` to expect it plus a transaction case
- [x] 2.2 Add `LockTimeoutError`, raised when a write-lock wait exhausts the busy timeout at open and at `Transaction.begin`, and verify with two handles where the first holds a write transaction and the second times out
- [x] 2.3 Add the keyword-only `busy_timeout` to `Graph.open` and thread it to `Database`, and verify a short timeout fails faster while the default still waits for a quick commit
- [x] 2.4 Document the two errors and the timeout knob in `docs/embedding.md`, and add the changelog entries for this group

## 3. Read snapshots

- [x] 3.1 Add a read-snapshot helper that starts a deferred transaction unless one is active, use it for `node`, `find_nodes`, and `find_relationships`, and verify a read inside an explicit transaction still sees its own writes
- [x] 3.2 Use the helper for the `traverse` and `paths` capture and for the `shortest_path` evaluation so that no transaction outlives a returned iterator, and verify reads still work after an iterator is abandoned
- [x] 3.3 Verify consistency with a multiprocess test where a writer alternates a node between two label/property states in single transactions and a reader asserts it never observes a mixed state
- [x] 3.4 Document snapshot semantics in `docs/embedding.md` and add the changelog entry for this group

## 4. Constraint model and declaration

- [x] 4.1 Add `ElementKind` with `IndexKind` kept as an alias, add `Constraint`, and export both, verifying with model tests for validation and ordering
- [x] 4.2 Add a constraint registry that encodes and decodes object names, renders the unique-index and trigger DDL, lists constraints from `sqlite_master`, creates them with validation inside one write transaction, and drops them, verifying declare-twice, remove-missing, and a reopen round trip
- [x] 4.3 Add `Graph.create_node_uniqueness_constraint`, `Graph.create_relationship_uniqueness_constraint`, `Graph.constraints`, and `Graph.drop_constraint` with the transaction and read-only guards, verifying each with graph tests
- [x] 4.4 Document constraints in `docs/constraints.md`, note in `docs/indexes.md` that constraint objects are not reported by `indexes()`, add a runnable README example, and add the changelog entries for this group

## 5. Enforcement and violation reporting

- [x] 5.1 Add `ConstraintViolationError` and a conservative translator for both SQLite shapes with the diagnostic lookup that fills `existing`, verifying that a foreign-key failure is not translated and that an intra-statement duplicate leaves `existing` empty
- [x] 5.2 Wire the translator into node creation, label changes, property writes, relationship creation, statement execution, and import batches, verifying one test per path including a `MERGE` that matches instead of failing and a delete-then-recreate
- [x] 5.3 Verify type-sensitive enforcement, scope exemption, immediate enforcement inside a transaction, and declaration over conflicting data with the scenarios in `specs/graph-constraints/spec.md`
- [x] 5.4 Add `.constraints` to the shell and report constraints and the journal mode in `.schema`, verifying with CLI tests and `docs/cli.md`

## 6. Integration

- [x] 6.1 Verify the whole concurrency contract with one multiprocess test file: concurrent first open, a reader in a second process observing commits, writers taking turns, and a read-only reader during a commit, skipping the last case when the reported journal mode is not the write-ahead mode
- [x] 6.2 Run `hatch check --fix` and `hatch test`, confirm coverage is at least 80%, and fix everything they report

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived result.
