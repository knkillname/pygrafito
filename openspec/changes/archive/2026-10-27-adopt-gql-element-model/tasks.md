# Tasks

## 1. Schema and storage foundation

- [x] 1.1 Replace the version 1 schema with version 2: `nodes` and `relationships` use `INTEGER PRIMARY KEY AUTOINCREMENT`, `relationships` gains `directed INTEGER NOT NULL DEFAULT 1 CHECK (directed IN (0, 1))`, and `relationship_labels` mirrors `node_labels` with a primary key on `(relationship_id, label)`. Verify a fresh `:memory:` graph reports `PRAGMA user_version = 2` and `tests/storage/test_schema.py` passes.
- [x] 1.2 Add the structural indexes `rel_by_src (src, dst)`, `rel_by_dst (dst, src)`, and `relationship_labels_by_label (label, relationship_id)`, and remove the type-keyed indexes. Verify `tests/storage/test_schema.py` asserts the index set and `tests/storage/test_indexes.py` passes.
- [x] 1.3 Rewrite the relationship repository for label sets and direction: create with zero or more labels and a directed flag, read labels in sorted order, add and remove labels, delete, and find by all specified labels with an optional direction filter. Verify `tests/storage/test_relationships.py` covers labeled, unlabeled, multi-label, directed, undirected, self-loop, parallel-edge, and missing-endpoint cases.
- [x] 1.4 Add stable id allocation tests: delete the highest-id node and relationship, create replacements, and assert the new ids are greater than every id ever used. Verify `tests/storage/test_nodes.py`, `tests/storage/test_relationships.py`, and `tests/storage/test_deletion.py`.
- [x] 1.5 Publish views version 2: `graph_relationships` exposes `id`, `start_id`, `end_id`, `labels` as JSON, `directed`, and `properties`; `graph_meta` reports view version 2. Verify `tests/test_interop_views.py` covers fresh publication, replacement of older views on a version 2 database, read-only opens, and the undirected row shape.
- [x] 1.6 Implement snapshot version 2: relationship records carry `labels` and `directed`; export sorts relationship labels and stays byte-deterministic; restore validates the new fields, remaps endpoints, and rejects a version 1 snapshot with an error that names the supported version. Verify `tests/test_interop_format.py`, `tests/test_interop_export.py`, and `tests/test_interop_restore.py`.
- [x] 1.7 Update the storage and interop documentation for the version 2 layout, label sets, direction, and snapshot format, including `docs/guides/interop.md`, `docs/reference/snapshot-format.md`, and `docs/reference/embedding-contract.md`. Verify `hatch run docs:build` passes with no warnings.

## 2. Version 1 refusal and fresh-start checks

- [x] 2.1 Add a raw version 1 database fixture builder in `tests/storage/test_schema.py` that creates the old tables, indexes, a property index, a uniqueness constraint, multi-label nodes, and typed relationships. Verify the fixture reports `user_version = 1` and is not opened as a graph.
- [x] 2.2 Refuse a version 1 database on a read-write handle with `UnsupportedSqliteError`, leave the file byte-identical, and assert the current schema version is created only for a new or empty file. Verify `tests/storage/test_schema.py` and `tests/test_read_only.py`.
- [x] 2.3 Refuse a version 1 database on a read-only handle with `UnsupportedSqliteError` and make no change to the file. Verify `tests/test_read_only.py`.
- [x] 2.4 Refuse a version 1 JSONL snapshot with an error that names the supported version, and assert a version 2 snapshot still round-trips. Verify `tests/test_interop_restore.py` and `tests/test_interop_format.py`.
- [x] 2.5 Document the pre-1.0 break: version 1 databases and snapshots are not converted, a fresh database is required, and a user who needs an existing 0.8 file should export it with 0.8 first. Update `docs/guides/embedding.md`, `docs/reference/embedding-contract.md`, and `docs/reference/snapshot-format.md`, and verify `hatch run docs:build` passes.
- [x] 2.6 Add a maintenance check that a fresh version 2 database passes `backup_to`, `check_integrity`, reopen, and `export_jsonl`. Verify `tests/test_maintenance.py` and `tests/test_integration.py`.

## 3. Public API, model, constraints, and indexes

- [x] 3.1 Change the `Relationship` model to a frozen snapshot with `labels: tuple[str, ...]` and `directed: bool`, remove `type`, and update equality, repr, hashing, and path values. Verify `tests/test_model.py` and `tests/test_codec.py` cover the new shape.
- [x] 3.2 Change `Graph.add_relationship` to accept a label string or iterable and a keyword-only `directed` flag, and change `Graph.find_relationships` to accept labels and an optional direction filter. Verify `tests/test_graph.py` covers labeled, unlabeled, multi-label, directed, undirected, self-loop, and missing-endpoint cases.
- [x] 3.3 Generalize `Graph.add_labels` and `Graph.remove_labels` to accept `Node | Relationship | int`, returning the updated snapshot, and mirror the behavior on `Transaction`. Verify `tests/test_transaction.py` and `tests/test_graph.py` cover label addition, removal, idempotence, missing elements, and undirected relationships.
- [x] 3.4 Adapt relationship uniqueness constraints to the label scope: store the label in `scope`, enforce on edge creation, property writes, and label addition/removal, and exempt edges without the label. Verify `tests/test_constraints.py` covers multi-label edges, label acquisition, label removal, declaration over existing data, and violation reporting.
- [x] 3.5 Adapt property indexes and the planner: relationship property indexes stay key-scoped and cover edges regardless of labels or direction; label filters join `relationship_labels`; the plan for a label filter without an endpoint names the label index. Verify `tests/test_indexes.py`, `tests/test_index_transparency.py`, and `tests/test_explain.py`.
- [x] 3.6 Update the API reference and guides for the new `Relationship` shape, `add_relationship`, `find_relationships`, label mutation, label-scoped constraints, and index behavior: `docs/api/model.md`, `docs/api/graph.md`, `docs/api/admin.md`, `docs/guides/constraints.md`, `docs/guides/indexes.md`, and `docs/reference/index-behavior.md`. Verify `hatch run docs:build` passes.
- [x] 3.7 Update the landing and quickstart examples in `README.md`, `docs/index.md`, and `docs/getting-started/quickstart.md` to the new relationship shape, and verify `tests/test_readme.py` and `tests/test_docs_examples.py` pass.

## 4. Traversal, transitional query dialect, shell, and import

- [x] 4.1 Update traversal for undirected edges and label filters: outgoing and incoming include incident undirected edges, both follows every incident edge, label sets match any listed label, and relationship-unique paths and shortest paths handle undirected edges without reusing them. Verify `tests/test_traversal_reads.py`, `tests/engine/test_reachability.py`, `tests/engine/test_neighborhood.py`, and `tests/engine/test_paths.py`.
- [x] 4.2 Update the transitional query dialect's relationship patterns: `:LABEL` filters by label, `-->` and `<--` match directed edges only, `--` matches every incident edge including undirected, and a bound relationship exposes `labels` and `directed`. Verify `tests/test_query_integration.py` covers each direction form, label alternatives, and bound label metadata.
- [x] 4.3 Update variable-length patterns for label filters and undirected edges: every hop applies labels and direction, `--` can traverse undirected edges, `-->` cannot, and an undirected edge is not reused within one path. Verify `tests/test_query_integration.py`.
- [x] 4.4 Update `SET` and `REMOVE` to accept relationship labels and reject labels on non-elements, and update the semantic and mutation paths accordingly. Verify `tests/test_query_integration.py` covers relationship label addition, removal, and the non-element rejection.
- [x] 4.5 Update `type` and `labels` functions: `type(r)` returns the first sorted label or null for an unlabeled relationship, and `labels(r)` returns every label. Verify `tests/test_query_integration.py` covers labeled and unlabeled relationship values.
- [x] 4.6 Update `CREATE` to carry the single label named in the pattern, allow an unlabeled relationship, and keep created edges directed. Verify `tests/test_query_integration.py`.
- [x] 4.7 Update shell introspection and rendering: `.schema` reports labels and direction counts, `.reltypes` reports labels, `.rel` and `.node` show labels and direction, `.expand` and `.path` follow undirected edges, and JSON/table/line render the new relationship shape. Verify `tests/cli/test_commands.py`, `tests/cli/test_session.py`, and `tests/cli/test_formatting.py`.
- [x] 4.8 Keep the statement-driven importer on single-label directed edges for this change and add a test that documents the limitation; verify `tests/test_import_integration.py` and `tests/engine/test_importing.py`.
- [x] 4.9 Update the querying guide, query-language reference, shell guide, CLI reference, and API query page for labels, direction, `type`/`labels`, `SET`/`REMOVE`, and the transitional direction rules: `docs/guides/querying.md`, `docs/guides/shell.md`, `docs/reference/query-language.md`, `docs/reference/cli.md`, and `docs/api/query.md`. Verify `hatch run docs:build` passes.

## 5. Integration, performance, and release

- [x] 5.1 Add an end-to-end test that a version 1 database is refused, a fresh version 2 graph supports labels and direction, a version 1 snapshot is refused, a version 2 snapshot round-trips, and read-only handles, backup, and integrity checks work. Verify `tests/test_integration.py`, `tests/storage/test_schema.py`, and `tests/test_interop_integration.py`.
- [x] 5.2 Update `benchmarks/run.py` to create labeled relationships and query label and direction filters, run the benchmark on the documented dataset, and refresh the numbers and notes in `docs/reference/performance.md`. Verify the benchmark command completes and the performance page has no stale type-based claims.
- [x] 5.3 Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; confirm the suite passes, coverage stays at least 80%, and the docs build has no warnings.
- [x] 5.4 Add the breaking-change entry to `CHANGELOG.md` under `## [Unreleased]`, covering label sets, direction, stable ids, the version 1 refusal (no migration), snapshot v2, views v2, the API change, and the transitional query dialect. Verify the entry names every removed or changed public behavior.
- [x] 5.5 Run the full test suite one final time after the changelog and docs edits, and verify `git diff --check` reports no whitespace errors.

## Workflow follow-up

- Update the `property-graph` and `graph-indexes` capability Purpose lines in `openspec/specs/` when the change is archived, because they still describe a single directed relationship type.
- Archive the change after the project's review requirements are satisfied.
