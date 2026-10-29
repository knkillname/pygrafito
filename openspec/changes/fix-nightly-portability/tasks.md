# Tasks

## 1. Exact equality primitives

- [x] 1.1 Add codec helpers that render the exact stored JSON text for a portable key, produce the matching bind values for reals (including `-0.0`/`0.0`), and keep the scalar fallback for keys that need a `json_each` scan; verify unit coverage in `tests/test_codec.py` passes.
- [x] 1.2 Add codec helpers that list every canonical numeric representation a GQL numeric constant matches (`36` with `36.0`, both signed zeros) and decode a reported conflict value from exact text; verify the new codec tests pass.
- [x] 1.3 Add a deterministic regression fixture using `2.7710821668887726e-173`, `3.277095539246836e-284`, `1.6287812207021506e-109`, and their `math.nextafter` neighbors; verify the codec tests distinguish the neighbors.

## 2. Storage property filters and indexing

- [x] 2.1 Match real values through the exact stored text in node and relationship filters while keeping the existing scalar path for booleans, integers, strings, and lists; verify `hatch test tests/storage tests/engine/query/test_predicate_properties.py` passes.
- [x] 2.2 Verify indexed and unindexed real filters return identical elements before and after index declaration, including the regression values and neighboring floats; add the assertions to `tests/test_index_transparency.py`.
- [x] 2.3 Add a test that integer, boolean, string, and list equality still uses the declared index and returns only the exact stored type; verify it in `tests/test_indexes.py` or `tests/test_explain.py`.
- [x] 2.4 Update `docs/guides/querying.md` and `docs/reference/index-behavior.md` to explain exact real equality and that real equality can scan when no exact-text index exists; verify the text matches the tested behavior.
- [x] 2.5 Add a user-facing `[Unreleased]` Fixed entry to `CHANGELOG.md` describing reliable property matching for very small and very large floats; verify the changelog follows Keep a Changelog categories.

## 3. GQL equality and membership

- [x] 3.1 Compile float equality and `IN` through the exact text alternatives while leaving integer equality on the indexed numeric path; verify `hatch test tests/engine/query/test_predicate_properties.py tests/engine/query/test_values.py` passes.
- [x] 3.2 Add query tests for the nightly values, `IN`, `<>`, signed zero, neighboring floats, and integer/float numeric-family equality; verify the tests fail with the old compiler and pass with the new one.
- [x] 3.3 Add a conformance corpus case in `tests/conformance/cases.json` and cover it in `tests/test_conformance.py`; verify `hatch test tests/test_conformance.py tests/test_gql_profile.py` passes.
- [x] 3.4 Update `docs/reference/query-language.md` and `docs/reference/gql-profile.md` to state that numeric equality and membership compare stored reals exactly; verify every construct and matrix row remains accurate.

## 4. Uniqueness constraints

- [x] 4.1 Use exact real text in uniqueness holder lookups, trigger comparisons, and conflict scans; verify `hatch test tests/test_constraints.py` passes.
- [x] 4.2 Decode a reported conflict from the exact stored value so tiny real violations name the correct value and holder; verify with a deterministic conflict test.
- [x] 4.3 Add node and relationship constraint tests for duplicate regression values, neighboring floats, existing-data declaration, `MERGE`, and batch import; verify each scenario fails before the change and passes after it.
- [x] 4.4 Update `docs/guides/constraints.md` to describe exact real uniqueness and violation values; verify the documented examples run as written.

## 5. Windows shell paths and redirected output

- [x] 5.1 Replace the POSIX-only path splitting used by `.import`, `.export`, `.restore`, and `.backup` with a platform-aware parser that preserves native Windows backslashes and drive letters; verify unit tests cover both Windows and POSIX path modes on Linux.
- [x] 5.2 Add shell command tests with Windows-shaped paths for import, export, restore, backup, and quoted paths containing spaces; verify the parser branch preserves the exact path and existing POSIX tests still pass.
- [x] 5.3 Audit `.output` and `.once` file writes and add a regression test that the redirected file contains `\n` line endings; verify the test passes on the current platform and the code uses an explicit newline setting.
- [x] 5.4 Normalize the failed-redirection regression to accept the platform's `OSError` subclass, and preserve the previous output target on both Linux and Windows; verify the session test no longer expects `IsADirectoryError` specifically.
- [ ] 5.5 Account for the Windows console-script suffix when comparing `pygrafito` with `python -m pygrafito`, and fix any other `test_app` process-wiring failures shown by the Windows traceback; verify the process tests pass on Windows.
- [x] 5.6 Update `docs/reference/cli.md` and the shell guide with native Windows path and redirected-newline behavior; add an `[Unreleased]` Fixed entry for the Windows shell fixes and verify the changelog wording is user-facing.

## 6. CSV newlines and SQL view documentation

- [x] 6.1 Add CSV tests that write LF and CRLF bytes explicitly and assert the imported field preserves each sequence; verify `hatch test tests/engine/test_importing.py` passes on Linux.
- [x] 6.2 Keep the CSV reader's no-translation behavior and update `docs/guides/importing.md` to state that embedded field newlines are preserved exactly; verify the guide matches the tests.
- [x] 6.3 Fix `docs/guides/interop.md` to close the raw SQLite reader before the temporary directory is removed, using the same closing pattern as the view tests; verify `hatch test tests/test_docs_examples.py` executes the snippet.
- [x] 6.4 Add a regression test fixture for the SQL view snippet that fails when the raw connection is left open on a platform that cannot delete open files; verify the test passes on Linux and is ready for Windows.

## 7. Crash recovery and SQLite error classification

- [x] 7.1 Change the JSON1 probe so only the actual missing-function error becomes `UnsupportedSqliteError`; preserve lock, I/O, and recovery errors and add unit tests with stand-in connections for each case in `tests/storage/test_schema.py`.
- [x] 7.2 Make the crash harness wait for the terminated process and retry the first open briefly on Windows; add coverage that a transient lock is not reported as missing JSON1 and verify `hatch test tests/test_crash_recovery.py` passes.
- [x] 7.3 Update the embedding or known-limitations reference to describe how an unavailable JSON1 runtime is distinguished from a locked or recovering database; add an `[Unreleased]` Fixed entry if the user-facing error changes.

## 8. POSIX developer tooling on Windows

- [ ] 8.1 Update the pre-push and verify-script test harness to invoke shell programs through a POSIX shell when available and skip with an explicit platform reason otherwise; verify the tests pass or skip cleanly on Linux and are Windows-safe.
- [x] 8.2 Update `docs/contributing/testing.md` and the verification guide to state that `scripts/verify` and the Git hook require a POSIX shell or Git Bash on Windows; verify the instructions match the test behavior.
- [x] 8.3 Add an `[Unreleased]` Changed entry for the Windows developer-tooling guidance and verify the nightly workflow still runs the full library matrix.

## 9. Integration and verification

- [x] 9.1 Run `hatch check --fix`, both supported `hatch test` environments, and `scripts/verify`; confirm the coverage gate and the pinned SQLite container pass.
- [ ] 9.2 Reproduce the nightly runtime with a SQLite 3.50.4 build and run the affected predicate, query, and constraint tests under Python 3.13 and 3.14 on the macOS and Windows portability targets; confirm the regression tests pass on every supported combination.
- [x] 9.3 Run `hatch run docs:build` and fix every warning; confirm the updated guides and references build with the rest of the Sphinx site.
- [ ] 9.4 Run the Windows nightly matrix on Python 3.13 and 3.14 and confirm the previous nightly failures are gone, with only explicitly marked POSIX-tooling skips remaining.
- [x] 9.5 Re-read the proposal, delta specs, design, and tasks; confirm the delivered behavior, documentation, changelog entries, and tests match without leftover placeholders.
