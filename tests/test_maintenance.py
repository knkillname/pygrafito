# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for database backup and integrity reporting."""

import sqlite3
from pathlib import Path

import pytest

from pygrafito import Graph, TransactionError, ValidationError


class TestBackup:
    """Verify consistent copies of a live database."""

    @pytest.fixture
    def populated(self, tmp_path: Path) -> Path:
        """Create a file-backed graph with nodes and a relationship.

        Parameters
        ----------
        tmp_path : Path
            Temporary directory for the database file.

        Yields
        ------
        Path
            Path of the open database.
        """
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node("Program", "ISO", designation="Quorra", cycles=37)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
            return path

    def test_backup_copies_content(self, populated: Path, tmp_path: Path) -> None:
        """A backup opens with the same nodes, labels, relationships, and properties."""
        destination = tmp_path / "backup.db"
        with Graph.open(populated) as graph:
            written = graph.backup_to(destination)

        assert written == destination
        with Graph.open(destination) as copy:
            assert copy.node(2)["designation"] == "Quorra"
            assert copy.node(2).labels == frozenset({"Program", "ISO"})
            relationship = copy.relationship(1)
            assert relationship.labels == ("ALLIES_WITH",)
            assert relationship["since_cycle"] == 2020

    def test_existing_destination_is_refused(self, populated: Path, tmp_path: Path) -> None:
        """An existing destination is never overwritten."""
        destination = tmp_path / "backup.db"
        destination.write_text("keep me", encoding="utf-8")
        with Graph.open(populated) as graph, pytest.raises(ValidationError):
            graph.backup_to(destination)

        assert destination.read_text(encoding="utf-8") == "keep me"

    def test_active_transaction_is_refused(self, populated: Path, tmp_path: Path) -> None:
        """A backup cannot run inside an explicit transaction."""
        destination = tmp_path / "backup.db"
        with Graph.open(populated) as graph:
            active = graph.transaction().begin()
            with pytest.raises(TransactionError):
                graph.backup_to(destination)
            active.add_node("Program", designation="Tron")
            active.rollback()

        assert not destination.exists()
        with Graph.open(populated) as graph:
            assert list(graph.find_nodes("Program", designation="Tron")) == []

    def test_version_two_labels_and_direction_survive_backup(self, tmp_path: Path) -> None:
        """A fresh version 2 graph keeps labels, direction, and integrity."""
        path = tmp_path / "grid.db"
        backup = tmp_path / "backup.db"
        snapshot = tmp_path / "grid.jsonl"
        with Graph.open(path) as graph:
            first = graph.add_node("Program", designation="Tron")
            second = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(
                first,
                ["ALLIES_WITH", "TRUSTS"],
                second,
                directed=False,
                since=2020,
            )
            graph.backup_to(backup)
            assert graph.check_integrity() == ()
            assert graph.export_jsonl(snapshot).relationships == 1

        with Graph.open(backup) as copy:
            relationship = next(iter(copy.find_relationships(directed=False)))
            assert relationship.labels == ("ALLIES_WITH", "TRUSTS")
            assert copy.check_integrity() == ()

    def test_read_only_source(self, populated: Path, tmp_path: Path) -> None:
        """A read-only handle can still write a backup copy."""
        destination = tmp_path / "backup.db"
        with Graph.open(populated, readonly=True) as graph:
            graph.backup_to(destination)

        with Graph.open(destination) as copy:
            assert copy.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"] == 2


class TestIntegrity:
    """Verify structural integrity reporting."""

    @pytest.fixture
    def populated(self, tmp_path: Path) -> Path:
        """Create a healthy file-backed graph.

        Parameters
        ----------
        tmp_path : Path
            Temporary directory for the database file.

        Yields
        ------
        Path
            Path of the closed database.
        """
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            tron = graph.add_node("Program", designation="Tron")
            rinzler = graph.add_node("Program", designation="Rinzler")
            graph.add_relationship(tron, "TRUSTS", rinzler)
        return path

    def test_healthy_store(self, populated: Path) -> None:
        """A healthy store reports no problems."""
        with Graph.open(populated) as graph:
            assert graph.check_integrity() == ()

    def test_read_only_store(self, populated: Path) -> None:
        """A read-only handle can report integrity."""
        with Graph.open(populated, readonly=True) as graph:
            assert graph.check_integrity() == ()

    def test_foreign_key_violation(self, populated: Path) -> None:
        """A dangling relationship is reported."""
        connection = sqlite3.connect(populated)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "INSERT INTO relationships (src, dst, directed, props) VALUES (1, 999, 1, '{}')"
            )
            connection.commit()
        finally:
            connection.close()

        with Graph.open(populated) as graph:
            problems = graph.check_integrity()

        assert problems
        assert any("foreign key" in problem for problem in problems)
