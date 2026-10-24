# Tasks

## 1. Escaped literal property paths

- [x] 1.1 Add one helper that renders a property key as an embeddable SQL literal: build the quoted JSON path and escape single quotes for the statement; verify with a unit test covering single quote, double quote, backslash, dot, space, Unicode, NUL, and an empty key rejected by validation.
- [x] 1.2 Switch the query compiler's predicate builders (`equality`, `comparison`, `string_predicate`, `is_null`) to the helper; verify existing query tests pass and a compiled-shape test asserts the emitted SQL carries a literal path and no path parameter.
- [x] 1.3 Switch `NodeRepository.find` and `RelationshipRepository.find` to the same helper; verify storage lookup tests pass and a predicate-shape test asserts literal paths for both element kinds.
- [x] 1.4 Add injection-safety tests for SQL-shaped keys through both the query API and the lookup API; verify the key is matched literally and no additional statement executes.

## 2. Index model and discovery

- [x] 2.1 Add the `IndexKind` enum and the frozen `Index` value type, and export both from the package; verify model tests and `tests/test_package.py` cover the new names.
- [x] 2.2 Add reversible index-name encoding (prefix, element kind, hex of the UTF-8 key) and discovery over `PRAGMA index_list`; verify round-trip tests for punctuation and Unicode keys and a discovery test that ignores indexes without the library prefix.
- [x] 2.3 Add the structural relationship-type index to schema bootstrap; verify a plan test shows an index search for a type filter with no bound endpoint and an existing-file reopen test stays green.

## 3. Index lifecycle, maintenance, and transparency

- [x] 3.1 Implement `Graph.create_node_index`, `Graph.create_relationship_index`, `Graph.drop_index`, and `Graph.indexes`, including idempotent creation, not-found removal, and `TransactionError` while an explicit transaction is active; verify with lifecycle tests for both element kinds.
- [x] 3.2 Refresh statistics with `ANALYZE` after create or drop and run `PRAGMA optimize` when a file-backed graph closes, both best-effort; verify that statistics are present after declaration, that close does not raise, and that results are unchanged.
- [x] 3.3 Add index-maintenance tests for property update, null removal, element deletion, rolled-back transaction, reopen, and in-memory graphs; verify each against the declared index.
- [x] 3.4 Add transparency tests asserting identical rows and ordering with and without an index for equality, type distinction, list order, and range filters; verify against the existing fixtures.
- [x] 3.5 Document the index API, the trade-off of explicit declarations, and the key-scoped model in `docs/indexes.md`, link it from the README, and add a runnable README example; verify with `hatch test tests/test_readme.py`.
- [x] 3.6 Add an `[Unreleased]` entry covering the index API, relationship-type index, plan inspection, and the literal-path change in `CHANGELOG.md`; verify the entry renders under the correct Keep a Changelog category.

## 4. Plan inspection

- [x] 4.1 Implement `Graph.explain` by parsing, analyzing, and compiling the statement and returning the plan detail rows without executing it; verify that a write statement inspected through it changes no data.
- [x] 4.2 Add plan tests for an indexed property filter, an unindexed property filter, a relationship-type filter, and an invalid statement; verify the expected index request or table scan and the query error respectively.
- [x] 4.3 Document `explain` in `docs/indexes.md` and the README index section, and run the documented snippet; verify with `hatch test tests/test_readme.py`.

## 5. Performance evidence

- [x] 5.1 Add a runnable benchmark harness in `benchmarks/` using themed synthetic data and scenarios for equality, range, type filter, node lookup, insert throughput, and update throughput, with and without declared indexes; verify with a tiny smoke test plus one manual run.
- [x] 5.2 Record the measured baseline and post-change numbers in `docs/performance.md` with machine, dataset sizes, and method; verify the recorded figures match a fresh harness run.
- [x] 5.3 Link `docs/performance.md` from the README and state what the numbers mean and what they do not promise; verify the documented commands run as written.

## 6. Integration checks

- [x] 6.1 Run `hatch check --fix` and confirm Ruff and Pyrefly report no issues.
- [x] 6.2 Run `hatch test` and confirm the full suite passes with coverage at or above 80%.

## Workflow follow-up

- Archive the change after review requirements are satisfied.
