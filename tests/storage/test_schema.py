# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for connection pragmas and schema bootstrap."""

import sqlite3
import typing
from collections.abc import Sequence
from pathlib import Path
from sqlite3 import Connection, OperationalError

import pytest

from pygrafito.model import (
    NotFoundError,
    UnsupportedSqliteError,
)
from pygrafito.storage.connection import Database
from pygrafito.storage.schema import Schema


class _BrokenJsonCursor:
    """Cursor stand-in that fails a JSON query."""

    def fetchone(self) -> tuple[object, ...] | None:
        message = "no such function: json_valid"
        raise OperationalError(message)


class _BrokenJsonConnection:
    """Connection stand-in without JSON1 support."""

    def execute(
        self,
        statement: str,
        parameters: Sequence[object] = (),
    ) -> _BrokenJsonCursor:
        message = "no such function: json_valid"
        raise OperationalError(message)


class _WrongJsonCursor:
    """Cursor stand-in returning unexpected JSON metadata."""

    def fetchone(self) -> tuple[object, ...] | None:
        return (1, "text")


class _WrongJsonConnection:
    """Connection stand-in reporting unexpected JSON metadata."""

    def execute(
        self,
        statement: str,
        parameters: Sequence[object] = (),
    ) -> _WrongJsonCursor:
        return _WrongJsonCursor()


class _EmptyCursor:
    """Cursor stand-in with no rows."""

    def fetchone(self) -> tuple[object, ...] | None:
        return None


class _EmptyConnection:
    """Connection stand-in returning no pragma rows."""

    def execute(
        self,
        statement: str,
        parameters: Sequence[object] = (),
    ) -> _EmptyCursor:
        return _EmptyCursor()


class _TextVersionCursor:
    """Cursor stand-in reporting a text schema version."""

    def fetchone(self) -> tuple[object, ...] | None:
        return ("one",)


class _TextVersionConnection:
    """Connection stand-in reporting a text schema version."""

    def execute(
        self,
        statement: str,
        parameters: Sequence[object] = (),
    ) -> _TextVersionCursor:
        return _TextVersionCursor()


class TestDatabasePragmas:
    """Verify the configured connection pragmas."""

    def test_memory_pragmas(self) -> None:
        database = Database(":memory:")
        try:
            row = database.connection.execute("PRAGMA foreign_keys").fetchone()
            assert row == (1,)
            row = database.connection.execute("PRAGMA busy_timeout").fetchone()
            assert row == (Database.BUSY_TIMEOUT_MS,)
            row = database.connection.execute("PRAGMA journal_mode").fetchone()
            assert row is not None
            assert str(row[0]).lower() == "memory"
            assert database.location == ":memory:"
        finally:
            database.close()

    def test_file_pragmas(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.db"
        database = Database(path)
        try:
            row = database.connection.execute("PRAGMA foreign_keys").fetchone()
            assert row == (1,)
            row = database.connection.execute("PRAGMA journal_mode").fetchone()
            assert row is not None
            assert str(row[0]).lower() == "wal"
            assert database.connection.isolation_level is None
        finally:
            database.close()

    def test_close_is_idempotent(self) -> None:
        database = Database(":memory:")
        database.close()
        database.close()

    def test_close_rolls_back_open_transaction(self) -> None:
        database = Database(":memory:")
        database.connection.execute("BEGIN IMMEDIATE")
        database.close()

    def test_missing_file_rejected_when_not_creating(self, tmp_path: Path) -> None:
        with pytest.raises(NotFoundError):
            Database(tmp_path / "absent.db", create=False)

    def test_existing_file_can_be_opened_without_creating(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "graph.db"
        Database(path).close()
        database = Database(path, create=False)
        database.close()


class TestSchemaBootstrap:
    """Verify schema creation and version reporting."""

    def test_bootstrap_sets_version_and_tables(self) -> None:
        database = Database(":memory:")
        try:
            store = Schema(database.connection)
            assert store.version() == Schema.VERSION
            rows = database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
            names = {str(row[0]) for row in rows}
            assert names == {"node_labels", "nodes", "relationships"}
            indexes = database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            index_names = {str(row[0]) for row in indexes}
            assert index_names == {"node_labels_by_label", "rel_by_dst", "rel_by_src"}
        finally:
            database.close()

    def test_repeat_bootstrap_is_idempotent(self) -> None:
        database = Database(":memory:")
        try:
            store = Schema(database.connection)
            store.bootstrap()
            store.bootstrap()
            assert store.version() == Schema.VERSION
        finally:
            database.close()

    def test_newer_schema_version_rejected(self) -> None:
        database = Database(":memory:")
        try:
            database.connection.execute(f"PRAGMA user_version = {Schema.VERSION + 1}")
            with pytest.raises(UnsupportedSqliteError):
                Schema(database.connection).bootstrap()
        finally:
            database.close()

    def test_version_zero_before_bootstrap(self) -> None:
        database = sqlite3.connect(":memory:")
        try:
            assert Schema(database).version() == 0
        finally:
            database.close()

    def test_missing_version_row_reports_zero(self) -> None:
        empty = typing.cast(Connection, _EmptyConnection())
        assert Schema(empty).version() == 0

    def test_non_integer_version_rejected(self) -> None:
        text = typing.cast(Connection, _TextVersionConnection())
        with pytest.raises(UnsupportedSqliteError):
            Schema(text).version()

    def test_schema_persists_after_reopen(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.db"
        first = Database(path)
        first.close()
        second = Database(path)
        try:
            assert Schema(second.connection).version() == Schema.VERSION
        finally:
            second.close()


class TestJsonSupport:
    """Verify SQLite JSON1 compatibility checks."""

    def test_current_runtime_supported(self) -> None:
        database = Database(":memory:")
        try:
            Schema.verify_json_support(database.connection)
        finally:
            database.close()

    def test_older_runtime_rejected(self) -> None:
        database = Database(":memory:")
        try:
            with pytest.raises(UnsupportedSqliteError):
                Schema.verify_json_support(database.connection, (3, 37, 0))
            with pytest.raises(UnsupportedSqliteError):
                Schema.verify_json_support(
                    database.connection,
                    (
                        Schema.MINIMUM_SQLITE_VERSION[0],
                        Schema.MINIMUM_SQLITE_VERSION[1] - 1,
                        Schema.MINIMUM_SQLITE_VERSION[2],
                    ),
                )
        finally:
            database.close()

    def test_missing_json_functions_rejected(self) -> None:
        broken = typing.cast(Connection, _BrokenJsonConnection())
        with pytest.raises(UnsupportedSqliteError):
            Schema.verify_json_support(broken, (3, 45, 0))

    def test_unexpected_json_metadata_rejected(self) -> None:
        wrong = typing.cast(Connection, _WrongJsonConnection())
        with pytest.raises(UnsupportedSqliteError):
            Schema.verify_json_support(wrong, (3, 45, 0))
