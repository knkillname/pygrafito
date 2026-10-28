# Embed a graph safely

Use a file-backed graph when the database should outlive the process, and keep one `Graph` handle
per thread. This guide covers the lifecycle rules most applications need. The [embedding
contract](../reference/embedding-contract.md) owns journal modes, lock waits, read snapshots, and
the foreign-file rules.

## Open and close a file

`Graph.open` creates a missing file unless `create=False`. A file database prefers write-ahead
logging; `journal_mode` reports what the connection actually obtained.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "grid.db"
    with Graph.open(path, busy_timeout=250) as graph:
        print(graph.journal_mode)  # wal
        graph.add_node("Program", designation="Tron", cycles=40)

    with Graph.open(path, readonly=True) as graph:
        print(graph.journal_mode)  # wal
```

The context manager closes the handle deterministically. Closing twice is a no-op.

## Respect thread affinity

A handle belongs to the thread that opened it. Using it from another thread raises
`HandleAffinityError` instead of sharing the connection silently.

```python
import threading

from pygrafito import Graph, HandleAffinityError

with Graph.open(":memory:") as graph:
    errors: list[Exception] = []

    def use_from_another_thread() -> None:
        try:
            graph.add_node("Program", designation="Rinzler")
        except HandleAffinityError as error:
            errors.append(error)

    thread = threading.Thread(target=use_from_another_thread)
    thread.start()
    thread.join()
    print(len(errors))  # 1
```

Open a handle in the thread that will use it. Several handles may open the same file in one process
or several; they observe each other's committed writes, and at most one writer runs at a time.

## Bound lock waits

`busy_timeout` is the number of milliseconds a write-lock wait may take. The default is 5000. A
wait longer than the configured timeout raises `LockTimeoutError` and changes nothing.

```python
import pathlib
import tempfile

from pygrafito import Graph, LockTimeoutError

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "grid.db"
    with Graph.open(path, busy_timeout=100) as graph:
        try:
            with graph.transaction():
                print("transaction started")
        except LockTimeoutError:
            print("another writer held the lock for too long")
```

The same timeout applies to the write lock needed while opening a database that still has to be
initialized. Increase it for a known long writer rather than retrying indefinitely.

## Reject writes on a read-only handle

A read-only open serves reads, queries, traversal, integrity checks, and backups. Every write,
transaction, and index or constraint change raises `ReadOnlyError`, and a read-only open never
creates a missing file.

```python
import pathlib
import tempfile

from pygrafito import Graph, ReadOnlyError

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "grid.db"
    with Graph.open(path) as graph:
        graph.add_node("Program", designation="Kevin Flynn")

    with Graph.open(path, readonly=True) as graph:
        print(next(iter(graph.find_nodes("Program")))["designation"])  # Kevin Flynn
        try:
            graph.add_node("Program", designation="Clu")
        except ReadOnlyError:
            print("writes are rejected")  # writes are rejected
```

## Back up and check

`backup_to` writes a consistent copy through SQLite's backup operation and moves it into place.
`check_integrity` reports structural problems. Both work on a read-only handle.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "grid.db"
    backup = pathlib.Path(directory) / "backup.db"
    with Graph.open(path) as graph:
        graph.add_node("Program", designation="Tron")
        graph.backup_to(backup)
        print(graph.check_integrity())  # ()

    with Graph.open(backup) as copy:
        print(copy.node(1)["designation"])  # Tron
```

Do not copy a database file while a handle has it open; use `backup_to` instead.

## Know the snapshot rules

Each public read observes one committed state, even if another handle commits while the call runs.
`traverse` and `paths` capture their reachable region before returning a lazy iterator, so no
transaction outlives the iterator. A long `shortest_path` holds a read snapshot for the duration
of the search.

Opening a file never adopts an unrelated SQLite database. A file with no graph layout and at least
one unrelated table is refused with `UnsupportedSqliteError` and left unchanged.

This release writes schema version 2. A version 1 file is refused on read-write and read-only
opens and is left unchanged. There is no in-place migration before 1.0; create a fresh database
with this release, and export an existing 0.8 graph with 0.8 first if you need its data.

## Go deeper

- [Embedding contract](../reference/embedding-contract.md) for journal modes, read snapshots,
  foreign-file rules, and error remedies.
- [`Graph.open`](../api/graph.md#lifecycle) in the API reference.
- [Use the shell](shell.md) for read-only maintenance from the command line.
