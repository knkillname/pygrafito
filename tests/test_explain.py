# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for plan inspection without execution."""

from collections.abc import Iterator

import pytest

from pygrafito import Graph, QuerySemanticError, QuerySyntaxError


class _ExplainTestCase:
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
            graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            yield graph


class TestExplain(_ExplainTestCase):
    """Verify statements are planned without side effects."""

    def test_returns_plan_lines(self, graph: Graph) -> None:
        plan = graph.explain("MATCH (n:Program) WHERE n.cycles = 36 RETURN n")
        assert isinstance(plan, tuple)
        assert plan
        assert all(isinstance(line, str) for line in plan)

    def test_write_statement_changes_nothing(self, graph: Graph) -> None:
        before = graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"]
        plan = graph.explain("CREATE (n:Program {designation: 'Tron', cycles: 40})")
        after = graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"]
        assert plan == ()
        assert after == before == 1

    def test_matched_write_changes_nothing(self, graph: Graph) -> None:
        before = dict(next(iter(graph.find_nodes("Program"))))
        graph.explain("MATCH (n:Program) SET n.cycles = 99 REMOVE n.designation")
        after = dict(next(iter(graph.find_nodes("Program"))))
        assert after == before

    def test_delete_statement_changes_nothing(self, graph: Graph) -> None:
        graph.explain("MATCH (n:Program) DETACH DELETE n")
        assert graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"] == 1

    def test_parameters_are_accepted(self, graph: Graph) -> None:
        plan = graph.explain(
            "MATCH (n:Program) WHERE n.cycles = $value RETURN n",
            {"value": 36},
        )
        assert plan

    def test_missing_parameter_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError):
            graph.explain("MATCH (n:Program) WHERE n.cycles = $value RETURN n")

    def test_invalid_statement_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError):
            graph.explain("MATCH (n:Program RETURN n")


class TestPlanSelection(_ExplainTestCase):
    """Verify the plan reports the access path an index changes."""

    def test_indexed_filter_uses_the_declared_index(self, graph: Graph) -> None:
        graph.create_node_index("cycles")
        plan = graph.explain("MATCH (n:Program) WHERE n.cycles = 36 RETURN n")
        details = " ".join(plan)
        assert "pygrafito_idx_node_" in details
        assert "SCAN n0" not in details

    def test_unindexed_filter_scans_the_node_table(self, graph: Graph) -> None:
        plan = graph.explain("MATCH (n:Program) WHERE n.cycles = 36 RETURN n")
        assert any(line.startswith("SCAN n0") for line in plan)

    def test_relationship_type_filter_uses_an_index(self, graph: Graph) -> None:
        plan = graph.explain("MATCH (a)-[r:ALLIES_WITH]->(b) RETURN b")
        details = " ".join(plan)
        assert "rel_by_type" in details
        assert "SCAN r0" not in details

    def test_range_filter_uses_the_declared_index(self, graph: Graph) -> None:
        graph.create_node_index("cycles")
        plan = graph.explain("MATCH (n:Program) WHERE n.cycles > 36 RETURN n")
        assert any("pygrafito_idx_node_" in line for line in plan)

    def test_invalid_statement_raises(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError):
            graph.explain("MATCH (n:Program WHERE")
