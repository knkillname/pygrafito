# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Multiprocess tests for the embedding concurrency contract."""

import multiprocessing
import queue
import sqlite3
import threading
import time
import typing
from pathlib import Path

import pytest

from pygrafito import Graph, LockTimeoutError
from pygrafito.storage.schema import Schema

type Event = typing.Any
type Queue = typing.Any


class _FirstOpenWorker:
    """Open one fresh database file and report a failure.

    Parameters
    ----------
    path : Path
        Database file all workers race to open.
    start : Event
        Event that releases every worker at the same time.
    errors : Queue
        Queue that receives one message per failure.
    """

    def __init__(self, path: Path, start: Event, errors: Queue) -> None:
        self._path = path
        self._start = start
        self._errors = errors

    def __call__(self) -> None:
        """Open and close the graph after the shared start signal."""
        self._start.wait(10)
        try:
            with Graph.open(self._path):
                pass
        except BaseException as error:
            self._errors.put(f"{type(error).__name__}: {error}")


class _CommitWriter:
    """Create a node, wait for a reader, then commit a second value.

    Parameters
    ----------
    path : Path
        Database file shared with the reader.
    ready : Event
        Set after the initial commit.
    first_read : Event
        Set by the reader after its first observation.
    updated : Event
        Set after the second commit.
    values : Queue
        Unused by the writer; kept for symmetry with the reader.
    """

    def __init__(
        self,
        path: Path,
        ready: Event,
        first_read: Event,
        updated: Event,
        values: Queue,
    ) -> None:
        self._path = path
        self._ready = ready
        self._first_read = first_read
        self._updated = updated
        self._values = values

    def __call__(self) -> None:
        """Commit two states around the reader's first observation."""
        with Graph.open(self._path) as graph:
            node = graph.add_node("Program", designation="Tron")
            self._ready.set()
            self._first_read.wait(10)
            graph.set_properties(node, designation="Rinzler")
        self._updated.set()


class _CommitReader:
    """Read a node before and after another process commits.

    Parameters
    ----------
    path : Path
        Database file shared with the writer.
    ready : Event
        Set after the writer's initial commit.
    first_read : Event
        Set after the reader's first observation.
    updated : Event
        Set after the writer's second commit.
    values : Queue
        Queue that receives both observations.
    """

    def __init__(
        self,
        path: Path,
        ready: Event,
        first_read: Event,
        updated: Event,
        values: Queue,
    ) -> None:
        self._path = path
        self._ready = ready
        self._first_read = first_read
        self._updated = updated
        self._values = values

    def __call__(self) -> None:
        """Observe the old value, then the new committed value."""
        self._ready.wait(10)
        with Graph.open(self._path) as graph:
            first = graph.node(1)["designation"]
            self._values.put(first)
            self._first_read.set()
            self._updated.wait(10)
            second = graph.node(1)["designation"]
            self._values.put(second)


class _Holder:
    """Hold a write transaction until another process has tried to begin.

    Parameters
    ----------
    path : Path
        Database file shared with the waiter.
    locked : Event
        Set after the write lock is held.
    attempting : Event
        Set by the waiter just before it begins.
    release : Event
        Set when the waiter reports that it is blocked.
    """

    def __init__(
        self,
        path: Path,
        locked: Event,
        attempting: Event,
        release: Event,
    ) -> None:
        self._path = path
        self._locked = locked
        self._attempting = attempting
        self._release = release

    def __call__(self) -> None:
        """Hold the lock until the other process has attempted a write."""
        with Graph.open(self._path) as graph:
            with graph.transaction() as transaction:
                transaction.add_node("Program", designation="Kevin Flynn")
                self._locked.set()
                self._attempting.wait(10)
                time.sleep(0.3)
                transaction.add_node("Program", designation="Quorra")
            self._release.set()


class _TurnTaker:
    """Begin a write transaction while another process holds the lock.

    Parameters
    ----------
    path : Path
        Database file shared with the holder.
    locked : Event
        Set after the holder owns the write lock.
    attempting : Event
        Set just before this process begins.
    release : Event
        Set after the holder commits.
    elapsed : Queue
        Queue that receives how long the write lock wait took.
    """

    def __init__(
        self,
        path: Path,
        locked: Event,
        attempting: Event,
        release: Event,
        elapsed: Queue,
    ) -> None:
        self._path = path
        self._locked = locked
        self._attempting = attempting
        self._release = release
        self._elapsed = elapsed

    def __call__(self) -> None:
        """Wait for the lock, write, and report the measured wait."""
        self._locked.wait(10)
        with Graph.open(self._path) as graph:
            self._attempting.set()
            start = time.perf_counter()
            with graph.transaction() as transaction:
                transaction.add_node("Program", designation="Rinzler")
            self._elapsed.put(time.perf_counter() - start)
        self._release.wait(10)


class _UncommittedWriter:
    """Write inside a transaction and hold it until a reader observes.

    Parameters
    ----------
    path : Path
        Database file shared with the read-only reader.
    ready : Event
        Set after the initial commit.
    uncommitted : Event
        Set after the change is written but not committed.
    observed : Event
        Set after the read-only reader observed the previous commit.
    committed : Event
        Set after the transaction commits.
    """

    def __init__(
        self,
        path: Path,
        ready: Event,
        uncommitted: Event,
        observed: Event,
        committed: Event,
    ) -> None:
        self._path = path
        self._ready = ready
        self._uncommitted = uncommitted
        self._observed = observed
        self._committed = committed

    def __call__(self) -> None:
        """Hold an uncommitted change until the reader has read."""
        with Graph.open(self._path) as graph:
            node = graph.add_node("Program", designation="Tron")
            self._ready.set()
            with graph.transaction() as transaction:
                transaction.set_properties(node, designation="Rinzler")
                self._uncommitted.set()
                self._observed.wait(10)
            self._committed.set()


class _ReadOnlyObserver:
    """Read a file from a read-only handle during another commit.

    Parameters
    ----------
    path : Path
        Database file shared with the writer.
    ready : Event
        Set after the writer's initial commit.
    uncommitted : Event
        Set while the writer holds an uncommitted change.
    observed : Event
        Set after the first observation.
    committed : Event
        Set after the writer commits.
    values : Queue
        Queue that receives both observations.
    """

    def __init__(
        self,
        path: Path,
        ready: Event,
        uncommitted: Event,
        observed: Event,
        committed: Event,
        values: Queue,
    ) -> None:
        self._path = path
        self._ready = ready
        self._uncommitted = uncommitted
        self._observed = observed
        self._committed = committed
        self._values = values

    def __call__(self) -> None:
        """Read the committed value while a writer is uncommitted."""
        self._ready.wait(10)
        with Graph.open(self._path, readonly=True) as graph:
            self._uncommitted.wait(10)
            self._values.put(graph.node(1)["designation"])
            self._observed.set()
            self._committed.wait(10)
            self._values.put(graph.node(1)["designation"])


class TestConcurrentFirstOpen:
    """Verify several processes can initialize one fresh file."""

    def test_first_open_race(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        path = tmp_path / "grid.db"
        start = context.Event()
        errors = context.Queue()
        workers = [_FirstOpenWorker(path, start, errors) for _ in range(6)]
        processes = [context.Process(target=worker) for worker in workers]
        for process in processes:
            process.start()
        start.set()
        for process in processes:
            process.join(30)
        failures: list[str] = []
        while True:
            try:
                failures.append(errors.get(timeout=0.1))
            except queue.Empty:
                break
        assert all(process.exitcode == 0 for process in processes)
        assert failures == []

    def test_first_open_records_version(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        path = tmp_path / "grid.db"
        start = context.Event()
        errors = context.Queue()
        workers = [_FirstOpenWorker(path, start, errors) for _ in range(6)]
        processes = [context.Process(target=worker) for worker in workers]
        for process in processes:
            process.start()
        start.set()
        for process in processes:
            process.join(30)
        assert all(process.exitcode == 0 for process in processes)
        assert errors.empty()
        with Graph.open(path) as graph:
            assert graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"] == 0
            row = graph._database.connection.execute("PRAGMA user_version").fetchone()
            assert row == (Schema.VERSION,)


class TestCrossProcessVisibility:
    """Verify committed writes travel between processes."""

    def test_reader_observes_each_commit(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        path = tmp_path / "grid.db"
        ready = context.Event()
        first_read = context.Event()
        updated = context.Event()
        values = context.Queue()
        writer = context.Process(target=_CommitWriter(path, ready, first_read, updated, values))
        reader = context.Process(target=_CommitReader(path, ready, first_read, updated, values))
        writer.start()
        reader.start()
        writer.join(30)
        reader.join(30)
        assert writer.exitcode == 0
        assert reader.exitcode == 0
        observed = [values.get(timeout=1) for _ in range(2)]
        assert sorted(observed) == ["Rinzler", "Tron"]

    def test_writers_take_turns(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        path = tmp_path / "grid.db"
        locked = context.Event()
        attempting = context.Event()
        release = context.Event()
        elapsed = context.Queue()
        holder = context.Process(target=_Holder(path, locked, attempting, release))
        waiter = context.Process(target=_TurnTaker(path, locked, attempting, release, elapsed))
        holder.start()
        waiter.start()
        holder.join(30)
        waiter.join(30)
        assert holder.exitcode == 0
        assert waiter.exitcode == 0
        wait = elapsed.get(timeout=1)
        assert wait >= 0.2
        with Graph.open(path) as graph:
            designations = sorted(node["designation"] for node in graph.find_nodes("Program"))
        assert designations == ["Kevin Flynn", "Quorra", "Rinzler"]


class TestReadOnlyDuringCommit:
    """Verify a read-only handle keeps reading while another process commits."""

    def test_read_only_reader_sees_the_previous_commit(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            mode = graph.journal_mode
        if mode != "wal":
            pytest.skip(f"write-ahead logging is unavailable; journal mode is {mode}")
        context = multiprocessing.get_context("spawn")
        ready = context.Event()
        uncommitted = context.Event()
        observed = context.Event()
        committed = context.Event()
        values = context.Queue()
        writer = context.Process(
            target=_UncommittedWriter(path, ready, uncommitted, observed, committed)
        )
        reader = context.Process(
            target=_ReadOnlyObserver(
                path,
                ready,
                uncommitted,
                observed,
                committed,
                values,
            )
        )
        writer.start()
        reader.start()
        writer.join(30)
        reader.join(30)
        assert writer.exitcode == 0
        assert reader.exitcode == 0
        observed_values = [values.get(timeout=1) for _ in range(2)]
        assert observed_values == ["Tron", "Rinzler"]


class TestReadSnapshotConsistency:
    """Verify a reader never sees a mixed state across two writes in one commit."""

    def test_reader_never_sees_a_mixed_state(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        path = tmp_path / "grid.db"
        ready = context.Event()
        stop = context.Event()
        errors = context.Queue()
        reads = context.Queue()
        writer = context.Process(target=_StateWriter(path, ready, stop, 50))
        reader = context.Process(target=_StateReader(path, ready, stop, errors, reads))
        writer.start()
        reader.start()
        writer.join(30)
        reader.join(30)
        assert writer.exitcode == 0
        assert reader.exitcode == 0
        assert errors.empty()
        assert reads.get(timeout=1) > 0


class TestLockTimeout:
    """Verify a write-lock wait can be bounded by the caller."""

    def test_short_timeout_fails(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        path = tmp_path / "grid.db"
        locked = context.Event()
        release = context.Event()
        with Graph.open(path, busy_timeout=50) as graph:
            holder = context.Process(target=_BoundedHolder(path, locked, release))
            holder.start()
            assert locked.wait(10)
            try:
                start = time.perf_counter()
                with pytest.raises(LockTimeoutError):
                    graph.transaction().begin()
                assert time.perf_counter() - start < 1
            finally:
                release.set()
                holder.join(30)
        assert holder.exitcode == 0

    def test_open_timeout_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path):
            pass
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA user_version = 0")
            connection.commit()
        finally:
            connection.close()
        locked = threading.Event()
        release = threading.Event()
        holder = threading.Thread(target=_RawLockHolder(path, locked, release))
        holder.start()
        assert locked.wait(10)
        try:
            with pytest.raises(LockTimeoutError):
                Graph.open(path, busy_timeout=50)
        finally:
            release.set()
            holder.join(30)
        with Graph.open(path) as graph:
            row = graph._database.connection.execute("PRAGMA user_version").fetchone()
            assert row == (Schema.VERSION,)


class _StateWriter:
    """Alternate one node between two label and property states.

    Parameters
    ----------
    path : Path
        Database file shared with the reader.
    ready : Event
        Set after the initial committed state.
    stop : Event
        Set after the last transaction commits.
    iterations : int
        Number of complete state switches.
    """

    def __init__(self, path: Path, ready: Event, stop: Event, iterations: int) -> None:
        self._path = path
        self._ready = ready
        self._stop = stop
        self._iterations = iterations

    def __call__(self) -> None:
        """Switch both the label and the property inside one transaction."""
        with Graph.open(self._path) as graph:
            node = graph.add_node("Program", designation="Tron")
            self._ready.set()
            for iteration in range(self._iterations):
                with graph.transaction() as transaction:
                    if iteration % 2 == 0:
                        transaction.remove_labels(node, "Program")
                        transaction.add_labels(node, "ISO")
                        transaction.set_properties(node, designation="Rinzler")
                    else:
                        transaction.remove_labels(node, "ISO")
                        transaction.add_labels(node, "Program")
                        transaction.set_properties(node, designation="Tron")
                time.sleep(0.001)
        self._stop.set()


class _StateReader:
    """Assert that a node never exposes a mixed label and property state.

    Parameters
    ----------
    path : Path
        Database file shared with the writer.
    ready : Event
        Set after the writer's initial committed state.
    stop : Event
        Set after the writer's last transaction commits.
    errors : Queue
        Queue that receives every mixed state observed.
    reads : Queue
        Queue that receives the number of successful reads.
    """

    VALID: frozenset[tuple[frozenset[str], str]] = frozenset(
        {
            (frozenset({"Program"}), "Tron"),
            (frozenset({"ISO"}), "Rinzler"),
        }
    )

    def __init__(
        self,
        path: Path,
        ready: Event,
        stop: Event,
        errors: Queue,
        reads: Queue,
    ) -> None:
        self._path = path
        self._ready = ready
        self._stop = stop
        self._errors = errors
        self._reads = reads

    def __call__(self) -> None:
        """Read the node repeatedly until the writer stops."""
        self._ready.wait(10)
        count = 0
        with Graph.open(self._path) as graph:
            while not self._stop.is_set():
                node = graph.node(1)
                state = (node.labels, node["designation"])
                if state not in self.VALID:
                    self._errors.put(f"mixed state: {state}")
                    break
                count += 1
        self._reads.put(count)


class _RawLockHolder:
    """Hold a raw SQLite write lock until the test releases it.

    Parameters
    ----------
    path : Path
        Database file locked by this connection.
    locked : Event
        Set after the write lock is held.
    release : Event
        Set when the test finished its bounded open attempt.
    """

    def __init__(self, path: Path, locked: Event, release: Event) -> None:
        self._path = path
        self._locked = locked
        self._release = release

    def __call__(self) -> None:
        """Hold a write transaction without using the graph facade."""
        connection = sqlite3.connect(self._path, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE nodes SET props = props")
            self._locked.set()
            self._release.wait(10)
            connection.execute("ROLLBACK")
        finally:
            connection.close()


class _BoundedHolder:
    """Hold a write transaction until the test releases it.

    Parameters
    ----------
    path : Path
        Database file locked by this process.
    locked : Event
        Set after the write lock is held.
    release : Event
        Set when the test finished its bounded attempt.
    """

    def __init__(self, path: Path, locked: Event, release: Event) -> None:
        self._path = path
        self._locked = locked
        self._release = release

    def __call__(self) -> None:
        """Hold the write lock until the release signal."""
        with Graph.open(self._path) as graph, graph.transaction() as transaction:
            transaction.add_node("Program", designation="Clu")
            self._locked.set()
            self._release.wait(10)
