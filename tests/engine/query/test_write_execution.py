# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Execution tests for write clauses and their mutation semantics."""

import pathlib
import sqlite3
import typing
import unittest.mock
from collections.abc import Iterator

import pytest

import pygrafito
from pygrafito import (
    Graph,
    GraphClosedError,
    MutationSummary,
    QueryExecutionError,
    TransactionError,
)
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import Node, Path
from pygrafito.storage.nodes import NodeRepository


@pytest.fixture
def graph() -> Iterator[Graph]:
    with Graph.open(":memory:") as graph:
        kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        quorra = graph.add_node("Program", designation="Quorra", cycles=37)
        tron = graph.add_node("Program", designation="Tron", cycles=40)
        rinzler = graph.add_node("Program", designation="Rinzler")
        graph.add_node("Program", designation="Clu")
        graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
        graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2021)
        graph.add_relationship(kevin, "ALLIES_WITH", tron)
        graph.add_relationship(quorra, "ALLIES_WITH", tron)
        graph.add_relationship(tron, "TRUSTS", kevin)
        graph.add_relationship(rinzler, "GUARDS", rinzler)
        yield graph


class TestCreateClause:
    """Verify CREATE creation, binding, and cardinality."""

    def test_map_property_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError, match="property value"):
            graph.query("INSERT (n:Program {metadata: {role: 'system'}})")
        assert len(list(graph.find_nodes("Program"))) == 5

    def test_create_standalone_node_and_return(self, graph: Graph) -> None:
        result = graph.query(
            "CREATE (n:Program {designation: 'Quorra', cycles: 37}) RETURN n.designation AS name"
        )
        assert result.columns == ("name",)
        assert [row["name"] for row in result] == ["Quorra"]
        assert result.summary.created_nodes == 1

    def test_create_without_return_is_empty(self, graph: Graph) -> None:
        result = graph.query("CREATE (n:Program {designation: 'Sam Flynn'})")
        assert result.columns == ()
        assert list(result) == []
        assert result.summary.created_nodes == 1
        assert len(list(graph.find_nodes("Program", designation="Sam Flynn"))) == 1

    def test_create_runs_once_per_match_row(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) CREATE (m:Program {designation: 'ISO'})")
        assert result.summary.created_nodes == 5

    def test_create_relationship_between_bound_nodes(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'})-[x:ALLIES_WITH]->(b) "
            "CREATE (a)-[r:TRUSTS {since_cycle: 2020}]->(b)"
        )
        assert result.summary.created_relationships == 3
        assert result.summary.created_nodes == 0

    def test_create_never_matches(self, graph: Graph) -> None:
        statement = "CREATE (n:Program {designation: 'Quorra'})"
        graph.query(statement)
        graph.query(statement)
        assert len(list(graph.find_nodes("Program", designation="Quorra"))) == 3

    def test_create_ignores_null_properties(self, graph: Graph) -> None:
        graph.query("CREATE (n:Program {designation: 'Quorra', cycles: null})")
        result = graph.query(
            "MATCH (n:Program {designation: 'Quorra'}) WHERE n.cycles IS NULL "
            "RETURN count(*) AS total"
        )
        assert result.rows[0]["total"] == 1


class TestSetAndRemoveClauses:
    """Verify property and label mutation."""

    def test_set_property(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = 38")
        assert result.summary.properties_set == 1
        quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
        assert quorra["cycles"] == 38

    def test_set_from_expression(self, graph: Graph) -> None:
        graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = n.cycles + 1")
        quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
        assert quorra["cycles"] == 38

    def test_set_null_removes_property(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = null")
        quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
        assert "cycles" not in quorra
        assert result.summary.properties_removed == 1

    def test_set_adds_label(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n:SystemMonitor")
        quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
        assert quorra.labels == frozenset({"Program", "SystemMonitor"})
        assert result.summary.labels_added == 1

    def test_set_relationship_property(self, graph: Graph) -> None:
        graph.query("MATCH ()-[r:TRUSTS]->() SET r.since_cycle = 2020")
        relationship = next(iter(graph.find_relationships("TRUSTS")))
        assert relationship["since_cycle"] == 2020

    def test_remove_property(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Quorra'}) REMOVE n.cycles")
        quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
        assert "cycles" not in quorra
        assert result.summary.properties_removed == 1

    def test_remove_absent_property_is_a_noop(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Clu'}) REMOVE n.cycles")
        clu = next(iter(graph.find_nodes("Program", designation="Clu")))
        assert "cycles" not in clu
        assert result.summary.properties_removed == 1

    def test_remove_label(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Quorra'}) REMOVE n:Program")
        quorra = next(iter(graph.find_nodes(designation="Quorra")))
        assert quorra.labels == frozenset()
        assert result.summary.labels_removed == 1


class TestDeleteClause:
    """Verify deletion, protection, and detaching."""

    def test_delete_relationship(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'})-[r:ALLIES_WITH]->(b) DELETE r"
        )
        assert result.summary.deleted_relationships == 3
        assert len(list(graph.find_relationships("ALLIES_WITH"))) == 1

    def test_delete_disconnected_node(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Clu'}) DELETE n")
        assert result.summary.deleted_nodes == 1
        assert list(graph.find_nodes("Program", designation="Clu")) == []

    def test_delete_connected_node_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("MATCH (n:Program {designation: 'Kevin Flynn'}) DELETE n")
        assert len(list(graph.find_nodes("Program", designation="Kevin Flynn"))) == 1

    def test_detach_delete_removes_incident_relationships(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Tron'}) DETACH DELETE n")
        assert result.summary.deleted_nodes == 1
        assert result.summary.deleted_relationships == 3
        assert list(graph.find_nodes("Program", designation="Tron")) == []

    def test_deleted_node_keeps_its_snapshot_in_return(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Clu'}) DELETE n RETURN n.designation AS name"
        )
        assert [row["name"] for row in result] == ["Clu"]


class TestMutationCardinality:
    """Verify deduplication across diamond, cycle, parallel, and self-loop rows."""

    def test_repeated_node_is_written_once_from_the_last_row(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a)-[:ALLIES_WITH]->(b:Program {designation: 'Tron'}) "
            "SET b.cycles = b.cycles + 1 RETURN b.cycles AS cycles"
        )
        assert result.summary.properties_set == 1
        tron = next(iter(graph.find_nodes("Program", designation="Tron")))
        assert tron["cycles"] == 41
        assert [row["cycles"] for row in result] == [41, 41]

    def test_repeated_node_is_deleted_once(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a)-[:ALLIES_WITH]->(b:Program {designation: 'Tron'}) DETACH DELETE b"
        )
        assert result.summary.deleted_nodes == 1
        assert list(graph.find_nodes("Program", designation="Tron")) == []

    def test_parallel_relationships_are_deleted_once_each(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'})-[r:ALLIES_WITH]->(b:Program "
            "{designation: 'Quorra'}) DELETE r"
        )
        assert result.summary.deleted_relationships == 2

    def test_self_loop_is_mutated_once(self, graph: Graph) -> None:
        result = graph.query("MATCH (a)-[r:GUARDS]->(a) SET r.since_cycle = 1")
        assert result.summary.properties_set == 1
        relationship = next(iter(graph.find_relationships("GUARDS")))
        assert relationship["since_cycle"] == 1


class TestBindingRefresh:
    """Verify a statement observes its own mutations."""

    def test_return_observes_a_new_value(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = 99 RETURN n.cycles AS cycles"
        )
        assert [row["cycles"] for row in result] == [99]

    def test_path_variable_is_refreshed(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH p = (a:Program {designation: 'Kevin Flynn'})-[r:ALLIES_WITH]->(b) "
            "SET a.cycles = 1 RETURN p"
        )
        for row in result:
            path = row["p"]
            assert isinstance(path, Path)
            assert isinstance(path.nodes[0], Node)
            assert path.nodes[0]["cycles"] == 1

    def test_write_after_delete_raises_and_rolls_back(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("MATCH (n:Program {designation: 'Clu'}) DELETE n SET n.cycles = 1")
        clu = next(iter(graph.find_nodes("Program", designation="Clu")))
        assert "cycles" not in clu


class TestWriteValues:
    """Verify stored value rules and null removal."""

    def test_list_parameter_is_stored(self, graph: Graph) -> None:
        graph.query(
            "CREATE (n:Program {designation: 'Quorra', tags: $tags})",
            {"tags": ["ISO", "Program"]},
        )
        created = list(graph.find_nodes("Program", designation="Quorra"))
        assert created[-1]["tags"] == ["ISO", "Program"]

    @pytest.mark.parametrize(
        "value",
        [{"nested": 1}, [1, [2]], float("nan"), float("inf"), float("-inf")],
    )
    def test_invalid_value_is_rejected(self, graph: Graph, value: object) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query(
                "MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = $value",
                {"value": typing.cast(QueryValue, value)},
            )
        quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
        assert quorra["cycles"] == 37


class TestWriteAtomicity:
    """Verify one statement is one transaction, or one savepoint."""

    def test_failure_rolls_back_the_statement(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query(
                "CREATE (n:Program {designation: 'Quorra'}) CREATE (m:Program {tags: $bad})",
                {"bad": {"nested": [1]}},
            )
        assert len(list(graph.find_nodes("Program", designation="Quorra"))) == 1
        assert graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"] == 5

    def test_handle_remains_usable_after_failure(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("CREATE (n:Program {x: $bad})", {"bad": {"nested": 1}})
        with graph.transaction() as transaction:
            transaction.add_node("Program", designation="Quorra")
        assert len(list(graph.find_nodes("Program", designation="Quorra"))) == 2

    def test_failure_inside_transaction_keeps_transaction_usable(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            transaction.add_node("Program", designation="Sam Flynn")
            with pytest.raises(QueryExecutionError):
                transaction.query("CREATE (n:Program {x: $bad})", {"bad": {"nested": 1}})
            transaction.add_node("Program", designation="Quorra")
        assert len(list(graph.find_nodes("Program", designation="Sam Flynn"))) == 1
        assert len(list(graph.find_nodes("Program", designation="Quorra"))) == 2


class TestWriteErrors:
    """Verify domain failures surface as query execution errors."""

    def test_connected_node_error_is_wrapped(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("MATCH (n:Program {designation: 'Kevin Flynn'}) DELETE n")

    def test_raw_sqlite_error_is_wrapped(self, graph: Graph) -> None:
        failure = sqlite3.OperationalError("storage failure")
        patched = unittest.mock.patch.object(NodeRepository, "create", side_effect=failure)
        with patched, pytest.raises(QueryExecutionError):
            graph.query("CREATE (n:Program)")


class TestWriteLifecycle:
    """Verify transactions, prepared writes, and guards."""

    def test_transaction_query_observes_uncommitted_write(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            transaction.query("CREATE (n:Program {designation: 'Sam Flynn'})")
            result = transaction.query(
                "MATCH (n:Program {designation: 'Sam Flynn'}) RETURN count(*) AS total"
            )
            assert result.rows[0]["total"] == 1
        assert len(list(graph.find_nodes("Program", designation="Sam Flynn"))) == 1

    def test_transaction_rollback_removes_created_node(self, graph: Graph) -> None:
        with pytest.raises(RuntimeError), graph.transaction() as transaction:
            self._create_and_fail(transaction)
        assert list(graph.find_nodes("Program", designation="Sam Flynn")) == []

    @staticmethod
    def _create_and_fail(transaction: object) -> None:
        transaction.query("CREATE (n:Program {designation: 'Sam Flynn'})")  # type: ignore[attr-defined]
        raise RuntimeError

    def test_graph_query_is_blocked_by_active_transaction(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            with pytest.raises(TransactionError):
                graph.query("CREATE (n:Program)")
            transaction.add_node("Program", designation="Quorra")

    def test_closed_handle_rejects_a_write(self) -> None:
        graph = Graph.open(":memory:")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.query("CREATE (n:Program)")

    def test_prepared_write_has_empty_columns(self, graph: Graph) -> None:
        prepared = graph.prepare("CREATE (n:Program {designation: $name})")
        assert prepared.columns == ()
        prepared.execute({"name": "Sam Flynn"})
        prepared.execute({"name": "Quorra"})
        assert len(list(graph.find_nodes("Program", designation="Sam Flynn"))) == 1


class TestWriteSummary:
    """Verify result summaries and write persistence."""

    def test_summary_reports_applied_operations(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = 38")
        assert result.summary == MutationSummary(properties_set=1)

    def test_read_statement_reports_zero_counts(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) RETURN count(*) AS total")
        assert result.summary == MutationSummary()

    def test_write_persists_across_reopen(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            graph.query("CREATE (n:Program {designation: 'Quorra'})")
        with Graph.open(path) as graph:
            assert len(list(graph.find_nodes("Program", designation="Quorra"))) == 1

    def test_result_values_stay_immutable_around_writes(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Quorra'}) RETURN n")
        node = result.rows[0]["n"]
        graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = 1")
        assert isinstance(node, Node)
        assert node["cycles"] == 37

    def test_exports_mutation_summary(self) -> None:
        assert pygrafito.MutationSummary is MutationSummary
