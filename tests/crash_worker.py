# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Subprocess worker for crash and recovery tests."""

import pathlib
import sys
import time

from pygrafito import Graph


class CrashWorker:
    """Perform one graph operation and wait to be terminated."""

    IMPORT_STATEMENT: str = "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})"

    @classmethod
    def main(cls) -> None:
        """Dispatch one action from the command line."""
        action, database, ready, *arguments = sys.argv[1:]
        method = getattr(cls, action.replace("-", "_"))
        method(pathlib.Path(database), pathlib.Path(ready), *arguments)

    @classmethod
    def commit(cls, database: pathlib.Path, ready: pathlib.Path) -> None:
        """Commit an explicit transaction and wait for termination."""
        with Graph.open(database) as graph:
            with graph.transaction() as transaction:
                transaction.add_node("Program", designation="Tron")
            cls._signal(ready)
            cls._wait()

    @classmethod
    def convenience(cls, database: pathlib.Path, ready: pathlib.Path) -> None:
        """Commit a convenience write and wait for termination."""
        with Graph.open(database) as graph:
            graph.add_node("Program", designation="Tron")
            cls._signal(ready)
            cls._wait()

    @classmethod
    def transaction(cls, database: pathlib.Path, ready: pathlib.Path) -> None:
        """Leave an explicit transaction open and wait for termination."""
        with Graph.open(database) as graph:
            active = graph.transaction().begin()
            active.add_node("Program", designation="Tron")
            cls._signal(ready)
            cls._wait()

    @classmethod
    def backup_start(
        cls,
        database: pathlib.Path,
        ready: pathlib.Path,
        destination: pathlib.Path,
    ) -> None:
        """Signal immediately before starting a backup."""
        with Graph.open(database) as graph:
            cls._signal(ready)
            graph.backup_to(destination)
            cls._wait()

    @classmethod
    def backup_complete(
        cls,
        database: pathlib.Path,
        ready: pathlib.Path,
        destination: pathlib.Path,
    ) -> None:
        """Complete a backup and then wait for termination."""
        with Graph.open(database) as graph:
            graph.backup_to(destination)
            cls._signal(ready)
            cls._wait()

    @classmethod
    def backup_readonly(
        cls,
        database: pathlib.Path,
        ready: pathlib.Path,
        destination: pathlib.Path,
    ) -> None:
        """Start a backup from a read-only handle."""
        with Graph.open(database, readonly=True) as graph:
            cls._signal(ready)
            graph.backup_to(destination)
            cls._wait()

    @classmethod
    def restore(
        cls,
        database: pathlib.Path,
        ready: pathlib.Path,
        snapshot: pathlib.Path,
        replace: str,
    ) -> None:
        """Start a restore from a blocking snapshot."""
        with Graph.open(database) as graph:
            cls._signal(ready)
            graph.restore_jsonl(snapshot, replace=replace == "1")
            cls._wait()

    @classmethod
    def importing(
        cls,
        database: pathlib.Path,
        ready: pathlib.Path,
        rows: pathlib.Path,
        atomic: str,
    ) -> None:
        """Start an import from a blocking JSONL source."""
        with Graph.open(database) as graph:
            cls._signal(ready)
            graph.import_file(
                rows,
                cls.IMPORT_STATEMENT,
                format="jsonl",
                batch_size=1,
                atomic=atomic == "1",
            )
            cls._wait()

    @classmethod
    def _signal(cls, ready: pathlib.Path) -> None:
        """Tell the parent that the operation may begin."""
        ready.write_text("ready", encoding="utf-8")

    @classmethod
    def _wait(cls) -> None:
        """Wait long enough for the parent to terminate the process."""
        time.sleep(60)


if __name__ == "__main__":
    CrashWorker.main()
