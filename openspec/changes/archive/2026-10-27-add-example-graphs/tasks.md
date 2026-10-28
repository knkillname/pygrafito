# Tasks

## 1. Foundation and curated data

- [x] 1.1 Create the `examples/` package tree with `__init__.py`, `README.md`, `data/`, `support/`, `tours/`, `analysis/`, `algorithms/`, and `extract/`, each Python file carrying the SPDX header. Verify `python -c "import examples"` succeeds and `hatch check` reports no new violations.
- [x] 1.2 Implement dataset loading and validation in `examples/support/dataset.py`: stable string handles, duplicate-handle rejection, unknown-endpoint rejection, typed property checks, label handling, and conflict detection when merging datasets. Verify `tests/test_examples.py` covers duplicate handles, missing endpoints, invalid values, and merge conflicts.
- [x] 1.3 Author `examples/data/grid.json` as the curated franchise graph across `tron-1981`, `legacy-2010`, and `ares-2025`, including film provenance, users, programs, organizations, places, vehicles, objects, multi-label nodes, undirected alliances, and lineage edges. Verify the in-memory build reports the expected node and relationship counts and preserves the declared label sets and directions.
- [x] 1.4 Author `examples/data/cast.json` and `examples/data/places.json` as aggregate datasets with weights and `basis` metadata, using handles that exist in `grid.json`. Verify merging them with `grid` creates no conflicting nodes and that a deliberate property conflict is rejected.

## 2. Builder, snapshots, and sample-graph documentation

- [x] 2.1 Implement `examples/build.py` and `examples/__main__.py`: `python -m examples` lists the catalog, `python -m examples build <dataset>` builds `grid`, `cast`, `places`, `all`, or `synthetic`, and `--output`, `--format db|jsonl`, `--nodes`, `--relationships`, and `--seed` are accepted. Creation runs in one transaction and validation completes before mutation. Verify `tests/test_examples.py` covers listing, each dataset name, both output formats, and invalid arguments.
- [x] 2.2 Implement deterministic output ordering, optional index and uniqueness-constraint creation for database output, and the documented difference between a database and a snapshot. Verify two builds in separate processes produce byte-identical snapshots and that a database opens with the expected counts.
- [x] 2.3 Generate and commit `examples/data/grid.jsonl`; add a drift test that rebuilds the dataset and compares it byte-for-byte with the committed snapshot, plus a restore round-trip test. Verify both tests pass.
- [x] 2.4 Write `examples/README.md` with the audience matrix, dataset catalog, build commands, provenance and no-screenplay-text policy, and the catalog discipline for adding examples. Verify every documented command runs from the repository root.
- [x] 2.5 Add `docs/guides/examples.md` describing the sample datasets, build commands, and lanes, add it to the guide toctree in `docs/index.md`, and link it from `README.md` and the quickstart. Run `hatch run docs:build` and fix every warning.
- [x] 2.6 Refresh the teaching examples in `docs/guides/querying.md`, `indexes.md`, `constraints.md`, and `interop.md` with names from the roster while keeping each Python fence self-contained and runnable. Verify `hatch test tests/test_docs_examples.py tests/test_readme.py` and `hatch run docs:build` pass.

## 3. GQL tours

- [x] 3.1 Add `examples/tours/01-match.gql`, `02-write.gql`, `03-compose.gql`, and `04-paths.gql` using only current-release syntax: `//` comments, `-->`/`<--`/`--` directions, legacy `*n..m` quantifiers, `CREATE`, `UNWIND`, `WITH`, and `MERGE`. Verify each tour runs to completion through the in-process shell harness against the built `grid` database.
- [x] 3.2 Add `examples/tours/README.md` cataloguing each tour with its GQL profile tier, profile section, constructs used, and migrating change. Include a test that every `.gql` file has a catalog entry and that extension constructs are labelled as extensions.
- [x] 3.3 Add a guard test that rejects target-only syntax in tours (`INSERT`, `FILTER`, `FOR`, `LET`, `NEXT`, `GROUP BY`, anonymous single-dash `->`, `~`, `{n,m}`, and `--` comments), so a tour cannot silently move ahead of the current release. Typed relationship arrows such as `-[r]->` are current syntax and remain allowed.
- [x] 3.4 Extend `docs/guides/examples.md` with the tour catalog and migration note, and update `docs/guides/shell.md` to seed `grid.db` from the example builder and run a tour. Verify `hatch run docs:build` passes.

## 4. Analysis lane

- [x] 4.1 Add `examples/analysis/rank_by_degree.py` ranking programs by weighted degree over `cast`, with a class entry point and zero-argument default. Verify its test asserts the top result and the row count.
- [x] 4.2 Add `examples/analysis/aggregate_by_source.py` grouping entities by source and label. Verify the test asserts per-source counts against the curated dataset.
- [x] 4.3 Add `examples/analysis/import_csv.py` with a small CSV fixture, importing typed rows through `Graph.import_file`. Verify the test checks integer conversion and the import summary.
- [x] 4.4 Add `examples/analysis/sql_views.py` reading `graph_nodes` and `graph_relationships` through stdlib `sqlite3`. Verify the test asserts the view rows and that no write is attempted.
- [x] 4.5 Add `examples/analysis/export_report.py` writing a CSV report and a JSONL snapshot to a caller-supplied directory. Verify the test reads both outputs back and checks their contents.
- [x] 4.6 Document the analysis lane in `docs/guides/examples.md` with copyable console commands and no repo-only Python imports. Verify `hatch test tests/test_docs_examples.py` and `hatch run docs:build` pass.

## 5. Algorithms lane

- [x] 5.1 Add `examples/algorithms/reachability.py` comparing `traverse()` with `shortest_path()` on the places network. Verify the test asserts depths and the chosen route.
- [x] 5.2 Add `examples/algorithms/trails_vs_walks.py` showing relationship-unique trails on a directed cycle and stating that `WALK` is the target default gated by the profile. Verify the test asserts the trail count and that the module does not claim `WALK` is implemented.
- [x] 5.3 Add `examples/algorithms/shortest_path.py` and `examples/algorithms/direction.py` covering bidirectional BFS, undirected edges, and the direction forms. Verify the tests assert path length, path shape, and direction-sensitive reachability.
- [x] 5.4 Add `examples/algorithms/scaling.py` timing traversal over increasing synthetic sizes with a `--seed` and `--nodes` arguments. Verify the test runs a small size and checks the reported counts.
- [x] 5.5 Document the algorithms lane in `docs/guides/examples.md`, including the trail-versus-WALK note and the profile link. Verify `hatch run docs:build` passes.

## 6. Synthetic fixture and benchmarks

- [x] 6.1 Move the benchmark `Dataset` into `examples/support/dataset.py` as `Synthetic`, keep the current topology and counts, and replace generated designations and regions with roster vocabulary and element-model label sets. Verify determinism and requested counts in `tests/test_examples.py`.
- [x] 6.2 Add `benchmarks/__init__.py`, make `benchmarks/run.py` import `Synthetic`, and invoke it as `python -m benchmarks.run`. Verify a small smoke run completes and a test asserts the benchmark imports the shared generator.
- [x] 6.3 Update `docs/reference/performance.md` with the module invocation, the themed dataset description, and the shared-fixture note. Verify `hatch run python -m benchmarks.run --nodes 1000 --relationships 3000` completes and `hatch run docs:build` passes.

## 7. Local-only extraction

- [x] 7.1 Add `examples/extract/` with screenplay, plain-transcript, and PDF-transcript adapters that accept a caller-supplied path and emit only aggregate JSON in the `cast`/`places` shape: handles, weights, counts, and `basis`. No dialogue or action text in the output.
- [x] 7.2 Add an invented mini-screenplay fixture and tests covering scene headings, cues, dialogue turns, blocks, and missing-file errors. Verify the extractor tests pass without any real script present.
- [x] 7.3 Document the extraction workflow, its per-source fidelity, and the `pdftotext` development-only requirement in `examples/README.md` and `docs/guides/examples.md`. Verify `hatch run docs:build` passes and no source script is tracked.

## 8. Integration and release checks

- [x] 8.1 Add `examples` to Ruff `src` and Pyrefly `project-includes`, and confirm coverage still measures only `pygrafito`. Verify `hatch check --fix` passes.
- [x] 8.2 Add a packaging assertion that the built wheel does not contain `examples/` or any screenplay/transcript source. Verify `tests/test_package.py` passes.
- [x] 8.3 Add an `Unreleased` `Added` entry to `CHANGELOG.md` describing the example layer, datasets, lanes, tours, and shared benchmark fixture.
- [x] 8.4 Run `hatch test` and confirm coverage stays at or above 80%, `hatch run docs:build` completes with no warnings, and `git diff --check` reports no whitespace errors.
- [x] 8.5 Manually run the documented front door (`python -m examples`, `build grid`, a tour, an analysis example, and an algorithm example) from a clean shell and verify the outputs match the documentation.

## Workflow follow-up

- Archive the change after review, and update the `graph-examples` purpose line if curation changes the dataset scope.
- If a later GQL change adds or changes a query construct, update `docs/reference/gql-profile.md`, its conformance matrix, and the conformance corpus before migrating the affected tour.
