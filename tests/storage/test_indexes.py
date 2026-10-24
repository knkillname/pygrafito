# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for declared index identity and discovery."""

from collections.abc import Iterator

import pytest

from pygrafito.model import Index, IndexKind, NotFoundError
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.indexes import IndexRegistry
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository


class _RegistryTestCase:
    """Provide an index registry on a fresh in-memory database."""

    @pytest.fixture
    def database(self) -> Iterator[Database]:
        """Yield an open in-memory database.

        Yields
        ------
        Database
            Database used by the test.
        """
        database = Database(":memory:")
        try:
            yield database
        finally:
            database.close()

    @pytest.fixture
    def registry(self, database: Database) -> IndexRegistry:
        """Return a registry over the test database.

        Parameters
        ----------
        database : Database
            Open database.

        Returns
        -------
        IndexRegistry
            Registry under test.
        """
        return IndexRegistry(database.connection, PropertyCodec())


class TestNameEncoding(_RegistryTestCase):
    """Verify declared index names round-trip and stay recognizable."""

    @pytest.mark.parametrize(
        "key",
        [
            "cycles",
            "a.b",
            "a b",
            "ñ✓",
            'quo"te',
            "back\\slash",
            "it's",
            "'); DROP TABLE nodes; --",
        ],
    )
    def test_round_trip(self, key: str) -> None:
        index = Index(IndexKind.NODE, key)
        assert IndexRegistry.parse_name(IndexRegistry.name(index)) == index

    def test_kind_is_encoded(self) -> None:
        node_name = IndexRegistry.name(Index(IndexKind.NODE, "cycles"))
        relationship_name = IndexRegistry.name(Index(IndexKind.RELATIONSHIP, "cycles"))
        assert node_name != relationship_name
        assert node_name.startswith("pygrafito_idx_node_")
        assert relationship_name.startswith("pygrafito_idx_relationship_")

    @pytest.mark.parametrize(
        "name",
        [
            "node_labels_by_label",
            "rel_by_src",
            "rel_by_type",
            "pygrafito_idx_node_",
            "pygrafito_idx_node_zz",
            "pygrafito_idx_agent_6379636c6573",
            "sqlite_autoindex_nodes_1",
        ],
    )
    def test_foreign_names_ignored(self, name: str) -> None:
        assert IndexRegistry.parse_name(name) is None


class TestDiscovery(_RegistryTestCase):
    """Verify declared indexes are discovered from SQLite metadata."""

    def test_empty_database(self, registry: IndexRegistry) -> None:
        assert registry.all() == ()

    def test_lists_declared_indexes_in_order(self, registry: IndexRegistry) -> None:
        relationship = Index(IndexKind.RELATIONSHIP, "since_cycle")
        designation = Index(IndexKind.NODE, "designation")
        cycles = Index(IndexKind.NODE, "cycles")
        for index in (relationship, designation, cycles):
            registry.create(index)
        assert registry.all() == (cycles, designation, relationship)

    def test_ignores_unrelated_indexes(
        self,
        database: Database,
        registry: IndexRegistry,
    ) -> None:
        database.connection.execute("CREATE INDEX custom_lookup ON nodes (id)")
        registry.create(Index(IndexKind.NODE, "cycles"))
        assert registry.all() == (Index(IndexKind.NODE, "cycles"),)

    def test_exists(self, registry: IndexRegistry) -> None:
        index = Index(IndexKind.NODE, "cycles")
        assert not registry.exists(index)
        registry.create(index)
        assert registry.exists(index)

    def test_create_is_idempotent(self, registry: IndexRegistry) -> None:
        index = Index(IndexKind.NODE, "cycles")
        registry.create(index)
        registry.create(index)
        assert registry.all() == (index,)


class TestMaintenance(_RegistryTestCase):
    """Verify creation and removal against a populated graph."""

    def test_drop_removes_index(
        self,
        database: Database,
        registry: IndexRegistry,
    ) -> None:
        node_repository = NodeRepository(database.connection, PropertyCodec())
        node_repository.create(("Program",), {"cycles": 36})
        index = Index(IndexKind.NODE, "cycles")
        registry.create(index)
        registry.drop(index)
        assert registry.all() == ()

    def test_drop_missing_raises(self, registry: IndexRegistry) -> None:
        with pytest.raises(NotFoundError):
            registry.drop(Index(IndexKind.NODE, "cycles"))

    def test_ddl_covers_both_element_kinds(self, registry: IndexRegistry) -> None:
        node_ddl = registry.ddl(Index(IndexKind.NODE, "cycles"))
        relationship_ddl = registry.ddl(Index(IndexKind.RELATIONSHIP, "since_cycle"))
        assert " ON nodes " in node_ddl
        assert " ON relationships " in relationship_ddl
        assert "json_extract(props, '$.\"cycles\"')" in node_ddl
        assert "json_type(props, '$.\"since_cycle\"')" in relationship_ddl

    def test_declared_indexes_apply_to_populated_tables(
        self,
        database: Database,
        registry: IndexRegistry,
    ) -> None:
        codec = PropertyCodec()
        node_repository = NodeRepository(database.connection, codec)
        relationship_repository = RelationshipRepository(database.connection, codec)
        first = node_repository.create(("Program",), {"cycles": 36})
        second = node_repository.create(("Program",), {"cycles": 37})
        relationship_repository.create(first.id, "ALLIES_WITH", second.id, {"since_cycle": 2020})
        registry.create(Index(IndexKind.NODE, "cycles"))
        registry.create(Index(IndexKind.RELATIONSHIP, "since_cycle"))
        assert len(registry.all()) == 2
