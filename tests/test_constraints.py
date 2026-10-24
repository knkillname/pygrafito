# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for declared uniqueness constraints and violation reporting."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from pygrafito import (
    Constraint,
    ConstraintViolationError,
    ElementKind,
    Graph,
    GraphClosedError,
    NotFoundError,
    ReadOnlyError,
    TransactionError,
    ValidationError,
)
from pygrafito.model import Value
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.constraints import ConstraintTranslator


class _ConstraintTestCase:
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


class TestDeclaration(_ConstraintTestCase):
    """Verify constraint creation, listing, and removal."""

    def test_create_node_constraint(self, graph: Graph) -> None:
        constraint = graph.create_node_uniqueness_constraint("Program", "designation")
        assert constraint == Constraint(ElementKind.NODE, "Program", "designation")
        assert graph.constraints() == (constraint,)

    def test_create_relationship_constraint(self, graph: Graph) -> None:
        constraint = graph.create_relationship_uniqueness_constraint("ALLIES_WITH", "since")
        assert constraint == Constraint(ElementKind.RELATIONSHIP, "ALLIES_WITH", "since")
        assert graph.constraints() == (constraint,)

    def test_declaration_is_idempotent(self, graph: Graph) -> None:
        first = graph.create_node_uniqueness_constraint("Program", "designation")
        second = graph.create_node_uniqueness_constraint("Program", "designation")
        assert first == second
        assert graph.constraints() == (first,)

    def test_constraints_are_ordered(self, graph: Graph) -> None:
        relationship = graph.create_relationship_uniqueness_constraint("ALLIES_WITH", "since")
        program = graph.create_node_uniqueness_constraint("Program", "designation")
        iso = graph.create_node_uniqueness_constraint("ISO", "designation")
        assert graph.constraints() == (iso, program, relationship)

    def test_empty_label_rejected(self, graph: Graph) -> None:
        with pytest.raises(ValidationError):
            graph.create_node_uniqueness_constraint("", "designation")
        assert graph.constraints() == ()

    def test_empty_key_rejected(self, graph: Graph) -> None:
        with pytest.raises(ValidationError):
            graph.create_relationship_uniqueness_constraint("ALLIES_WITH", "")
        assert graph.constraints() == ()

    def test_drop_constraint(self, graph: Graph) -> None:
        constraint = graph.create_node_uniqueness_constraint("Program", "designation")
        node = graph.add_node("Program", designation="Tron")
        graph.drop_constraint(constraint)
        assert graph.constraints() == ()
        assert graph.node(node.id) == node

    def test_drop_missing_constraint(self, graph: Graph) -> None:
        constraint = Constraint(ElementKind.NODE, "Program", "designation")
        with pytest.raises(NotFoundError):
            graph.drop_constraint(constraint)

    def test_constraint_objects_are_not_reported_as_indexes(self, graph: Graph) -> None:
        graph.create_node_uniqueness_constraint("Program", "designation")
        graph.create_relationship_uniqueness_constraint("ALLIES_WITH", "since")
        assert graph.indexes() == ()

    def test_declaring_keeps_the_schema_version(self, graph: Graph) -> None:
        before = graph._database.connection.execute("PRAGMA user_version").fetchone()
        constraint = graph.create_node_uniqueness_constraint("Program", "designation")
        graph.drop_constraint(constraint)
        after = graph._database.connection.execute("PRAGMA user_version").fetchone()
        assert before == after

    def test_reopen_preserves_and_enforces(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            constraint = graph.create_node_uniqueness_constraint("Program", "designation")
            graph.add_node("Program", designation="Tron")
        with Graph.open(path) as graph:
            assert graph.constraints() == (constraint,)
            with pytest.raises(ConstraintViolationError):
                graph.add_node("Program", designation="Tron")


class TestAccessGuards(_ConstraintTestCase):
    """Verify read-only handles and active transactions are respected."""

    def test_create_inside_transaction_rejected(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            transaction.add_node("Program", designation="Quorra")
            with pytest.raises(TransactionError):
                graph.create_node_uniqueness_constraint("Program", "designation")
        assert graph.constraints() == ()

    def test_drop_inside_transaction_rejected(self, graph: Graph) -> None:
        constraint = graph.create_node_uniqueness_constraint("Program", "designation")
        with graph.transaction() as transaction:
            transaction.add_node("Program", designation="Tron")
            with pytest.raises(TransactionError):
                graph.drop_constraint(constraint)
        assert graph.constraints() == (constraint,)

    def test_read_only_listing_works(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            constraint = graph.create_node_uniqueness_constraint("Program", "designation")
        with Graph.open(path, readonly=True) as graph:
            assert graph.constraints() == (constraint,)

    def test_read_only_declaration_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path):
            pass
        with Graph.open(path, readonly=True) as graph, pytest.raises(ReadOnlyError):
            graph.create_node_uniqueness_constraint("Program", "designation")

    def test_read_only_drop_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            constraint = graph.create_node_uniqueness_constraint("Program", "designation")
        with Graph.open(path, readonly=True) as graph, pytest.raises(ReadOnlyError):
            graph.drop_constraint(constraint)

    def test_closed_handle_rejected(self) -> None:
        graph = Graph.open(":memory:")
        graph.close()
        with pytest.raises(GraphClosedError):
            graph.constraints()
        with pytest.raises(GraphClosedError):
            graph.create_node_uniqueness_constraint("Program", "designation")


class TestNodeEnforcement(_ConstraintTestCase):
    """Verify node uniqueness on every write path."""

    @pytest.fixture
    def constrained(self, graph: Graph) -> Graph:
        """Declare a node constraint on the fixture graph.

        Parameters
        ----------
        graph : Graph
            Graph under test.

        Returns
        -------
        Graph
            The same graph with one declared constraint.
        """
        graph.create_node_uniqueness_constraint("Program", "designation")
        return graph

    def test_create_duplicate_fails(self, constrained: Graph) -> None:
        constrained.add_node("Program", designation="Tron")
        with pytest.raises(ConstraintViolationError):
            constrained.add_node("Program", designation="Tron")
        assert [node["designation"] for node in constrained.find_nodes("Program")] == ["Tron"]

    def test_assign_duplicate_keeps_the_previous_value(self, constrained: Graph) -> None:
        tron = constrained.add_node("Program", designation="Tron")
        quorra = constrained.add_node("Program", designation="Quorra")
        with pytest.raises(ConstraintViolationError):
            constrained.set_properties(quorra, designation="Tron")
        assert constrained.node(tron.id)["designation"] == "Tron"
        assert constrained.node(quorra.id)["designation"] == "Quorra"

    def test_acquiring_the_label_fails(self, constrained: Graph) -> None:
        tron = constrained.add_node("Program", designation="Tron")
        outsider = constrained.add_node(designation="Tron")
        with pytest.raises(ConstraintViolationError):
            constrained.add_labels(outsider, "ISO", "Program")
        assert constrained.node(outsider.id).labels == frozenset()
        assert constrained.node(tron.id)["designation"] == "Tron"

    def test_statement_create_fails(self, constrained: Graph) -> None:
        constrained.add_node("Program", designation="Tron")
        with pytest.raises(ConstraintViolationError):
            constrained.query("CREATE (n:Program {designation: 'Tron'})")
        assert constrained.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"] == 1

    def test_merge_matches_instead_of_failing(self, constrained: Graph) -> None:
        tron = constrained.add_node("Program", designation="Tron")
        constrained.query("MERGE (n:Program {designation: 'Tron'})")
        assert constrained.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"] == 1
        assert constrained.node(tron.id)["designation"] == "Tron"

    def test_import_batch_reports_the_failing_row(self, constrained: Graph) -> None:
        with pytest.raises(ConstraintViolationError) as raised:
            constrained.import_rows(
                "UNWIND $rows AS row CREATE (n:Program {designation: row.designation})",
                [{"designation": "Tron"}, {"designation": "Tron"}],
            )
        notes = "\n".join(raised.value.__notes__)
        assert "row 2" in notes
        assert list(constrained.find_nodes("Program")) == []

    def test_delete_releases_the_value(self, constrained: Graph) -> None:
        tron = constrained.add_node("Program", designation="Tron")
        constrained.delete(tron)
        recreated = constrained.add_node("Program", designation="Tron")
        assert constrained.node(recreated.id)["designation"] == "Tron"

    def test_relationship_constraint(self, graph: Graph) -> None:
        graph.create_relationship_uniqueness_constraint("ALLIES_WITH", "since")
        first = graph.add_node("Program", designation="Tron")
        second = graph.add_node("Program", designation="Quorra")
        graph.add_relationship(first, "ALLIES_WITH", second, since=2020)
        with pytest.raises(ConstraintViolationError):
            graph.add_relationship(second, "ALLIES_WITH", first, since=2020)
        graph.add_relationship(second, "ALLIES_WITH", first, since=2021)
        graph.add_relationship(second, "TRUSTS", first, since=2020)
        assert len(list(graph.find_relationships("ALLIES_WITH"))) == 2

    def test_relationship_property_update_fails(self, graph: Graph) -> None:
        graph.create_relationship_uniqueness_constraint("ALLIES_WITH", "since")
        first = graph.add_node("Program", designation="Tron")
        second = graph.add_node("Program", designation="Quorra")
        allies = graph.add_relationship(first, "ALLIES_WITH", second, since=2020)
        other = graph.add_relationship(second, "ALLIES_WITH", first, since=2021)
        with pytest.raises(ConstraintViolationError):
            graph.set_properties(allies, since=2021)
        assert graph.relationship(other.id)["since"] == 2021
        assert graph.relationship(allies.id)["since"] == 2020


class TestTypeSensitiveEnforcement(_ConstraintTestCase):
    """Verify values compare by type and value, and scope exemptions hold."""

    @pytest.fixture
    def constrained(self, graph: Graph) -> Graph:
        """Declare a node constraint on the fixture graph.

        Parameters
        ----------
        graph : Graph
            Graph under test.

        Returns
        -------
        Graph
            The same graph with one declared constraint.
        """
        graph.create_node_uniqueness_constraint("Program", "state")
        return graph

    def test_boolean_does_not_collide_with_integer(self, constrained: Graph) -> None:
        first = constrained.add_node("Program", state=True)
        second = constrained.add_node("Program", state=1)
        assert constrained.node(first.id)["state"] is True
        assert constrained.node(second.id)["state"] == 1
        with pytest.raises(ConstraintViolationError):
            constrained.set_properties(second, state=True)

    def test_integer_does_not_collide_with_float(self, constrained: Graph) -> None:
        first = constrained.add_node("Program", state=1)
        second = constrained.add_node("Program", state=1.0)
        assert constrained.node(first.id)["state"] == 1
        assert constrained.node(second.id)["state"] == 1.0

    def test_string_does_not_collide_with_number(self, constrained: Graph) -> None:
        first = constrained.add_node("Program", state="1")
        second = constrained.add_node("Program", state=1)
        assert constrained.node(first.id)["state"] == "1"
        assert constrained.node(second.id)["state"] == 1

    def test_missing_property_is_exempt(self, constrained: Graph) -> None:
        constrained.add_node("Program", designation="Tron")
        constrained.add_node("Program", designation="Quorra")
        assert len(list(constrained.find_nodes("Program"))) == 2

    def test_outside_the_scope_is_exempt(self, constrained: Graph) -> None:
        constrained.add_node("Program", state="Tron")
        constrained.add_node("ISO", state="Tron")
        assert len(list(constrained.find_nodes(state="Tron"))) == 2

    def test_lists_compare_by_content_and_order(self, constrained: Graph) -> None:
        constrained.add_node("Program", state=["ISO", "Grid"])
        with pytest.raises(ConstraintViolationError):
            constrained.add_node("Program", state=["ISO", "Grid"])
        constrained.add_node("Program", state=["Grid", "ISO"])
        assert len(list(constrained.find_nodes("Program"))) == 2


class TestImmediateEnforcement(_ConstraintTestCase):
    """Verify a violation fails its statement inside a transaction."""

    def test_first_write_survives_and_the_transaction_commits(self, graph: Graph) -> None:
        graph.create_node_uniqueness_constraint("Program", "designation")
        with graph.transaction() as transaction:
            first = transaction.add_node("Program", designation="Tron")
            with pytest.raises(ConstraintViolationError):
                transaction.add_node("Program", designation="Tron")
            total = transaction.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"]
            assert total == 1
            second = transaction.add_node("Program", designation="Quorra")
        assert graph.node(first.id)["designation"] == "Tron"
        assert graph.node(second.id)["designation"] == "Quorra"
        assert graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"] == 2

    def test_swap_in_one_statement_fails(self, graph: Graph) -> None:
        graph.create_node_uniqueness_constraint("Program", "designation")
        tron = graph.add_node("Program", designation="Tron")
        quorra = graph.add_node("Program", designation="Quorra")
        with pytest.raises(ConstraintViolationError):
            graph.query(
                "MATCH (a:Program {designation: 'Tron'}), "
                "(b:Program {designation: 'Quorra'}) "
                "SET a.designation = 'Quorra', b.designation = 'Tron'"
            )
        assert graph.node(tron.id)["designation"] == "Tron"
        assert graph.node(quorra.id)["designation"] == "Quorra"

    def test_rollback_keeps_the_graph_unchanged(self, graph: Graph) -> None:
        graph.create_node_uniqueness_constraint("Program", "designation")
        graph.add_node("Program", designation="Tron")
        transaction = graph.transaction().begin()
        transaction.add_node("Program", designation="Quorra")
        transaction.rollback()
        assert [node["designation"] for node in graph.find_nodes("Program")] == ["Tron"]


class TestDeclarationOverExistingData(_ConstraintTestCase):
    """Verify a declaration validates the data in the same transaction."""

    def test_conflicting_data_refuses_declaration(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Tron")
        graph.add_node("Program", designation="Tron")
        with pytest.raises(ConstraintViolationError):
            graph.create_node_uniqueness_constraint("Program", "designation")
        assert graph.constraints() == ()

    def test_conflicting_relationship_data_refuses_declaration(self, graph: Graph) -> None:
        first = graph.add_node("Program", designation="Tron")
        second = graph.add_node("Program", designation="Quorra")
        graph.add_relationship(first, "ALLIES_WITH", second, since=2020)
        graph.add_relationship(second, "ALLIES_WITH", first, since=2020)
        with pytest.raises(ConstraintViolationError):
            graph.create_relationship_uniqueness_constraint("ALLIES_WITH", "since")
        assert graph.constraints() == ()

    def test_clean_data_accepts_declaration(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Tron")
        graph.add_node("Program", designation="Quorra")
        constraint = graph.create_node_uniqueness_constraint("Program", "designation")
        assert graph.constraints() == (constraint,)


class TestViolationPayload(_ConstraintTestCase):
    """Verify the violation error carries the attempted value and holder."""

    def test_existing_holder_is_named(self, graph: Graph) -> None:
        graph.create_node_uniqueness_constraint("Program", "designation")
        holder = graph.add_node("Program", designation="Tron")
        with pytest.raises(ConstraintViolationError) as raised:
            graph.add_node("Program", designation="Tron")
        error = raised.value
        assert error.kind is ElementKind.NODE
        assert error.scope == "Program"
        assert error.key == "designation"
        assert error.value == "Tron"
        assert error.existing == holder.id

    def test_duplicate_removed_with_the_statement_has_no_holder(self, graph: Graph) -> None:
        graph.create_node_uniqueness_constraint("Program", "designation")
        with pytest.raises(ConstraintViolationError) as raised:
            graph.query(
                "CREATE (a:Program {designation: 'Clu'}) CREATE (b:Program {designation: 'Clu'})"
            )
        error = raised.value
        assert error.value == "Clu"
        assert error.existing is None
        assert list(graph.find_nodes("Program")) == []

    def test_foreign_key_failure_is_not_translated(self) -> None:
        with Graph.open(":memory:") as graph:
            translator = ConstraintTranslator(graph._database.connection, PropertyCodec())
            failure = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
            assert translator.translate(failure) is None

    def test_unknown_object_name_is_not_translated(self) -> None:
        with Graph.open(":memory:") as graph:
            translator = ConstraintTranslator(graph._database.connection, PropertyCodec())
            failure = sqlite3.IntegrityError("UNIQUE constraint failed: index 'some_other_index'")
            assert translator.translate(failure) is None


class TestWrapperGeneric:
    """Verify explicit values remain storable when no constraint applies."""

    @pytest.mark.parametrize("value", [True, 1, 1.0, "1", ["ISO", "Grid"]])
    def test_values_round_trip(self, value: Value) -> None:
        with Graph.open(":memory:") as graph:
            graph.create_node_uniqueness_constraint("Program", "state")
            node = graph.add_node("Program", state=value)
            assert graph.node(node.id)["state"] == value
