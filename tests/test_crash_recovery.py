# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Crash and recovery tests driven by real terminated subprocesses."""

import contextlib
import os
import pathlib
import sqlite3
import subprocess
import sys
import time
import typing

import pytest

from pygrafito import Graph, LockTimeoutError


class CrashHarness:
    """Start the crash worker, wait for its signal, and terminate it."""

    WORKER: typing.ClassVar[pathlib.Path] = pathlib.Path(__file__).with_name("crash_worker.py")
    RETRY_ON_LOCK: typing.ClassVar[bool] = sys.platform == "win32"
    RETRY_ATTEMPTS: typing.ClassVar[int] = 20
    RETRY_DELAY: typing.ClassVar[float] = 0.05

    @classmethod
    @contextlib.contextmanager
    def reopen(cls, database: pathlib.Path) -> typing.Iterator[Graph]:
        """Open a graph after a crash and close it after the test block.

        Parameters
        ----------
        database : pathlib.Path
            Database to open.

        Yields
        ------
        Graph
            Open graph handle.
        """
        graph = cls._open_after_crash(database)
        try:
            yield graph
        finally:
            graph.close()

    @classmethod
    def _open_after_crash(cls, database: pathlib.Path) -> Graph:
        """Open a graph, retrying a transient handle lock on Windows.

        Parameters
        ----------
        database : pathlib.Path
            Database to open.

        Returns
        -------
        Graph
            Open graph handle.

        Raises
        ------
        sqlite3.OperationalError
            If the database still reports a lock after every retry.
        LockTimeoutError
            If the configured busy timeout still expires after every retry.
        """
        attempt = 0
        while True:
            try:
                return Graph.open(database)
            except (sqlite3.OperationalError, LockTimeoutError):
                attempt += 1
                if not cls.RETRY_ON_LOCK or attempt >= cls.RETRY_ATTEMPTS:
                    raise
                time.sleep(cls.RETRY_DELAY)

    @classmethod
    def start(
        cls,
        action: str,
        database: pathlib.Path,
        ready: pathlib.Path,
        *arguments: object,
    ) -> subprocess.Popen[str]:
        """Start one worker action.

        Parameters
        ----------
        action : str
            Worker method name.
        database : pathlib.Path
            Database path passed to the worker.
        ready : pathlib.Path
            File the worker writes after it is ready.
        *arguments : object
            Additional positional arguments.

        Returns
        -------
        subprocess.Popen[str]
            Running worker.
        """
        ready.unlink(missing_ok=True)
        command = [
            sys.executable,
            str(cls.WORKER),
            action,
            str(database),
            str(ready),
            *(str(argument) for argument in arguments),
        ]
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @classmethod
    def wait_ready(
        cls,
        process: subprocess.Popen[str],
        ready: pathlib.Path,
        timeout: float = 10.0,
    ) -> None:
        """Wait until the worker signals that its operation may begin.

        Parameters
        ----------
        process : subprocess.Popen[str]
            Running worker.
        ready : pathlib.Path
            Signal file written by the worker.
        timeout : float, optional
            Maximum wait in seconds, by default ten.

        Raises
        ------
        AssertionError
            If the worker exits or does not signal in time.
        """
        deadline = time.monotonic() + timeout
        while not ready.exists():
            if process.poll() is not None:
                _stdout, stderr = process.communicate()
                message = f"worker exited before it was ready: {stderr}"
                raise AssertionError(message)
            if time.monotonic() > deadline:
                process.kill()
                _stdout, stderr = process.communicate()
                message = f"worker did not become ready: {stderr}"
                raise AssertionError(message)
            time.sleep(0.005)

    @classmethod
    def kill(cls, process: subprocess.Popen[str]) -> tuple[str, str]:
        """Terminate the worker and collect its output.

        Parameters
        ----------
        process : subprocess.Popen[str]
            Running worker.

        Returns
        -------
        tuple[str, str]
            Captured standard output and standard error.
        """
        process.kill()
        try:
            return process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.communicate(timeout=10)

    @classmethod
    def run(
        cls,
        action: str,
        database: pathlib.Path,
        ready: pathlib.Path,
        *arguments: object,
        delay: float = 0.0,
    ) -> tuple[str, str]:
        """Run one worker, kill it after a delay, and return its output."""
        process = cls.start(action, database, ready, *arguments)
        try:
            cls.wait_ready(process, ready)
            if delay:
                time.sleep(delay)
            return cls.kill(process)
        finally:
            if process.poll() is None:
                cls.kill(process)

    @classmethod
    def run_fifo(
        cls,
        action: str,
        database: pathlib.Path,
        ready: pathlib.Path,
        fifo: pathlib.Path,
        payload: bytes,
        *arguments: object,
        delay: float = 0.5,
    ) -> tuple[str, str]:
        """Run one worker against a FIFO and kill it mid-operation."""
        process = cls.start(action, database, ready, fifo, *arguments)
        try:
            cls.wait_ready(process, ready)
            descriptor = os.open(fifo, os.O_RDWR)
            try:
                assert os.write(descriptor, payload) == len(payload)
                time.sleep(delay)
                return cls.kill(process)
            finally:
                os.close(descriptor)
        finally:
            if process.poll() is None:
                cls.kill(process)


class _FlakyOpen:
    """Fail a fixed number of graph opens before delegating.

    Parameters
    ----------
    failures : int
        Number of initial calls that raise a lock error.
    message : str
        Lock error text.
    """

    def __init__(self, failures: int, message: str) -> None:
        self._failures = failures
        self._message = message
        self._real = Graph.open
        self.attempts = 0

    def __call__(self, path: pathlib.Path) -> Graph:
        """Open a graph, raising a lock error for the first calls.

        Parameters
        ----------
        path : pathlib.Path
            Database to open.

        Returns
        -------
        Graph
            Open graph handle.

        Raises
        ------
        sqlite3.OperationalError
            While the configured failure count remains.
        """
        self.attempts += 1
        if self.attempts <= self._failures:
            raise sqlite3.OperationalError(self._message)
        return self._real(path)


class TestCrashHarness:
    """Verify crash reopen retries are bounded and preserve the failure."""

    def test_reopen_retries_a_transient_lock(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        monkeypatch.setattr(CrashHarness, "RETRY_ON_LOCK", True)
        flaky = _FlakyOpen(1, "database is locked")
        monkeypatch.setattr(Graph, "open", flaky)
        with CrashHarness.reopen(tmp_path / "grid.db") as graph:
            assert graph.check_integrity() == ()
        assert flaky.attempts == 2

    def test_reopen_reports_a_persistent_lock(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        monkeypatch.setattr(CrashHarness, "RETRY_ON_LOCK", True)
        monkeypatch.setattr(CrashHarness, "RETRY_ATTEMPTS", 2)
        monkeypatch.setattr(CrashHarness, "RETRY_DELAY", 0.0)
        flaky = _FlakyOpen(3, "database is locked")
        monkeypatch.setattr(Graph, "open", flaky)
        with (
            pytest.raises(sqlite3.OperationalError, match="locked"),
            CrashHarness.reopen(tmp_path / "grid.db"),
        ):
            pass
        assert flaky.attempts == 2


class TestCommitDurability:
    """Verify committed and uncommitted work across a hard termination."""

    def test_explicit_commit_survives_termination(self, tmp_path: pathlib.Path) -> None:
        """Reopen a database after a committed process is killed."""
        database = tmp_path / "grid.db"
        CrashHarness.run("commit", database, tmp_path / "ready")
        with CrashHarness.reopen(database) as graph:
            assert [node["designation"] for node in graph.find_nodes("Program")] == ["Tron"]

    def test_uncommitted_transaction_is_absent(self, tmp_path: pathlib.Path) -> None:
        """Discard a transaction that was open when the process was killed."""
        database = tmp_path / "grid.db"
        CrashHarness.run("transaction", database, tmp_path / "ready")
        with CrashHarness.reopen(database) as graph:
            assert list(graph.find_nodes("Program")) == []
            assert graph.check_integrity() == ()

    def test_convenience_write_survives_termination(self, tmp_path: pathlib.Path) -> None:
        """Reopen a database after a committed convenience write is killed."""
        database = tmp_path / "grid.db"
        CrashHarness.run("convenience", database, tmp_path / "ready")
        with CrashHarness.reopen(database) as graph:
            assert [node["designation"] for node in graph.find_nodes("Program")] == ["Tron"]

    def test_wal_recovery_and_integrity(self, tmp_path: pathlib.Path) -> None:
        """Recover the write-ahead log and pass the integrity check."""
        database = tmp_path / "grid.db"
        CrashHarness.run("commit", database, tmp_path / "ready")
        with CrashHarness.reopen(database) as graph:
            assert graph.journal_mode == "wal"
            assert graph.check_integrity() == ()
            assert [node["designation"] for node in graph.find_nodes("Program")] == ["Tron"]


class TestBackupCrash:
    """Verify backup termination leaves a usable source and destination."""

    @classmethod
    def populate(cls, path: pathlib.Path) -> None:
        """Create a small file-backed graph."""
        with Graph.open(path) as graph:
            tron = graph.add_node("Program", designation="Tron")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(tron, "TRUSTS", quorra)

    @classmethod
    def assert_source(cls, path: pathlib.Path) -> None:
        """Check the source content and integrity."""
        with CrashHarness.reopen(path) as graph:
            assert graph.check_integrity() == ()
            assert {node["designation"] for node in graph.find_nodes("Program")} == {
                "Tron",
                "Quorra",
            }

    @classmethod
    def assert_destination(cls, path: pathlib.Path) -> bool:
        """Check a destination if the backup reached it."""
        if not path.exists():
            return False
        with CrashHarness.reopen(path) as graph:
            assert graph.check_integrity() == ()
            assert {node["designation"] for node in graph.find_nodes("Program")} == {
                "Tron",
                "Quorra",
            }
        return True

    def test_source_unchanged_when_backup_starts(self, tmp_path: pathlib.Path) -> None:
        """Leave the source intact when termination interrupts a backup."""
        source = tmp_path / "source.db"
        destination = tmp_path / "backup.db"
        self.populate(source)
        CrashHarness.run(
            "backup-start",
            source,
            tmp_path / "ready",
            destination,
            delay=0.05,
        )
        self.assert_source(source)
        self.assert_destination(destination)

    def test_completed_backup_is_visible_after_termination(self, tmp_path: pathlib.Path) -> None:
        """Keep a complete backup when termination follows the copy."""
        source = tmp_path / "source.db"
        destination = tmp_path / "backup.db"
        self.populate(source)
        CrashHarness.run("backup-complete", source, tmp_path / "ready", destination)
        self.assert_source(source)
        assert self.assert_destination(destination)

    def test_read_only_backup_source_unchanged(self, tmp_path: pathlib.Path) -> None:
        """Keep a read-only source intact across termination."""
        source = tmp_path / "source.db"
        destination = tmp_path / "backup.db"
        self.populate(source)
        CrashHarness.run(
            "backup-readonly",
            source,
            tmp_path / "ready",
            destination,
            delay=0.05,
        )
        self.assert_source(source)
        self.assert_destination(destination)


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="FIFO crash tests require Linux named pipes",
)
class TestRestoreCrash:
    """Verify restore atomicity when the process dies mid-transaction."""

    HEADER: typing.ClassVar[bytes] = (
        b'{"kind":"header","format":"pygrafito-jsonl","version":2,"nodes":1,"relationships":0}\n'
    )

    @classmethod
    def fifo(cls, path: pathlib.Path) -> pathlib.Path:
        """Create a named pipe for a blocking snapshot."""
        os.mkfifo(path)
        return path

    @classmethod
    def assert_empty(cls, path: pathlib.Path) -> None:
        """Check that a restored target has no graph content."""
        with CrashHarness.reopen(path) as graph:
            assert list(graph.find_nodes()) == []
            assert graph.check_integrity() == ()

    def test_empty_target_after_termination(self, tmp_path: pathlib.Path) -> None:
        """Leave an empty target empty after a terminated restore."""
        target = tmp_path / "target.db"
        snapshot = self.fifo(tmp_path / "snapshot.jsonl")
        CrashHarness.run_fifo(
            "restore",
            target,
            tmp_path / "ready",
            snapshot,
            self.HEADER,
            "0",
        )
        self.assert_empty(target)

    def test_replace_target_after_termination(self, tmp_path: pathlib.Path) -> None:
        """Roll back the delete phase of a replaced restore."""
        target = tmp_path / "target.db"
        with Graph.open(target) as graph:
            graph.add_node("Program", designation="Rinzler")
        snapshot = self.fifo(tmp_path / "snapshot.jsonl")
        CrashHarness.run_fifo(
            "restore",
            target,
            tmp_path / "ready",
            snapshot,
            self.HEADER,
            "1",
        )
        with CrashHarness.reopen(target) as graph:
            assert [node["designation"] for node in graph.find_nodes("Program")] == ["Rinzler"]
            assert graph.check_integrity() == ()

    def test_no_partial_graph_after_termination(self, tmp_path: pathlib.Path) -> None:
        """Leave no partially restored node or relationship."""
        target = tmp_path / "target.db"
        snapshot = self.fifo(tmp_path / "snapshot.jsonl")
        CrashHarness.run_fifo(
            "restore",
            target,
            tmp_path / "ready",
            snapshot,
            self.HEADER,
            "0",
        )
        with CrashHarness.reopen(target) as graph:
            assert graph.query("MATCH (n:Program) RETURN n").rows == ()
            assert graph.check_integrity() == ()


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="FIFO crash tests require Linux named pipes",
)
class TestImportCrash:
    """Verify atomic and non-atomic import behavior across termination."""

    ROW: typing.ClassVar[bytes] = b'{"designation": "Tron"}\n'

    @classmethod
    def fifo(cls, path: pathlib.Path) -> pathlib.Path:
        """Create a named pipe for a blocking import source."""
        os.mkfifo(path)
        return path

    def test_atomic_import_is_rolled_back(self, tmp_path: pathlib.Path) -> None:
        """Leave no rows when an atomic import dies mid-transaction."""
        target = tmp_path / "target.db"
        rows = self.fifo(tmp_path / "rows.jsonl")
        CrashHarness.run_fifo(
            "importing",
            target,
            tmp_path / "ready",
            rows,
            self.ROW,
            "1",
        )
        with CrashHarness.reopen(target) as graph:
            assert list(graph.find_nodes("Program")) == []
            assert graph.check_integrity() == ()

    def test_non_atomic_import_keeps_committed_batch(self, tmp_path: pathlib.Path) -> None:
        """Keep the batch that committed before the process died."""
        target = tmp_path / "target.db"
        rows = self.fifo(tmp_path / "rows.jsonl")
        CrashHarness.run_fifo(
            "importing",
            target,
            tmp_path / "ready",
            rows,
            self.ROW,
            "0",
        )
        with CrashHarness.reopen(target) as graph:
            assert [node["designation"] for node in graph.find_nodes("Program")] == ["Tron"]
            assert graph.check_integrity() == ()
