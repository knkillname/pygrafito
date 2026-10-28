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

    def test_two_stage_statement_reports_each_stage(self, graph: Graph) -> None:
        graph.create_node_index("cycles")
        plan = graph.explain(
            "MATCH (a:Program) WHERE a.cycles = 36 WITH a MATCH (a)-[:ALLIES_WITH]->(b) RETURN b"
        )
        assert any("pygrafito_idx_node_" in line for line in plan)
        assert len(plan) >= 2

    def test_quantified_statement_reports_expansion(self, graph: Graph) -> None:
        plan = graph.explain("MATCH (n:Program {cycles: 36})-[:ALLIES_WITH*1..2]->(b) RETURN b")
        assert any("QUANTIFIED PATTERN max_hops=2" in line for line in plan)

    def test_match_mode_is_reported(self, graph: Graph) -> None:
        plan = graph.explain("MATCH DIFFERENT EDGES (a:Program)-[:ALLIES_WITH]->(b) RETURN b")
        assert "MATCH DIFFERENT EDGES" in plan

    def test_default_match_mode_is_omitted(self, graph: Graph) -> None:
        plan = graph.explain("MATCH REPEATABLE ELEMENTS (a:Program)-[:ALLIES_WITH]->(b) RETURN b")
        assert all("DIFFERENT EDGES" not in line for line in plan)

    def test_optional_match_mode_is_reported(self, graph: Graph) -> None:
        plan = graph.explain(
            "OPTIONAL MATCH DIFFERENT EDGES (a:Program)-[:ALLIES_WITH]->(b) RETURN b"
        )
        assert "OPTIONAL MATCH DIFFERENT EDGES" in plan

    def test_quantified_match_mode_is_reported(self, graph: Graph) -> None:
        plan = graph.explain("MATCH DIFFERENT EDGES (a:Program)-[:ALLIES_WITH*1..2]->(b) RETURN b")
        assert "MATCH DIFFERENT EDGES" in plan
        assert any("QUANTIFIED PATTERN" in line for line in plan)

    def test_path_search_prefix_is_reported(self, graph: Graph) -> None:
        plan = graph.explain("MATCH p = ANY (a:Program)-[:ALLIES_WITH]->(b) RETURN p")
        assert plan[0] == "PATH SEARCH ANY"

    def test_shortest_count_is_reported(self, graph: Graph) -> None:
        plan = graph.explain("MATCH p = SHORTEST 2 (a:Program)-[:ALLIES_WITH]->(b) RETURN p")
        assert "PATH SEARCH SHORTEST 2" in plan

    def test_open_search_reports_the_open_marker(self, graph: Graph) -> None:
        plan = graph.explain("MATCH p = ANY SHORTEST (a:Program)-[:ALLIES_WITH{1,}]->(b) RETURN p")
        assert plan[0] == "PATH SEARCH ANY SHORTEST"
        assert any("MATCH QUANTIFIED OPEN" in line for line in plan)

    def test_plain_pattern_has_no_search_marker(self, graph: Graph) -> None:
        plan = graph.explain("MATCH (a:Program)-[:ALLIES_WITH]->(b) RETURN b")
        assert all("PATH SEARCH" not in line for line in plan)

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

    def test_unindexed_filter_starts_from_the_label_index(self, graph: Graph) -> None:
        plan = graph.explain("MATCH (n:Program) WHERE n.cycles = 36 RETURN n")
        details = " ".join(plan)
        assert "node_labels_by_label" in details
        assert "pygrafito_idx_node_" not in details

    def test_relationship_label_filter_uses_an_index(self, graph: Graph) -> None:
        plan = graph.explain("MATCH (a)-[r:ALLIES_WITH]->(b) RETURN b")
        details = " ".join(plan)
        assert "relationship_labels_by_label" in details

    def test_range_filter_uses_the_declared_index(self, graph: Graph) -> None:
        graph.create_node_index("cycles")
        plan = graph.explain("MATCH (n:Program) WHERE n.cycles > 36 RETURN n")
        assert any("pygrafito_idx_node_" in line for line in plan)

    def test_invalid_statement_raises(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError):
            graph.explain("MATCH (n:Program WHERE")


class TestExplainUnwindAndDynamicValues(_ExplainTestCase):
    """Verify plan inspection covers UNWIND and dynamic pattern values."""

    def test_unwind_stage_is_reported(self, graph: Graph) -> None:
        plan = graph.explain("UNWIND [1, 2] AS value MATCH (n:Program) RETURN n")
        assert any("UNWIND value" in line for line in plan)
        assert any(line.startswith("SEARCH n0") for line in plan)

    def test_dynamic_pattern_value_is_planned_without_a_row(self, graph: Graph) -> None:
        plan = graph.explain(
            "UNWIND $rows AS row MATCH (n:Program {designation: row.name}) RETURN n",
            {"rows": [{"name": "Kevin Flynn"}]},
        )
        assert any("UNWIND row" in line for line in plan)
        assert any("n0" in line for line in plan)


class TestExplainComposition(_ExplainTestCase):
    """Verify composition boundaries appear in plan inspection."""

    def test_next_and_yield_are_reported(self, graph: Graph) -> None:
        plan = graph.explain(
            "MATCH (n:Program) RETURN n AS element NEXT YIELD element RETURN element"
        )
        assert "RETURN" in plan
        assert "NEXT" in plan
        assert "YIELD" in plan

    def test_let_and_finish_are_reported(self, graph: Graph) -> None:
        let_plan = graph.explain("MATCH (n:Program) LET cycles = n.cycles RETURN cycles")
        finish_plan = graph.explain("MATCH (n:Program) FINISH")
        assert "LET" in let_plan
        assert "FINISH" in finish_plan


class TestExplainSetOperations(_ExplainTestCase):
    """Verify compound operators appear in plan inspection."""

    def test_all_quantifiers_are_reported(self, graph: Graph) -> None:
        plan = graph.explain(
            "UNWIND [1] AS x RETURN x AS n "
            "INTERSECT ALL UNWIND [1] AS x RETURN x AS n "
            "EXCEPT ALL UNWIND [2] AS x RETURN x AS n"
        )
        assert plan.count("INTERSECT ALL") == 1
        assert plan.count("EXCEPT ALL") == 1

    def test_explicit_distinct_renders_the_bare_operator(self, graph: Graph) -> None:
        plan = graph.explain(
            "UNWIND [1] AS x RETURN x AS n UNION DISTINCT UNWIND [1] AS x RETURN x AS n"
        )
        assert "UNION" in plan
        assert "UNION DISTINCT" not in plan
