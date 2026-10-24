# Embedding contract

A file-backed graph is designed to be embedded in an application that may run several handles,
in one process or several. This page states what those handles may rely on: journal mode, thread
affinity, lock waits, read snapshots, and the rules for creating or refusing a database file.
The read-only SQL views for external readers are documented in [`interop.md`](interop.md).

## Opening a graph

`Graph.open` accepts a filesystem path or `":memory:"`. A missing file is created unless
`create=False` is passed, and `readonly=True` opens an existing file without write access.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    print(graph.journal_mode)  # memory

with Graph.open("grid.db", busy_timeout=250) as graph:
    print(graph.journal_mode)  # wal
```

| Argument | Meaning |
| --- | --- |
| `create` | Whether a missing file may be created. Defaults to `True`. |
| `readonly` | Open an existing file without write access. Defaults to `False`. |
| `busy_timeout` | Milliseconds a lock wait may take. Defaults to 5000. |

A read-only open never creates a file and is not available for an in-memory database. Reads,
queries, traversal, integrity checks, and backups work on a read-only handle; every write,
transaction, and index or constraint change raises `ReadOnlyError`.

## Journal mode

File-backed graphs prefer write-ahead logging. `Graph.journal_mode` reports the mode the
connection actually obtained, lower-cased: `wal` for write-ahead logging, `memory` for an
in-memory graph, or the rollback mode reported by the platform.

Preferring write-ahead logging is not the same as requiring it. A platform that cannot provide
it still opens the graph and keeps every consistency guarantee; only the ability to read while
another handle commits is lost. Check `graph.journal_mode` when that concurrency property
matters.

The journal-mode switch is retried with a small bounded backoff during open, because SQLite's
busy handler does not cover `PRAGMA journal_mode`. This is internal and has no configuration
knob: opening a fresh file from several processes must be safe without caller setup.

## Handles and threads

A handle belongs to the thread that opened it. Using it from another thread raises
`HandleAffinityError` instead of sharing the connection silently. Open a handle in the thread
that will use it.

Several handles may open the same file, in one process or in several. They observe each other's
committed writes. At most one writer runs at a time; another writer waits for the lock and
proceeds when the first commits.

A wait longer than the configured busy timeout raises `LockTimeoutError` and changes nothing.
This applies to a write transaction started with `Graph.transaction` and also to the write lock
needed while opening a database that still has to be initialized.

```python
from pygrafito import Graph, LockTimeoutError

with Graph.open("grid.db", busy_timeout=100) as graph:
    try:
        with graph.transaction():
            ...
    except LockTimeoutError:
        print("another writer held the lock for too long")
```

## Read snapshots

Each public read call observes one committed state, even when another handle commits while the
call runs. A multi-statement read therefore cannot combine a property from one commit with a
label from another.

- `Graph.node` and `Graph.relationship` read their row and their labels from one transaction.
- `Graph.find_nodes` and `Graph.find_relationships` materialize their rows and labels inside one
  transaction.
- `Graph.traverse` and `Graph.paths` capture the reachable region inside one transaction before
  returning a lazy iterator, so no transaction outlives the iterator.
- `Graph.shortest_path` evaluates its whole search inside one snapshot.

Inside an explicit transaction, a convenience read reuses that transaction and therefore sees
its uncommitted writes. A long `shortest_path` holds a read snapshot for the duration of the
search, which can delay checkpointing but never blocks a writer.

## Refusing a foreign database

Opening a file never adds the graph schema to an unrelated SQLite database. The library refuses
an existing file when it records no graph layout and contains at least one unrelated table,
raising `UnsupportedSqliteError` and leaving the file unchanged.

These files still open:

- a path that does not exist, which is created with the graph schema;
- an empty SQLite file;
- a graph database to which an external tool added another table;
- a graph database that contains externally visible views, because views are not tables.

The read-only path applies the same rule, so a read-only handle cannot adopt a foreign file
either.

## Closing and copying

Closing the last handle of a file-backed graph leaves one self-contained database file with no
log or shared-memory sidecar. A database closed cleanly can be copied or opened from read-only
media.

Copying a file while a handle has it open is outside the contract. Use `Graph.backup_to`, which
writes a consistent copy through SQLite's backup operation and atomically moves it into place.

## Errors

| Error | Remedy |
| --- | --- |
| `HandleAffinityError` | Open and use the handle in the same thread. |
| `LockTimeoutError` | Retry later, or increase `busy_timeout` for a known long writer. |
| `ReadOnlyError` | Open the file without `readonly=True` before writing. |
| `UnsupportedSqliteError` | Use a supported SQLite runtime, or choose a path that is not a foreign database. |
