# Design

## Context

See `proposal.md` for motivation. The codec stores properties as canonical JSON text and
reads them with Python's `json.loads`, which round-trips every finite float exactly.
Property filters and uniqueness checks do not read that text directly: they call
`json_extract`, which converts JSON numbers back into binary floats through SQLite's
`sqlite3AtoF`.

SQLite 3.45.1 and 3.53.4 convert the nightly values correctly. SQLite 3.50.4, linked by
the macOS and Windows portability jobs, uses a rounded double-double path and returns a
neighboring float for some literals. The macOS jobs fail on Python 3.13 and 3.14, and both
Windows jobs fail on the same values. The stored JSON text is still exact, and
`json_extract(document, path, path)` returns a JSON array of the original number lexeme
without converting it to a SQL float. For a key that needs a `json_each` scan, the
extracted value is already a parsed scalar, so the existing numeric comparison remains
the fallback.

## Goals / Non-Goals

**Goals:**

- Real equality returns the same element before and after an index is declared, on every
  supported SQLite runtime.
- GQL equality and `IN` keep integers and floats in one numeric family while comparing
  tiny and large reals exactly.
- Uniqueness constraints detect equal reals and report the exact stored value.
- Keep integer, boolean, string, and list equality on the existing numeric index path.
- Native Windows paths work in shell commands, text outputs have deterministic newlines,
  and Windows-only test failures identify the real cause.

**Non-Goals:**

- No change to storage format, schema version, views, or public API.
- No change to arithmetic, `ORDER BY`, or range operators (`<`, `<=`, `>`, `>=`).
- No new dependency or custom SQLite function.
- No requirement that POSIX developer scripts run natively on Windows.

## Decisions

### Compare real equality through canonical JSON text

`PropertyCodec` gains a strict equality expression that asks `json_extract` for the same
path twice. For a portable key this renders
`json_extract(document, '$."key"', '$."key"')`, whose result is the text
`[<stored number>,<stored number>]`. The matching bind value is the same two-element array
serialized by the codec. Comparing text avoids SQLite's float conversion entirely.

Keys that still require the `json_each` scan keep the existing extracted scalar and
numeric bind value, because those builds cannot address the path and offer no raw token.
That path only affects SQLite older than 3.47, which uses the long-double conversion on
the supported macOS and Linux runtimes.

Alternative rejected: adding a custom SQLite function or index expression. It would make
the schema depend on application-defined callbacks and complicate read-only and external
access.

### Use exact text only where SQLite's conversion is unsafe

Storage filters already guard each property with `json_type`. For a real value they bind
the exact array text; for booleans, integers, strings, and arrays they keep the existing
scalar comparison. This preserves the numeric index for the common types and avoids the
index-transparency regression the numeric comparison caused for reals.

GQL still treats integers and floats as one numeric family. A float constant matches the
canonical text for its own representation and, when it is an exact integer in range, the
canonical text for that integer. `0.0` and `-0.0` match both signed-zero spellings. An
integer constant keeps the existing SQL comparison because integer parsing is exact and
the declared index still applies.

Alternative rejected: `numeric = ? OR exact_text = ?`. On SQLite 3.50.4 the next
representable float can round to the same parsed value, so the numeric branch produces
false positives for neighboring reals.

Alternative rejected: tolerance-based comparison with `math.isclose`. Real property
equality is exact: neighboring floats are distinct values, and uniqueness must not treat
them as duplicates. Any tolerance large enough to absorb SQLite's rounding also conflates
some neighbors, is arbitrary around zero and across exponents, is not transitive, and
cannot run inside the SQL predicates, indexes, or triggers that enforce the contract.

### Apply the same rule to uniqueness constraints

Triggers, holder lookups, and conflict scans compare two stored reals with the exact text
expression and only fall back to the scalar comparison for non-real types. The conflict
scan selects the exact text and type so a reported violation carries the stored value,
not SQLite's rounded reconstruction.

### Keep index DDL unchanged

Declared indexes keep their current `(json_extract, json_type)` expressions. Integer,
boolean, string, and list equality still seek. Real equality may read candidate rows
when no expression index over the exact text exists; correctness and index transparency
take priority over a new companion index. The index-behavior reference will state this.

### Preserve native paths in shell commands

The shell currently delegates `.import`, `.export`, `.restore`, and `.backup` arguments
to `shlex.split`, whose POSIX mode treats backslashes as escapes and strips them from
`C:\grid\file.csv`. A platform-aware argument parser will treat backslashes as ordinary
path characters on Windows while keeping quote handling and the existing POSIX behavior.
Quoted paths remain the way to include spaces. The parser is shared by every dot command
that accepts a path, so import, export, restore, and backup cannot drift.

Alternative rejected: requiring every Windows path to be quoted. It would break existing
scripts and make the shell feel foreign on the platform.

### Keep text output byte-for-byte stable

Redirected shell output already opens files with `newline=""`. The remaining Windows
failures come from tests and fixtures that use default text-mode writes, plus
platform-specific exceptions such as opening a directory. Tests that assert a specific
line ending will write those bytes explicitly; redirected output will keep `\n` on every
platform. The CSV reader already opens with `newline=""`, so field contents survive
unchanged; the test fixture will write LF bytes for the LF scenario and a new scenario
will cover CRLF input.

### Classify SQLite startup failures accurately and let Windows release handles

`Schema.verify_json_support` currently maps every `OperationalError` to "missing JSON1".
On Windows, a killed worker can leave a database or WAL handle briefly busy, so a lock or
recovery error is reported as a missing JSON1 runtime. The probe will inspect the
underlying error and only report missing JSON1 for the actual missing-function case.
Crash tests will wait for the terminated process and retry the first read briefly before
asserting failure. A server-side retry is preferable to marking the Windows crash suite
as skipped because durability is part of the library contract.

### Close raw SQLite readers before temporary directories disappear

The SQL-view guide opens `sqlite3.connect(...)` in a `with` block. A `sqlite3.Connection`
context manager commits or rolls back but does not close the handle, so Windows cannot
delete the temporary directory while the database is open. The example will use
`contextlib.closing`, matching the view tests, and the documentation test will keep
executing the snippet.

### Run POSIX developer tooling through a shell or mark it skipped

`scripts/verify` and the pre-push hook are POSIX shell programs. Windows can run them
through Git Bash, but Python cannot execute them directly. Their tests will locate a
POSIX shell and invoke the script through it, or skip with an explicit platform reason
when no shell is available. The verification guide will say which scripts require a
POSIX shell. Library, CLI, import, interop, and constraint tests still run on Windows.

## Risks / Trade-offs

- [Real equality may scan instead of seek on a declared index] → Accept for this fix;
  document the behavior and keep all other types on the indexed path.
- [Text equality assumes canonical stored JSON] → Every write, import, and restore path
  already goes through the codec; tests will cover round-trip and adjacent values.
- [Special keys on SQLite older than 3.47 keep the numeric fallback] → Those runtimes
  convert with the long-double path on supported platforms; the fallback preserves the
  current behavior and cannot regress older databases.
- [Range comparisons keep SQLite's numeric conversion] → Out of scope; equality, `IN`,
  and uniqueness are the reported failure and the documented contract changes.
- [A platform-aware argument splitter could change quoting on POSIX] → Keep the existing
  POSIX branch unchanged and add path tests for both platform families.
- [Crash tests may still be timing-sensitive on Windows] → Wait for process exit and
  retry the first read; if the platform cannot provide the guarantee, report the specific
  failure instead of masking it as missing JSON1.
- [POSIX tooling tests may skip on a Windows runner without Bash] → Skip only the
  developer-tooling tests and keep the library signal intact; the skip reason names the
  missing shell.

## Migration Plan

No data migration. A reopened database keeps its schema version, indexes, and canonical
payloads; only the generated predicate SQL changes. Rollback is a code revert, and the
database remains readable by both versions.

## Open Questions

- The Windows 3.14 log confirms that export and restore lose backslashes and that a
  directory redirect raises `PermissionError` rather than `IsADirectoryError`. The apply
  run still needs the remaining `test_app` and `test_commands` tracebacks to confirm that
  path parsing and console-script naming explain every CLI failure.
- The Windows runner should provide Git Bash's `sh`; if it does not, the POSIX tooling
  tests skip with the platform reason described above.
