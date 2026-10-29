# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the declared index API."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from pygrafito import (
    Graph,
    GraphClosedError,
    Index,
    IndexKind,
    NotFoundError,
    TransactionError,
    ValidationError,
)
from pygrafito.model import Value


class _IndexTestCase:
    """Provide an in-memory graph handle."""

    @pytest.fixture
    def graph(self) -> Iterator[Graph]:
        """Yield an open in-memory graph.

        Yields
        ------
        Graph
            Graph under test.
        """
        with Graph.open(":memory:") as graph:
            yield graph


class TestDeclaration(_IndexTestCase):
    """Verify index creation, listing, and removal."""

    def test_create_node_index(self, graph: Graph) -> None:
        index = graph.create_node_index("cycles")
        assert index == Index(IndexKind.NODE, "cycles")
        assert graph.indexes() == (index,)

    def test_create_relationship_index(self, graph: Graph) -> None:
        index = graph.create_relationship_index("since_cycle")
        assert index == Index(IndexKind.RELATIONSHIP, "since_cycle")
        assert graph.indexes() == (index,)

    def test_declaration_is_idempotent(self, graph: Graph) -> None:
        first = graph.create_node_index("cycles")
        second = graph.create_node_index("cycles")
        assert first == second
        assert graph.indexes() == (first,)

    def test_indexes_are_ordered(self, graph: Graph) -> None:
        relationship = graph.create_relationship_index("since_cycle")
        designation = graph.create_node_index("designation")
        cycles = graph.create_node_index("cycles")
        assert graph.indexes() == (cycles, designation, relationship)

    def test_drop_index(self, graph: Graph) -> None:
        index = graph.create_node_index("cycles")
        graph.drop_index(index)
        assert graph.indexes() == ()

    def test_drop_missing_index(self, graph: Graph) -> None:
        with pytest.raises(NotFoundError):
            graph.drop_index(Index(IndexKind.NODE, "cycles"))

    def test_empty_key_rejected(self, graph: Graph) -> None:
        with pytest.raises(ValidationError):
            graph.create_node_index("")
        assert graph.indexes() == ()

    def test_indexes_do_not_change_content(self, graph: Graph) -> None:
        kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        before = dict(kevin)
        graph.create_node_index("cycles")
        assert dict(graph.node(kevin.id)) == before
        assert [node.id for node in graph.find_nodes("Program")] == [kevin.id]

    @pytest.mark.parametrize("key", ['a"b', "a\nb"])
    def test_special_key_is_reported_and_matchable(self, graph: Graph, key: str) -> None:
        index = graph.create_node_index(key)
        tron = graph.add_node("Program", **{key: "Tron"})
        assert graph.indexes() == (index,)
        assert [node.id for node in graph.find_nodes("Program", **{key: "Tron"})] == [tron.id]
        graph.drop_index(index)
        assert graph.indexes() == ()

    def test_indexed_equality_returns_only_the_stored_type(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Tron", state=True)
        graph.add_node("Program", designation="Quorra", state=1)
        graph.add_node("Program", designation="Rinzler", state="true")
        graph.add_node("Program", designation="Yori", state=["true"])
        graph.create_node_index("state")
        cases: list[tuple[Value, str]] = [
            (True, "Tron"),
            (1, "Quorra"),
            ("true", "Rinzler"),
            (["true"], "Yori"),
        ]
        for value, expected in cases:
            found = [node["designation"] for node in graph.find_nodes("Program", state=value)]
            assert found == [expected]


class TestTransactionGuard(_IndexTestCase):
    """Verify index changes are rejected inside an explicit transaction."""

    def test_create_rejected(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            transaction.add_node("Program", designation="Quorra")
            with pytest.raises(TransactionError):
                graph.create_node_index("cycles")
        assert graph.indexes() == ()

    def test_drop_rejected(self, graph: Graph) -> None:
        index = graph.create_node_index("cycles")
        with graph.transaction() as transaction:
            transaction.add_node("Program", designation="Tron")
            with pytest.raises(TransactionError):
                graph.drop_index(index)
        assert graph.indexes() == (index,)


class TestClosedHandle(_IndexTestCase):
    """Verify index operations reject a closed graph."""

    def test_create_after_close(self) -> None:
        graph = Graph.open(":memory:")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.create_node_index("cycles")

    def test_list_after_close(self) -> None:
        graph = Graph.open(":memory:")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.indexes()


class TestStatistics(_IndexTestCase):
    """Verify planning statistics refresh without changing results."""

    def test_declaration_records_statistics(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        graph.create_node_index("cycles")
        row = graph._database.connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'sqlite_stat1'"
        ).fetchone()
        assert row == ("sqlite_stat1",)

    def test_statistics_do_not_change_results(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        graph.add_node("Program", designation="Quorra", cycles=37)
        statement = (
            "MATCH (n:Program) WHERE n.cycles >= 36 RETURN n.designation AS name ORDER BY name"
        )
        before = [row["name"] for row in graph.query(statement)]
        graph.create_node_index("cycles")
        after = [row["name"] for row in graph.query(statement)]
        assert before == after == ["Kevin Flynn", "Quorra"]

    def test_close_and_reopen_keeps_indexes(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            graph.add_node("Program", designation="Tron")
            graph.create_node_index("designation")
        with Graph.open(path) as graph:
            assert graph.indexes() == (Index(IndexKind.NODE, "designation"),)


class TestMaintenance(_IndexTestCase):
    """Verify indexes stay consistent with stored data."""

    def test_property_update(self, graph: Graph) -> None:
        kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        graph.create_node_index("cycles")
        graph.set_properties(kevin, cycles=37)
        assert list(graph.find_nodes("Program", cycles=36)) == []
        assert [node.id for node in graph.find_nodes("Program", cycles=37)] == [kevin.id]

    def test_property_removal(self, graph: Graph) -> None:
        kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        graph.create_node_index("cycles")
        graph.set_properties(kevin, cycles=None)
        assert list(graph.find_nodes("Program", cycles=36)) == []

    def test_element_deletion(self, graph: Graph) -> None:
        kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        graph.create_node_index("cycles")
        graph.delete(kevin)
        assert list(graph.find_nodes("Program", cycles=36)) == []
        assert graph.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"] == 0

    def test_rolled_back_write(self, graph: Graph) -> None:
        graph.create_node_index("cycles")
        with pytest.raises(RuntimeError):
            self.write_and_fail(graph)
        assert list(graph.find_nodes("Program", cycles=40)) == []

    @staticmethod
    def write_and_fail(graph: Graph) -> None:
        with graph.transaction() as transaction:
            transaction.add_node("Program", designation="Clu", cycles=40)
            raise RuntimeError

    def test_relationship_property_update(self, graph: Graph) -> None:
        kevin = graph.add_node("Program", designation="Kevin Flynn")
        quorra = graph.add_node("Program", designation="Quorra")
        allies = graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
        graph.create_relationship_index("since_cycle")
        graph.set_properties(allies, since_cycle=2021)
        assert list(graph.find_relationships("ALLIES_WITH", since_cycle=2020)) == []
        found = list(graph.find_relationships("ALLIES_WITH", since_cycle=2021))
        assert [relationship.id for relationship in found] == [allies.id]

    def test_in_memory_index_survives_data_changes(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        index = graph.create_node_index("cycles")
        graph.add_node("Program", designation="Quorra", cycles=37)
        assert graph.indexes() == (index,)

    def test_reopened_index_still_matches(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            graph.add_node("Program", designation="Tron", cycles=40)
            graph.create_node_index("cycles")
        with Graph.open(path) as graph:
            assert graph.indexes() == (Index(IndexKind.NODE, "cycles"),)
            found = list(graph.find_nodes("Program", cycles=40))
            assert [node["designation"] for node in found] == ["Tron"]
