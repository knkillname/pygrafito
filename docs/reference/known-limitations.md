# Known limitations

:::{admonition} tl;dr
:class: tldr

The deliberate 1.x boundaries: materialized results, a single-writer SQLite connection,
non-atomic imports, frozen version 2 formats, and no server or streaming API. Plan around them or
open a change proposal.
:::

These are the deliberate 1.x boundaries. They are not bugs to work around; plan the
application around them or open a change proposal for a future release.

## Platform

- **Linux with glibc is the supported platform.** macOS and Windows are exercised nightly as a
  non-blocking portability signal. Do not treat them as supported until that signal is green.
- **Python 3.13 and 3.14 are supported.** Python 3.12 and older are not. The package is pure
  Python and does not need a compiler, but it does need SQLite 3.38 or newer with JSON functions.
- **Google Colab storage is ephemeral.** Use `/content` for a database that only needs to live for
  the notebook session, or mount Google Drive for persistence. A runtime restart loses a file
  under `/content`.

## Results and memory

- **Query results are fully materialized.** `Graph.query` and `PreparedQuery.execute` return a
  `QueryResult` with every row before returning. There is no streaming result API in 1.x.
- **The row budget bounds memory.** `QueryBudget.max_rows` defaults to 100,000 intermediate
  bindings. Lower it for a memory-sensitive embedding; exceeding it raises
  `QueryBudgetExceededError` and returns no rows.
- **Writes are single-writer.** The library uses one connection per handle and is not thread-safe.
  Keep a handle in the thread that opened it. Several handles or processes may read and take
  turns writing, but they do not provide parallel writes.

## Ingestion

- **Single-node `MERGE` is row-at-a-time.** The benchmark measures roughly 480 to 700 rows per
  second depending on dataset size and whether the graph is in memory or on disk. This favors
  sequential visibility and a small implementation. A faster `MERGE` path is deferred to a later
  release.
- **The default import is non-atomic.** Each batch commits independently. A failure or termination
  can leave the batches that already committed. Pass `atomic=True` for a bulk load that must be
  all-or-nothing; it holds the write lock and uses more memory for the transaction.

## Formats and migration

- **Schema version 2, snapshot version 2, and view version 2 are frozen for 1.x.** A version 2
  database or snapshot written by 0.9 or 1.0 opens without migration. Any other version is
  refused; export the graph with the release that wrote it and load it into a fresh version 2
  graph. There is no automatic migration.
- **Snapshots do not carry indexes or constraints.** Restore keeps the target's schema objects and
  enforces them during the load; a snapshot that is valid without a constraint can fail against a
  target that declares one.
- **Snapshot restore holds the write lock and an id map.** Restore uses memory proportional to the
  number of nodes and blocks other writers for the duration. Run a large restore during a quiet
  period.

## Not in 1.x

- A server, driver, multi-tenant mode, or network protocol.
- A Cypher compatibility mode beyond the published GQL profile.
- Automatic database migration or background compaction.
- A streaming result API or a public lazy row iterator.
