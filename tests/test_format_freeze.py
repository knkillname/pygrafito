# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Freeze the schema, snapshot, and view versions with golden fixtures."""

import contextlib
import pathlib
import shutil
import sqlite3
import typing

import pytest

from pygrafito import Graph, UnsupportedSqliteError, ValidationError
from pygrafito.engine.interop import JsonLinesCodec
from pygrafito.storage.schema import Schema
from pygrafito.storage.views import Views


class Fixtures:
    """Paths and helpers for the checked-in version 2 fixtures."""

    ROOT: typing.ClassVar[pathlib.Path] = pathlib.Path(__file__).resolve().parent / "fixtures"
    DATABASE: typing.ClassVar[pathlib.Path] = ROOT / "golden-v2.db"
    SNAPSHOT: typing.ClassVar[pathlib.Path] = ROOT / "golden-v2.jsonl"

    @classmethod
    def database_copy(cls, directory: pathlib.Path) -> pathlib.Path:
        """Copy the golden database so a test never touches the fixture."""
        destination = directory / "golden-v2.db"
        shutil.copyfile(cls.DATABASE, destination)
        return destination

    @classmethod
    def version_one_database(cls, path: pathlib.Path) -> pathlib.Path:
        """Create an empty SQLite file that records schema version 1."""
        return cls.database_with_version(path, 1)

    @classmethod
    def version_three_database(cls, path: pathlib.Path) -> pathlib.Path:
        """Create an empty SQLite file that records schema version 3."""
        return cls.database_with_version(path, 3)

    @classmethod
    def database_with_version(cls, path: pathlib.Path, version: int) -> pathlib.Path:
        """Create an empty SQLite file with one recorded schema version."""
        with contextlib.closing(sqlite3.connect(path)) as connection:
            connection.execute(f"PRAGMA user_version = {version}")
            connection.commit()
        return path

    @classmethod
    def versioned_snapshot(cls, path: pathlib.Path, version: int) -> pathlib.Path:
        """Create a header-only snapshot with one declared version."""
        path.write_text(
            '{"kind":"header","format":"pygrafito-jsonl",'
            f'"version":{version},"nodes":0,"relationships":0}}\n',
            encoding="utf-8",
        )
        return path


class TestGoldenFormats(Fixtures):
    """Verify the checked-in version 2 database and snapshot."""

    def test_golden_database_content(self, tmp_path: pathlib.Path) -> None:
        """Open the golden database and check its TRON content."""
        with Graph.open(self.database_copy(tmp_path), readonly=True) as graph:
            assert graph.node(1)["designation"] == "Kevin Flynn"
            assert graph.node(1).labels == frozenset({"Program", "User"})
            assert graph.node(2)["designation"] == "Quorra"
            assert graph.node(2).labels == frozenset({"Program", "ISO"})
            assert graph.node(3)["designation"] == "Tron"
            assert graph.node(3).labels == frozenset({"Program"})
            assert graph.node(4).labels == frozenset()
            assert graph.relationship(1).labels == ("ALLIES_WITH",)
            assert graph.relationship(1).directed is True
            assert graph.relationship(2).start_id == 3
            assert graph.relationship(2).end_id == 3
            assert graph.relationship(3).directed is False
            assert graph.check_integrity() == ()

    def test_golden_database_export_matches_snapshot(self, tmp_path: pathlib.Path) -> None:
        """Export the golden database to the same canonical bytes."""
        exported = tmp_path / "exported.jsonl"
        with Graph.open(self.database_copy(tmp_path), readonly=True) as graph:
            graph.export_jsonl(exported)
        assert exported.read_bytes() == self.SNAPSHOT.read_bytes()

    def test_golden_snapshot_restores(self) -> None:
        """Restore the golden snapshot and check labels, direction, and self-loop."""
        with Graph.open(":memory:") as graph:
            summary = graph.restore_jsonl(self.SNAPSHOT)
            assert summary.nodes == 4
            assert summary.relationships == 3
            by_designation = {
                str(node["designation"]): node
                for node in graph.find_nodes("Program")
                if "designation" in node
            }
            assert set(by_designation) == {"Kevin Flynn", "Quorra", "Tron"}
            assert by_designation["Quorra"].labels == frozenset({"Program", "ISO"})
            relationships = list(graph.find_relationships())
            self_loop = next(
                relationship for relationship in relationships if relationship.labels == ("GUARDS",)
            )
            assert self_loop.start_id == self_loop.end_id
            assert (
                next(
                    relationship
                    for relationship in relationships
                    if relationship.labels == ("TRUSTS",)
                ).directed
                is False
            )
            assert graph.check_integrity() == ()

    def test_golden_snapshot_round_trip_is_byte_stable(self, tmp_path: pathlib.Path) -> None:
        """Restore and export the golden snapshot with identical bytes."""
        exported = tmp_path / "round-trip.jsonl"
        with Graph.open(":memory:") as graph:
            graph.restore_jsonl(self.SNAPSHOT)
            graph.export_jsonl(exported)
        assert exported.read_bytes() == self.SNAPSHOT.read_bytes()

    def test_golden_snapshot_header(self) -> None:
        """Keep the canonical version 2 header and record counts."""
        first_line = self.SNAPSHOT.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == (
            '{"kind":"header","format":"pygrafito-jsonl","version":2,"nodes":4,"relationships":3}'
        )

    def test_golden_view_version(self, tmp_path: pathlib.Path) -> None:
        """Publish version 2 in Graph.view_version and graph_meta."""
        database = self.database_copy(tmp_path)
        with Graph.open(database, readonly=True) as graph:
            assert graph.view_version == 2
        with contextlib.closing(
            sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        ) as connection:
            version = connection.execute(
                "SELECT value FROM graph_meta WHERE key = 'view_version'"
            ).fetchone()
            format_name = connection.execute(
                "SELECT value FROM graph_meta WHERE key = 'format'"
            ).fetchone()
        assert version == ("2",)
        assert format_name == ("pygrafito",)


class TestFrozenVersions:
    """Pin each format version explicitly."""

    def test_schema_version_is_two(self, tmp_path: pathlib.Path) -> None:
        """Keep the schema layout at version 2."""
        assert Schema.VERSION == 2
        database = Fixtures.database_copy(tmp_path)
        with contextlib.closing(
            sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        ) as connection:
            assert connection.execute("PRAGMA user_version").fetchone() == (2,)

    def test_snapshot_version_is_two(self) -> None:
        """Keep the snapshot format at version 2."""
        assert JsonLinesCodec.VERSION == 2

    def test_view_version_is_two(self, tmp_path: pathlib.Path) -> None:
        """Keep the published view version at version 2."""
        assert Views.VERSION == 2
        with Graph.open(Fixtures.database_copy(tmp_path), readonly=True) as graph:
            assert graph.view_version == 2


class TestVersionRefusal:
    """Verify that unsupported layouts are refused without migration."""

    @pytest.mark.parametrize("version", [1, 3])
    def test_database_version_is_refused(self, tmp_path: pathlib.Path, version: int) -> None:
        """Reject a database version other than 2 and name the export path."""
        path = tmp_path / f"version-{version}.db"
        if version == 1:
            Fixtures.version_one_database(path)
        else:
            Fixtures.version_three_database(path)
        before = path.read_bytes()
        with pytest.raises(UnsupportedSqliteError) as caught:
            Graph.open(path)
        message = str(caught.value)
        assert f"version {version}" in message
        assert "requires version 2" in message
        assert "export" in message
        assert path.read_bytes() == before

    def test_future_database_is_refused_read_only(self, tmp_path: pathlib.Path) -> None:
        """Reject a future version on a read-only open without changing the file."""
        path = Fixtures.version_three_database(tmp_path / "future.db")
        before = path.read_bytes()
        with pytest.raises(UnsupportedSqliteError, match="read-only"):
            Graph.open(path, readonly=True)
        assert path.read_bytes() == before

    @pytest.mark.parametrize("version", [1, 3])
    def test_snapshot_version_is_refused(self, tmp_path: pathlib.Path, version: int) -> None:
        """Reject a snapshot version other than 2 and leave the target empty."""
        snapshot = Fixtures.versioned_snapshot(tmp_path / f"version-{version}.jsonl", version)
        before = snapshot.read_bytes()
        with (
            Graph.open(":memory:") as graph,
            pytest.raises(
                ValidationError,
                match=f"unsupported snapshot version {version}; expected 2",
            ),
        ):
            graph.restore_jsonl(snapshot)
        with Graph.open(":memory:") as graph:
            assert list(graph.find_nodes()) == []
        assert snapshot.read_bytes() == before
