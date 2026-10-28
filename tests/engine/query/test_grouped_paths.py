# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for grouped and juxtaposed path patterns."""

import typing
from pathlib import Path

import pytest

from pygrafito import (
    Graph,
    QueryBudgetExceededError,
    QueryResult,
    QuerySemanticError,
    QuerySyntaxError,
)
from pygrafito.engine.query.ast import (
    GroupedPathTerm,
    HopRange,
    Match,
    PathMode,
    SimplePathTerm,
)
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.plan import Plan, PlanBuilder
from pygrafito.engine.query.semantic import (
    Analysis,
    MatchStage,
    OptionalMatchStage,
    SemanticAnalyzer,
    VariableKind,
)
from pygrafito.model import Path as GraphPath
from pygrafito.model import QueryBudget


class TestGroupedFixtures:
    """Build the TRON graphs used by the grouped-path tests."""

    @staticmethod
    def cycle_graph() -> Graph:
        """Return a directed three-program cycle."""
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        clu = graph.add_node("Program", designation="Clu")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(tron, "TRUSTS", clu)
        graph.add_relationship(clu, "TRUSTS", flynn)
        return graph

    @staticmethod
    def diamond_graph() -> Graph:
        """Return two two-hop routes from Kevin to Alan."""
        graph = Graph.open(":memory:")
        kevin = graph.add_node("User", designation="Kevin Flynn")
        sam = graph.add_node("User", designation="Sam Flynn")
        quorra = graph.add_node("Program", designation="Quorra")
        alan = graph.add_node("User", designation="Alan Bradley")
        graph.add_relationship(kevin, "PARENT_OF", sam)
        graph.add_relationship(kevin, "TRUSTS", quorra)
        graph.add_relationship(sam, "TRUSTS", alan)
        graph.add_relationship(quorra, "TRUSTS", alan)
        return graph

    @staticmethod
    def parallel_graph() -> Graph:
        """Return parallel trust and alliance relationships."""
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(flynn, "ALLIES_WITH", tron)
        return graph

    @staticmethod
    def self_loop_graph() -> Graph:
        """Return one monitor self-loop."""
        graph = Graph.open(":memory:")
        tron = graph.add_node("Program", designation="Tron")
        graph.add_relationship(tron, "MONITORS", tron)
        return graph

    @staticmethod
    def rows(result: QueryResult) -> list[tuple[object, ...]]:
        """Return result rows as tuples."""
        return [tuple(row.values()) for row in result.rows]

    @staticmethod
    def lengths(result: QueryResult) -> list[int]:
        """Return the projected ``n`` column."""
        return [typing.cast(int, row["n"]) for row in result.rows]


class TestGroupedParsing:
    """Verify grouped syntax and juxtaposition."""

    @staticmethod
    def match(text: str) -> Match:
        statement = Parser.parse_statement(text)
        clause = statement.clauses[0]
        if not isinstance(clause, Match):
            raise AssertionError("expected a match clause")
        return clause

    @pytest.mark.parametrize(
        ("text", "minimum", "maximum"),
        [
            ("MATCH ((a)-[r]->(b)){2} RETURN a", 2, 2),
            ("MATCH ((a)-[r]->(b)){1,3} RETURN a", 1, 3),
            ("MATCH ((a)-[r]->(b)){,2} RETURN a", 0, 2),
            ("MATCH ((a)-[r]->(b)){1,} RETURN a", 1, None),
            ("MATCH ((a)-[r]->(b))* RETURN a", 0, None),
            ("MATCH ((a)-[r]->(b))+ RETURN a", 1, None),
        ],
    )
    def test_quantifiers(self, text: str, minimum: int, maximum: int | None) -> None:
        term = self.match(text).patterns[0].terms[0]
        assert isinstance(term, GroupedPathTerm)
        assert term.quantifier == HopRange(minimum, maximum)

    def test_group_path_variable_and_mode(self) -> None:
        term = self.match("MATCH (p = TRAIL (a)-[r]->(b)){2} RETURN p").patterns[0].terms[0]
        assert isinstance(term, GroupedPathTerm)
        assert term.variable == "p"
        assert term.mode is PathMode.TRAIL

    def test_node_pattern_and_property_map_are_not_groups(self) -> None:
        clause = self.match("MATCH (a:Program {designation: 'Flynn'}) RETURN a")
        term = clause.patterns[0].terms[0]
        assert isinstance(term, SimplePathTerm)
        assert term.nodes[0].properties

    def test_juxtaposition_builds_adjacent_terms(self) -> None:
        pattern = self.match("MATCH (a)((b)-[r:TRUSTS]->(c)){2}(d) RETURN d").patterns[0]
        assert len(pattern.terms) == 3
        assert isinstance(pattern.terms[0], SimplePathTerm)
        assert isinstance(pattern.terms[1], GroupedPathTerm)
        assert isinstance(pattern.terms[2], SimplePathTerm)

    def test_nested_group(self) -> None:
        outer = self.match("MATCH (((a)-[r]->(b)){2}){2} RETURN a").patterns[0].terms[0]
        assert isinstance(outer, GroupedPathTerm)
        inner = outer.pattern.terms[0]
        assert isinstance(inner, GroupedPathTerm)

    def test_missing_quantifier_is_rejected(self) -> None:
        with pytest.raises(QuerySyntaxError, match="quantifier"):
            Parser.parse_statement("MATCH ((a)-[r]->(b)) RETURN a")

    def test_legacy_group_quantifier_is_rejected(self) -> None:
        with pytest.raises(QuerySyntaxError, match="legacy"):
            Parser.parse_statement("MATCH ((a)-[r]->(b))*1..2 RETURN a")

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH ((ANY (a)-[r]->(b))){2} RETURN a",
            "MATCH (p = ANY (a)-[r]->(b)){2} RETURN p",
        ],
    )
    def test_search_prefix_inside_group_is_rejected(self, text: str) -> None:
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement(text)

    @pytest.mark.parametrize(
        "text",
        [
            "INSERT ((a)-[:TRUSTS]->(b)){2}",
            "CREATE ((n:Program)){2}",
            "MERGE ((n:Program)){2}",
        ],
    )
    def test_write_patterns_reject_groups(self, text: str) -> None:
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement(text)


class TestGroupedSemantics:
    """Verify scopes, kinds, structural rules, and planning."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_group_variable_kinds(self) -> None:
        analysis = self.analyze("MATCH (p = (a)-[r]->(b)){2} RETURN p, a, r, b")
        assert analysis.variable_kinds["a"] is VariableKind.NODE_LIST
        assert analysis.variable_kinds["r"] is VariableKind.RELATIONSHIP_LIST
        assert analysis.variable_kinds["p"] is VariableKind.PATH

    def test_outer_variable_is_an_equality_constraint(self) -> None:
        analysis = self.analyze("MATCH (x) ((x)-[r]->(y)){2} RETURN x, y")
        assert analysis.variable_kinds["x"] is VariableKind.NODE
        assert analysis.variable_kinds["y"] is VariableKind.NODE_LIST

    def test_duplicate_group_variable_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError, match="more than once"):
            self.analyze("MATCH ((a)-[r]->(b)-[r]->(c)){2} RETURN a")

    def test_group_path_variable_shadowing_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError, match="shadows"):
            self.analyze("MATCH (p) (p = (a)-[r]->(b)){2} RETURN p")

    def test_nested_group_cannot_reference_outer_local(self) -> None:
        with pytest.raises(QuerySemanticError, match="enclosing group"):
            self.analyze("MATCH (((a)-[r]->(b)){2} ((c)-[r]->(d)){2}){2} RETURN a")

    def test_group_without_relationship_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError, match="at least one relationship"):
            self.analyze("MATCH ((a)){2} RETURN a")

    def test_non_progressing_group_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError, match="at least one relationship"):
            self.analyze("MATCH ((a)-[:TRUSTS*0..2]->(b)){2} RETURN a")

    def test_lone_zero_lower_group_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError, match="zero lower bound"):
            self.analyze("MATCH ((a)-[:TRUSTS]->(b)){0,2} RETURN a")

    def test_zero_lower_group_with_rest_is_allowed(self) -> None:
        analysis = self.analyze("MATCH ((a)-[:TRUSTS]->(b)){0,2}(c)-[:TRUSTS]->(d) RETURN a")
        assert analysis.variable_kinds["a"] is VariableKind.NODE_LIST

    def test_lower_bound_cannot_exceed_upper(self) -> None:
        with pytest.raises(QuerySemanticError, match="lower bound"):
            self.analyze("MATCH ((a)-[:TRUSTS]->(b)){3,2} RETURN a")

    def test_group_path_variable_needs_positive_lower(self) -> None:
        with pytest.raises(QuerySemanticError, match="positive lower bound"):
            self.analyze("MATCH (p = (a)-[:TRUSTS]->(b)){0,2} RETURN p")

    def test_property_access_on_list_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError, match="node lists"):
            self.analyze("MATCH ((a)-[:TRUSTS]->(b)){2} RETURN a.designation")

    def test_plan_and_modes_are_carried(self) -> None:
        analysis = self.analyze("MATCH WALK p = ANY SHORTEST ((a)-[:TRUSTS]->(b)){2} RETURN p")
        plan = PlanBuilder.build(analysis)
        assert isinstance(plan, Plan)
        assert "group" in plan.operators
        assert "path_search" in plan.operators
        stage = plan.stages[0].stage
        if not isinstance(stage, MatchStage | OptionalMatchStage):
            raise AssertionError("expected a match stage")
        assert stage.patterns[0].mode is PathMode.WALK


class TestGroupedMatching(TestGroupedFixtures):
    """Verify fixed and nested group execution."""

    def test_fixed_group_matches_the_unrolled_form(self) -> None:
        grouped = (
            "MATCH ((a)-[r:TRUSTS]->(b)){2} "
            "RETURN [x IN a | id(x)] AS lefts, [x IN b | id(x)] AS rights, "
            "[x IN r | id(x)] AS rels ORDER BY lefts, rights"
        )
        unrolled = (
            "MATCH (a1)-[r1:TRUSTS]->(b1)-[r2:TRUSTS]->(b2) "
            "RETURN [id(a1), id(b1)] AS lefts, [id(b1), id(b2)] AS rights, "
            "[id(r1), id(r2)] AS rels ORDER BY lefts, rights"
        )
        with self.cycle_graph() as graph:
            grouped_rows = self.rows(graph.query(grouped))
            unrolled_rows = self.rows(graph.query(unrolled))
        assert grouped_rows == unrolled_rows

    def test_list_bindings_keep_traversal_order(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH ((a)-[r:TRUSTS]->(b)){2} "
                "RETURN [x IN a | x.designation] AS names, "
                "[x IN r | id(x)] AS rels"
            )
        names = [typing.cast(list[str], row["names"]) for row in result.rows]
        assert ["Flynn", "Tron"] in names
        assert all(len(typing.cast(list[int], row["rels"])) == 2 for row in result.rows)

    def test_nested_groups_flatten(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (((a)-[r:TRUSTS]->(b)){2}){2} RETURN [x IN r | id(x)] AS rels LIMIT 1"
            )
        assert len(typing.cast(list[int], result.rows[0]["rels"])) == 4

    def test_group_path_variable_concatenates_iterations(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (s:Program {designation: 'Flynn'}) "
                "(p = (a)-[r:TRUSTS]->(b)){2} "
                "RETURN length(p) AS n, [x IN nodes(p) | x.designation] AS names"
            )
        assert self.lengths(result) == [2]
        assert result.rows[0]["names"] == ["Flynn", "Tron", "Clu"]

    def test_zero_iterations_bind_empty_lists(self) -> None:
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'}) "
                "((b)-[:TRUSTS]->(c)){0,1}(d)-[:ALLIES_WITH]->(e) "
                "RETURN [x IN b | id(x)] AS nodes"
            )
        assert result.rows[0]["nodes"] == []

    def test_self_loop_boundary_is_shared(self) -> None:
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH ((a)-[r:MONITORS]->(b)){2} RETURN [x IN a | id(x)] AS starts"
            )
        assert len(result.rows) == 1

    def test_juxtaposed_boundary_is_shared(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})"
                "((b)-[:TRUSTS]->(c)){2}(d:Program {designation: 'Clu'}) "
                "RETURN d.designation AS name"
            )
        assert result.rows[0]["name"] == "Clu"


class TestGroupedModes(TestGroupedFixtures):
    """Verify inner, outer, and match modes across iterations."""

    def test_outer_acyclic_rejects_a_repeated_node(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query("MATCH ACYCLIC ((a)-[:TRUSTS]->(b)){1,3} RETURN count(*) AS total")
        assert result.rows[0]["total"] == 6

    def test_inner_acyclic_is_enforced(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH WALK (ACYCLIC (a)-[:TRUSTS]->(b)){1,3} RETURN count(*) AS total"
            )
        assert result.rows[0]["total"] == 6

    def test_inner_trail_is_enforced(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH WALK (TRAIL (a)-[:TRUSTS]->(b)){1,3} RETURN count(*) AS total"
            )
        assert result.rows[0]["total"] == 9

    def test_different_edges_spans_iterations(self) -> None:
        with self.self_loop_graph() as graph:
            repeatable = graph.query("MATCH ((a)-[:MONITORS]->(b)){2} RETURN count(*) AS total")
            different = graph.query(
                "MATCH DIFFERENT EDGES ((a)-[:MONITORS]->(b)){2} RETURN count(*) AS total"
            )
        assert repeatable.rows[0]["total"] == 1
        assert different.rows[0]["total"] == 0

    def test_path_functions_and_list_comprehension(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (p = (a)-[r:TRUSTS]->(b)){2} "
                "RETURN length(p) AS n, size(nodes(p)) AS node_count, "
                "[x IN r | id(x)] AS rels"
            )
        assert self.lengths(result) == [2, 2, 2]
        assert all(row["node_count"] == 3 for row in result.rows)


class TestGroupedExecution(TestGroupedFixtures):
    """Verify optional, open, search, budget, explain, and persistence."""

    def test_optional_group_null_extends(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'}) "
                "OPTIONAL MATCH ((a)-[:TRUSTS]->(b)){3} "
                "RETURN [x IN b | x.designation] AS names"
            )
        assert result.rows[0]["names"] is None

    def test_open_trail_group_terminates(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query("MATCH TRAIL ((a)-[:TRUSTS]->(b)){1,} RETURN count(*) AS total")
        assert result.rows[0]["total"] == 9

    def test_open_walk_group_stops_at_limit(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH ((a)-[:TRUSTS]->(b)){1,} RETURN [x IN a | x.designation] AS names LIMIT 3"
            )
        assert len(result.rows) == 3

    def test_open_walk_group_hits_the_budget(self) -> None:
        with self.cycle_graph() as graph, pytest.raises(QueryBudgetExceededError):
            graph.query(
                "MATCH ((a)-[:TRUSTS]->(b)){1,} RETURN count(*) AS total",
                budget=QueryBudget(max_expansions=10),
            )

    def test_grouped_search_selects_per_endpoint(self) -> None:
        query = (
            "MATCH p = {kind} (a:User {{designation: 'Kevin Flynn'}}) "
            "((m)-[:PARENT_OF|TRUSTS]->(n)){{2}} "
            "(b:User {{designation: 'Alan Bradley'}}) "
            "RETURN length(p) AS n"
        )
        with self.diamond_graph() as graph:
            any_row = graph.query(query.format(kind="ANY SHORTEST"))
            all_rows = graph.query(query.format(kind="ALL SHORTEST"))
            two_rows = graph.query(query.format(kind="SHORTEST 2"))
        assert self.lengths(any_row) == [2]
        assert self.lengths(all_rows) == [2, 2]
        assert self.lengths(two_rows) == [2, 2]

    def test_grouped_explain_names_the_group(self) -> None:
        with self.cycle_graph() as graph:
            plan = graph.explain("MATCH ((a:Program)-[:TRUSTS]->(b:Program)){2} RETURN a")
            open_plan = graph.explain("MATCH ((a:Program)-[:TRUSTS]->(b:Program)){1,} RETURN a")
        assert any("GROUP {2}" in line for line in plan)
        assert any("GROUP OPEN" in line for line in open_plan)
        assert any("MATCH QUANTIFIED OPEN" in line for line in open_plan)

    def test_write_rolls_back_on_budget_failure(self) -> None:
        with self.cycle_graph() as graph:
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    "MATCH (x:Program {designation: 'Flynn'}) "
                    "((a)-[:TRUSTS]->(b)){1,} SET x.cycles = 1",
                    budget=QueryBudget(max_rows=0),
                )
            result = graph.query("MATCH (n:Program) RETURN n.cycles AS cycles")
        assert [row["cycles"] for row in result.rows] == [None, None, None]

    def test_memory_and_file_databases_agree(self, tmp_path: Path) -> None:
        query = (
            "MATCH ((a)-[r:TRUSTS]->(b)){2} "
            "RETURN [x IN a | x.designation] AS names, [x IN r | id(x)] AS rels "
            "ORDER BY names"
        )
        path = tmp_path / "grouped.db"

        def populate(graph: Graph) -> None:
            nodes = [
                graph.add_node("Program", designation=f"Program {index}") for index in range(3)
            ]
            graph.add_relationship(nodes[0], "TRUSTS", nodes[1])
            graph.add_relationship(nodes[1], "TRUSTS", nodes[2])
            graph.add_relationship(nodes[2], "TRUSTS", nodes[0])

        with Graph.open(":memory:") as memory:
            populate(memory)
            memory_rows = self.rows(memory.query(query))
        with Graph.open(str(path)) as stored:
            populate(stored)
            stored_rows = self.rows(stored.query(query))
        assert memory_rows
        assert memory_rows == stored_rows


class TestGroupedPathValue(TestGroupedFixtures):
    """Verify the selected group path is a real path value."""

    def test_group_path_value_is_a_path(self) -> None:
        with self.cycle_graph() as graph:
            result = graph.query("MATCH (p = (a)-[r:TRUSTS]->(b)){2} RETURN p LIMIT 1")
        path = result.rows[0]["p"]
        assert isinstance(path, GraphPath)
        assert len(path.relationships) == 2
        assert len(path.nodes) == 3
