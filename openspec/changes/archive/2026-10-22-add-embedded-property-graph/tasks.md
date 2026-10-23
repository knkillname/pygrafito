# Tasks

## 1. Project Setup and Quality Gates

- [x] 1.1 Update `pyproject.toml` to require Python 3.14, trim classifiers, keep runtime dependencies empty, and add Ruff, mypy strict, pytest, and coverage configuration; verify with `hatch project metadata` and a TOML parse that the project metadata is valid.
- [x] 1.2 Create the package skeleton (`model.py`, `storage/`, `engine/`, public `__init__.py`) and a smoke test that imports the package; verify `hatch check --fix` and `hatch test` both complete without errors.

## 2. Domain Model and Property Codec

- [x] 2.1 Implement `model.py` with `Direction`, `Node`, `Relationship`, `Path`, `TraversalStep`, `Value`/`Scalar` aliases, and the `PygrafitoError` hierarchy; add unit tests for mapping access, frozen snapshots, path length/endpoints, and error inheritance, and verify they pass with `hatch test tests/test_model.py`.
- [x] 2.2 Implement `PropertyCodec` with strict validation, canonical JSON encoding/decoding, `None` removal, and quoted JSON path construction; add tests covering accepted scalars, homogeneous lists, maps, nested lists, non-finite floats, 64-bit bounds, dotted/spaced/quoted keys, and canonical list equality, and verify they pass with `hatch test tests/test_codec.py`.

## 3. Storage Layer

- [x] 3.1 Implement `storage/connection.py` and `storage/schema.py` with pragmas, single-connection setup, idempotent schema bootstrap, `PRAGMA user_version`, and the JSON1 compatibility check; add tests for pragma values, repeat bootstrap, version reporting, and unsupported-runtime errors, and verify with `hatch test tests/storage/test_schema.py`.
- [x] 3.2 Implement `NodeRepository` with create, get, label add/remove, property set/remove, and equality lookups; add tests for multiple labels, arbitrary property keys, type-sensitive lookups, list-order-sensitive lookups, snapshot immutability, and missing nodes, and verify they pass.
- [x] 3.3 Implement `RelationshipRepository` with create, get, property set/remove, and type/property lookups; add tests for missing endpoints, self-loops, stored direction, and type-sensitive lookups, and verify they pass.
- [x] 3.4 Implement deletion rules in the repositories: direct relationship deletion, refusal for connected nodes, and detach deletion of incident relationships; add tests for each path and verify with `hatch test tests/storage`.

## 4. Graph Facade and Transactions

- [x] 4.1 Implement `Transaction` as a context manager with `BEGIN IMMEDIATE`, commit on success, and rollback on failure; add tests for committed writes, rolled-back writes, and transaction reuse errors, and verify with `hatch test tests/test_transaction.py`.
- [x] 4.2 Implement `Graph.open`/`close`, the context manager, convenience writes, reads, and delegation to `Transaction`; add tests for file reopen, in-memory operation, cross-thread rejection, atomic convenience writes, and detach delete, and verify they pass.
- [x] 4.3 Document persistence, CRUD, and transaction usage in `README.md` with a runnable example; verify the documented snippet runs as written against a temporary database.

## 5. Traversal Engine

- [x] 5.1 Implement the adjacency snapshot and `ReachabilityEvaluator`, then wire `Graph.traverse`; add tests for diamonds, cycles, depth bounds, direction modes, type filters, and start exclusion, and verify with `hatch test tests/engine/test_reachability.py`.
- [x] 5.2 Implement `ShortestPathEvaluator` with bidirectional BFS and wire `Graph.shortest_path`; add tests for shortest routes, unreachable pairs, same-node zero-length paths, incoming direction, and maximum depth, and verify with `hatch test tests/engine/test_shortest_path.py`.
- [x] 5.3 Implement `TrailEnumerator` with per-path relationship uniqueness, depth bounds, backward-distance pruning, lazy generation, and result limits, then wire `Graph.paths`; add tests for two-route diamonds, repeated nodes, relationship reuse rejection, parallel relationships, self-loops, depth ranges, limits, and early stopping, and verify with `hatch test tests/engine/test_paths.py`.
- [x] 5.4 Add traversal input-validation and snapshot-consistency tests for negative depths, inverted depth ranges, missing nodes, and writes made during iteration; verify with `hatch test tests/engine`.
- [x] 5.5 Document traversal usage, direction/type filters, depth bounds, and the exponential cost of path enumeration in `README.md`; verify the documented examples run as written.

## 6. Integration and Final Gates

- [x] 6.1 Add cross-cutting integration tests that combine persistence, transactions, detach deletion, equality lookup, and traversal on one graph; verify with `hatch test tests/test_integration.py`.
- [x] 6.2 Enable the coverage threshold (`fail_under = 80`) and run `hatch check --fix` followed by `hatch test`; fix all lint, type, and test failures until the suite passes with at least 80% coverage.

## Workflow follow-up

- Run `openspec validate add-embedded-property-graph --strict` and resolve any artifact issues before archiving.
- Archive the change after the implementation and review are complete.
- Verify the archived specs describe the shipped behavior.
