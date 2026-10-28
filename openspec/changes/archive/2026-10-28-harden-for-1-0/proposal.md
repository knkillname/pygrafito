# Proposal

## Why

The GQL language profile is complete, but the 1.0 promise is not yet credible. The Python floor is
accidentally 3.14-only, the schema and snapshot formats are not frozen, the public API has no
stability or deprecation policy, the query boundary leaks raw built-in exceptions on adversarial
input, result memory is undocumented, and there is no fuzz or crash/recovery evidence. This change
closes the 1.0 hardening gate without adding language features.

Python 3.13 is the floor because Google Colab currently runs 3.13, and the library should be
installable in the environment many readers already use.

## What Changes

- **Platform contract:** support Python 3.13 and 3.14; Linux is the blocking gate; macOS and
  Windows run nightly as non-blocking portability signals; document the SQLite 3.38 minimum.
- **CI:** a Linux gate over 3.13 and 3.14, with separate quality, package, and docs jobs, plus a
  scheduled nightly cross-platform workflow that reports failures without blocking releases.
- **Python compatibility:** lower `requires-python` to `>=3.13`, set Ruff and Pyrefly targets to
  3.13, quote the three annotations that rely on 3.14 deferred evaluation, and make the
  concurrency tests spawn-safe so the nightly Windows job can run.
- **Public API freeze:** a golden surface snapshot, a deprecation policy that warns, documents,
  keeps a deprecated name for at least one minor release, and removes it only in 2.0, and PEP 702
  decorators on 3.13.
- **Error contract:** parser depth limits and oversized literals raise query errors; no raw
  `RecursionError`, `ValueError`, `sqlite3.Error`, or `UnicodeDecodeError` escapes the library.
- **Result memory:** materialized `QueryResult` is the 1.0 contract; `QueryBudget.max_rows` bounds
  it; document the envelope and keep streaming out of 1.0.
- **Format freeze:** schema v2, snapshot v2, and the view version are frozen; golden fixtures prove
  0.9/1.0 compatibility; unknown versions are refused with an export path; no automatic migration.
- **Reliability evidence:** Hypothesis property tests for the lexer, parser, values, SQL predicate
  generation, import, and snapshot codec, plus crash/recovery tests for WAL, backup, import, and
  restore.
- **Performance and documentation:** file-backed benchmarks, known limitations, a production
  checklist, Colab guidance, and migration notes.
- **No new GQL constructs.** The language profile stays frozen.

## Capabilities

### New Capabilities

- `platform-support`: supported Python versions, operating systems, SQLite minimum, pure-Python
  installation, and the blocking-gate plus nightly portability contract.
- `public-api`: stability of the exported Python surface, deprecation policy, and the golden API
  snapshot.

### Modified Capabilities

- `property-graph`: crash durability (committed transactions survive process termination,
  uncommitted work does not, WAL recovery succeeds) and the frozen v2 layout and migration policy.
- `graph-query-language`: the total query error contract for resource limits and literal
  conversion, and the materialized result-memory contract bounded by the query budget.
- `graph-interop`: frozen snapshot v2 and view version, golden compatibility with 0.9/1.0,
  unknown-version refusal, and crash-safe restore.

## Impact

- `pyproject.toml`: `requires-python`, classifiers, Ruff and Pyrefly targets, the Hatch test
  matrix, and a Hypothesis test-only dependency.
- `.github/workflows/ci.yml` and a new nightly workflow.
- `src/pygrafito/engine/query/ast.py`, `executor.py`, `parser.py`, `lexer.py`, and
  `src/pygrafito/cli/commands.py`: annotation compatibility and depth/literal guards.
- `src/pygrafito/storage/schema.py` and `src/pygrafito/engine/interop.py`: freeze and refusal
  messages, with no format change.
- `tests/`: the Hypothesis suite, the crash/recovery suite, golden fixtures, the public-API
  snapshot, and spawn-safe concurrency tests.
- `.gitattributes`, `docs/`, `CHANGELOG.md`, and `benchmarks/`.
- Runtime dependencies remain standard library only; Hypothesis is test-only.
