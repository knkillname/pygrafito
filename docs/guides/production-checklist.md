# Production checklist

Use this list before putting a graph in front of real users. It assumes a file-backed graph on
Linux with Python 3.13 or 3.14 and SQLite 3.38 or newer.

## Before the first write

- [ ] Confirm the runtime: `python -c "import sqlite3; print(sqlite3.sqlite_version)"` reports
  3.38 or newer.
- [ ] Open one handle per thread and keep it in that thread. Do not share a handle across threads.
- [ ] Choose a `busy_timeout` that covers the longest expected writer, and handle
  `LockTimeoutError` with a retry or an explicit failure.
- [ ] Decide where the database lives. On Colab, use `/content` for ephemeral data or mount Drive
  for persistence; the runtime filesystem is not durable.

## Memory and query shape

- [ ] Set a `QueryBudget(max_rows=...)` for memory-sensitive workloads. The default is 100,000
  intermediate bindings, and results are materialized.
- [ ] Add a final `LIMIT` or use a bounded path mode for open walks. An open `WALK` without demand
  or a restricting mode runs until the query budget stops it.
- [ ] Add indexes for the property filters that select small start sets; verify with `EXPLAIN` or
  the benchmark shape rather than assuming every index helps.
- [ ] Keep labels and property values within the strict model: booleans, signed 64-bit integers,
  finite floats, strings, and homogeneous lists of those scalars.

## Durability and recovery

- [ ] Use `Graph.transaction()` for multi-write units and keep convenience writes for single
  atomic changes.
- [ ] Schedule `backup_to` to a different filesystem or bucket. Do not copy a live database file;
  the backup path writes a temporary sibling and replaces the destination atomically.
- [ ] For a bulk load that must be all-or-nothing, pass `atomic=True` to `import_rows` or
  `import_file`. The default commits each batch independently.
- [ ] Test recovery once: kill a writer after a commit and after an uncommitted write, reopen the
  file, and run `check_integrity`. Committed rows should remain; the open transaction should not.
- [ ] Do not delete `-wal` or `-shm` files by hand. Reopen the graph and let SQLite recover.

## Formats and upgrades

- [ ] Pin the pygrafito version in the deployment. Schema, snapshot, and view version 2 are frozen
  for 1.x.
- [ ] Keep a JSONL snapshot alongside the database backup if the data must move between releases
  or into another tool.
- [ ] Before a major upgrade, read the changelog for migration notes. Version 2 files open in 1.x;
  other versions are refused with an export path rather than migrated automatically.
- [ ] Run `check_integrity` after a restore, a backup restore, or an unexpected shutdown.

## Observability

- [ ] Log `journal_mode`, `view_version`, and the SQLite runtime version at startup.
- [ ] Record query budget failures and lock timeouts separately from validation errors.
- [ ] Keep the database, its sidecars, and the backup destination on storage with enough free
  space for a full copy plus the write-ahead log.

See [Known limitations](../reference/known-limitations.md) for the boundaries behind these
checks, and [Embed a graph safely](embedding.md) for the lifecycle rules.
