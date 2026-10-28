# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for whole-path search prefixes and their evaluator."""

import typing
from collections.abc import Iterator
from pathlib import Path

import pytest

from pygrafito import (
    Graph,
    QueryBudgetExceededError,
    QueryResult,
    QuerySemanticError,
    QuerySyntaxError,
)
from pygrafito.engine.query.ast import Match, PathMode, PathSearchKind
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.plan import Plan, PlanBuilder
from pygrafito.engine.query.semantic import Analysis, SemanticAnalyzer, VariableKind
from pygrafito.engine.traversal import DatabaseNeighborhood
from pygrafito.model import Path as GraphPath
from pygrafito.model import QueryBudget, Relationship


class TestSearchFixtures:
    """Build the TRON graphs used by the path-search tests."""

    @staticmethod
    def diamond_graph() -> Graph:
        """Return two two-hop routes and one three-hop route.

        Returns
        -------
        Graph
            Flynn reaches Quorra through Tron, through Clu, and through
            Tron then Clu.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        clu = graph.add_node("Program", designation="Clu")
        quorra = graph.add_node("Program", designation="Quorra")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(tron, "TRUSTS", quorra)
        graph.add_relationship(flynn, "TRUSTS", clu)
        graph.add_relationship(clu, "TRUSTS", quorra)
        graph.add_relationship(tron, "TRUSTS", clu)
        return graph

    @staticmethod
    def cycle_graph() -> Graph:
        """Return a directed three-program cycle.

        Returns
        -------
        Graph
            Flynn -> Tron -> Clu -> Flynn.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        clu = graph.add_node("Program", designation="Clu")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(tron, "TRUSTS", clu)
        graph.add_relationship(clu, "TRUSTS", flynn)
        return graph

    @staticmethod
    def parallel_graph() -> Graph:
        """Return two parallel trust relationships.

        Returns
        -------
        Graph
            Flynn with two TRUSTS relationships to Tron.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(flynn, "TRUSTS", tron)
        return graph

    @staticmethod
    def self_loop_graph() -> Graph:
        """Return a graph with one trust self-loop.

        Returns
        -------
        Graph
            Quorra with one TRUSTS self-loop.
        """
        graph = Graph.open(":memory:")
        quorra = graph.add_node("Program", designation="Quorra")
        graph.add_relationship(quorra, "TRUSTS", quorra)
        return graph

    @staticmethod
    def unreachable_graph() -> Graph:
        """Return a reachable and an isolated program.

        Returns
        -------
        Graph
            Flynn trusts Tron; Quorra is isolated.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        graph.add_node("Program", designation="Quorra")
        graph.add_relationship(flynn, "TRUSTS", tron)
        return graph

    @staticmethod
    def star_graph(leaves: int = 20) -> Graph:
        """Return Flynn with many direct trust relationships.

        Parameters
        ----------
        leaves : int, optional
            Number of leaf programs, by default 20.

        Returns
        -------
        Graph
            Flynn trusts each leaf program.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        for index in range(leaves):
            leaf = graph.add_node("Program", designation=f"Program {index}")
            graph.add_relationship(flynn, "TRUSTS", leaf)
        return graph

    @staticmethod
    def many_starts_graph(programs: int = 20) -> Graph:
        """Return many programs that all trust one shared place.

        Parameters
        ----------
        programs : int, optional
            Number of start programs, by default 20.

        Returns
        -------
        Graph
            Each program has one TRUSTS relationship to The Grid.
        """
        graph = Graph.open(":memory:")
        grid = graph.add_node("Place", designation="The Grid")
        for index in range(programs):
            program = graph.add_node("Program", designation=f"Program {index}")
            graph.add_relationship(program, "TRUSTS", grid)
        return graph

    @staticmethod
    def path_names(result: QueryResult) -> list[list[str | None]]:
        """Return the projected path node designations.

        Parameters
        ----------
        result : QueryResult
            Query result carrying a ``names`` list column.

        Returns
        -------
        list[list[str | None]]
            Node names per row.
        """
        return [typing.cast(list[str | None], row["names"]) for row in result.rows]

    @staticmethod
    def path_lengths(result: QueryResult) -> list[int]:
        """Return the projected path lengths.

        Parameters
        ----------
        result : QueryResult
            Query result carrying an ``n`` column.

        Returns
        -------
        list[int]
            Path lengths per row.
        """
        return [typing.cast(int, row["n"]) for row in result.rows]


class TestSearchParsing:
    """Verify the path-search prefix syntax and placement."""

    @staticmethod
    def match(text: str) -> Match:
        """Return the first match clause of a parsed statement.

        Parameters
        ----------
        text : str
            Query source.

        Returns
        -------
        Match
            First match clause.
        """
        statement = Parser.parse_statement(text)
        clauses = statement.clauses
        if not isinstance(clauses[0], Match):
            raise AssertionError("expected a match clause")
        return clauses[0]

    def test_no_prefix_is_the_default(self) -> None:
        """Leave a plain path without a search selection."""
        assert self.match("MATCH (a) RETURN a").patterns[0].search is None

    @pytest.mark.parametrize(
        ("text", "kind", "k"),
        [
            ("MATCH p = ANY (a) RETURN p", PathSearchKind.ANY, None),
            ("MATCH p = ANY SHORTEST (a) RETURN p", PathSearchKind.ANY_SHORTEST, None),
            ("MATCH p = ALL SHORTEST (a) RETURN p", PathSearchKind.ALL_SHORTEST, None),
            ("MATCH p = SHORTEST 2 (a) RETURN p", PathSearchKind.SHORTEST, 2),
            ("MATCH p = SHORTEST 0 (a) RETURN p", PathSearchKind.SHORTEST, 0),
        ],
    )
    def test_prefixes(self, text: str, kind: PathSearchKind, k: int | None) -> None:
        """Parse every prefix after the path variable."""
        search = self.match(text).patterns[0].search
        assert search is not None
        assert search.kind is kind
        assert search.k == k

    def test_prefix_precedes_the_path_mode(self) -> None:
        """Accept a per-path mode after the prefix."""
        pattern = self.match("MATCH p = ANY SHORTEST WALK (a) RETURN p").patterns[0]
        assert pattern.search is not None
        assert pattern.search.kind is PathSearchKind.ANY_SHORTEST
        assert pattern.mode is PathMode.WALK

    def test_clause_mode_precedes_the_prefix(self) -> None:
        """Accept a clause mode before the path variable and prefix."""
        clause = self.match("MATCH TRAIL p = ANY (a) RETURN p")
        assert clause.mode is PathMode.TRAIL
        assert clause.patterns[0].variable == "p"
        assert clause.patterns[0].search is not None
        assert clause.patterns[0].search.kind is PathSearchKind.ANY

    def test_prefix_without_a_path_variable(self) -> None:
        """Allow a prefix on an unbound path."""
        search = self.match("MATCH ANY SHORTEST (a)-[r]->(b) RETURN r").patterns[0].search
        assert search is not None
        assert search.kind is PathSearchKind.ANY_SHORTEST

    def test_prefix_on_a_comma_separated_path(self) -> None:
        """Apply a prefix to one path of a comma-separated clause."""
        clause = self.match("MATCH (a), ANY (b) RETURN a")
        assert clause.patterns[0].search is None
        assert clause.patterns[1].search is not None

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH p = SHORTEST (a) RETURN p",
            "MATCH p = SHORTEST $k (a) RETURN p",
            "MATCH p = SHORTEST 1.5 (a) RETURN p",
            "MATCH p = SHORTEST 1 + 1 (a) RETURN p",
            "MATCH p = ALL (a) RETURN p",
        ],
    )
    def test_malformed_prefixes_are_rejected(self, text: str) -> None:
        """Reject a missing or non-literal count and a missing SHORTEST."""
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement(text)

    def test_prefix_inside_parentheses_is_rejected(self) -> None:
        """Reject a prefix where a node pattern starts."""
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement("MATCH (ANY (a)) RETURN a")
        assert "path-search prefix" in str(caught.value)
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement("MATCH ((ANY (a)-[:TRUSTS]->(b))){2} RETURN a")

    @pytest.mark.parametrize(
        "text",
        [
            "INSERT ANY (a)-[:TRUSTS]->(b)",
            "CREATE SHORTEST 2 (n:Program)",
            "MERGE ALL SHORTEST (n:Program)",
        ],
    )
    def test_write_patterns_have_no_search_prefix(self, text: str) -> None:
        """Reject a search prefix in a data pattern."""
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement(text)


class TestSearchSemantics:
    """Verify static validation and plan propagation."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_negative_count_is_rejected(self) -> None:
        """Reject `SHORTEST -1` with a source position."""
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH p = SHORTEST -1 (a) RETURN p")
        assert caught.value.line == 1
        assert caught.value.column == 11

    def test_zero_count_is_valid(self) -> None:
        """Accept `SHORTEST 0` as a valid empty selection."""
        self.analyze("MATCH p = SHORTEST 0 (a) RETURN p")

    def test_path_variable_binds_a_path(self) -> None:
        """Keep the path variable's `PATH` kind with a prefix."""
        analysis = self.analyze("MATCH p = ANY SHORTEST (a)-[r]->(b) RETURN p")
        assert analysis.variable_kinds["p"] is VariableKind.PATH

    def test_prefix_without_path_variable_still_binds_nodes(self) -> None:
        """Bind the node and relationship variables of an unbound path."""
        analysis = self.analyze("MATCH ANY SHORTEST (a)-[r]->(b) RETURN a, r, b")
        assert analysis.variable_kinds["a"] is VariableKind.NODE
        assert analysis.variable_kinds["r"] is VariableKind.RELATIONSHIP
        assert analysis.variable_kinds["b"] is VariableKind.NODE

    def test_plan_names_the_search_operator(self) -> None:
        """Expose the prefix in the physical plan."""
        plan = PlanBuilder.build(self.analyze("MATCH p = ANY SHORTEST (a) RETURN p"))
        assert isinstance(plan, Plan)
        assert "path_search" in plan.operators

    def test_plain_pattern_keeps_its_plan(self) -> None:
        """Leave a pattern without a prefix on the existing plan."""
        plain = PlanBuilder.build(self.analyze("MATCH (a) RETURN a"))
        searched = PlanBuilder.build(self.analyze("MATCH ANY (a) RETURN a"))
        assert isinstance(plain, Plan)
        assert isinstance(searched, Plan)
        assert "path_search" not in plain.operators
        assert "path_search" in searched.operators


class TestSearchSelection(TestSearchFixtures):
    """Verify per-partition selection on the TRON fixtures."""

    def test_any_selects_one_path_per_pair(self) -> None:
        """Return one route from Flynn to Quorra under `ANY`."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH p = ANY (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*1..3]->(b:Program {designation: 'Quorra'}) "
                "RETURN length(p) AS n, [x IN nodes(p) | x.designation] AS names"
            )
        assert self.path_names(result) == [["Flynn", "Tron", "Quorra"]]

    def test_any_shortest_selects_a_minimum_path(self) -> None:
        """Return a length-two route when longer routes exist."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH p = ANY SHORTEST (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*1..3]->(b:Program {designation: 'Quorra'}) "
                "RETURN length(p) AS n"
            )
        assert self.path_lengths(result) == [2]

    def test_all_shortest_returns_both_minimum_routes(self) -> None:
        """Return both two-hop routes from Flynn to Quorra."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH p = ALL SHORTEST (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*1..3]->(b:Program {designation: 'Quorra'}) "
                "RETURN length(p) AS n, [x IN nodes(p) | x.designation] AS names"
            )
        assert self.path_names(result) == [
            ["Flynn", "Tron", "Quorra"],
            ["Flynn", "Clu", "Quorra"],
        ]

    def test_shortest_k_returns_increasing_lengths(self) -> None:
        """Return two minimum routes under `SHORTEST 2`."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH p = SHORTEST 2 (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*1..3]->(b:Program {designation: 'Quorra'}) "
                "RETURN length(p) AS n, [x IN nodes(p) | x.designation] AS names"
            )
        assert self.path_lengths(result) == [2, 2]

    def test_shortest_three_includes_the_third_path(self) -> None:
        """Add the three-hop route under `SHORTEST 3`."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH p = SHORTEST 3 (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*1..3]->(b:Program {designation: 'Quorra'}) "
                "RETURN length(p) AS n ORDER BY n"
            )
        assert self.path_lengths(result) == [2, 2, 3]

    def test_zero_k_selects_nothing(self) -> None:
        """Return no rows for `SHORTEST 0`."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH p = SHORTEST 0 (a:Program)-[:TRUSTS*1..2]->(b:Program) RETURN p"
            )
        assert result.rows == ()

    def test_unreachable_pair_is_absent(self) -> None:
        """Return no row when no route reaches the candidate end."""
        with self.unreachable_graph() as graph:
            result = graph.query(
                "MATCH p = ANY SHORTEST (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*1..2]->(b:Program {designation: 'Quorra'}) RETURN p"
            )
        assert result.rows == ()

    def test_parallel_relationships_are_distinct_paths(self) -> None:
        """Return both parallel relationships under `ALL SHORTEST`."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH p = ALL SHORTEST (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS]->(b:Program {designation: 'Tron'}) RETURN p"
            )
        ids: list[int] = []
        for row in result.rows:
            path = row["p"]
            assert isinstance(path, GraphPath)
            ids.append(path.relationships[0].id)
        assert ids == [1, 2]

    def test_any_selects_one_of_the_parallel_relationships(self) -> None:
        """Select the deterministic first parallel relationship under `ANY`."""
        with self.parallel_graph() as graph:
            result = graph.query("MATCH p = ANY (a:Program)-[:TRUSTS]->(b:Program) RETURN p")
        assert len(result.rows) == 1

    def test_self_loop_is_a_path(self) -> None:
        """Select the self-loop path."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH p = ALL SHORTEST (a:Program)-[:TRUSTS]->(b:Program) RETURN p"
            )
        assert len(result.rows) == 1

    def test_shortest_k_returns_distinct_walk_lengths_on_a_self_loop(self) -> None:
        """Return one-hop and two-hop self-loop walks under canonical bounds."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH p = SHORTEST 2 (a:Program)-[:TRUSTS{1,2}]->(b:Program) "
                "RETURN length(p) AS n ORDER BY n"
            )
        assert self.path_lengths(result) == [1, 2]

    def test_fixed_search_keeps_the_regular_bindings(self) -> None:
        """Return the same node and relationship bindings as the regular matcher."""
        with self.diamond_graph() as graph:
            regular = graph.query(
                "MATCH (a:User {designation: 'Kevin Flynn'})-[r:PARENT_OF]->(b) "
                "RETURN b.designation AS name, id(r) AS edge"
            )
            searched = graph.query(
                "MATCH p = ANY SHORTEST (a:User {designation: 'Kevin Flynn'})"
                "-[r:PARENT_OF]->(b) RETURN b.designation AS name, id(r) AS edge"
            )
        assert [dict(row) for row in regular.rows] == [dict(row) for row in searched.rows]

    def test_output_order_is_by_partition(self) -> None:
        """Order rows by start and end node identifier without ORDER BY."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH p = ANY SHORTEST (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*1..2]->(b:Program) RETURN id(b) AS target"
            )
        targets = [typing.cast(int, row["target"]) for row in result.rows]
        assert targets == sorted(targets)
        assert len(targets) == len(set(targets))


class TestSearchModes(TestSearchFixtures):
    """Verify search interaction with path and match modes."""

    def test_trail_excludes_edge_reusing_candidates(self) -> None:
        """Keep edge reuse out of the selected set under `TRAIL`."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH p = SHORTEST 2 TRAIL (a:Program)-[:TRUSTS{1,2}]->(b:Program) "
                "RETURN length(p) AS n ORDER BY n"
            )
        assert self.path_lengths(result) == [1]

    def test_different_edges_narrows_the_search(self) -> None:
        """Reject a candidate that would share an edge across patterns."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES p = ANY SHORTEST "
                "(a:Program)-[r:TRUSTS]->(b:Program), "
                "(c:Program)-[s:TRUSTS]->(d:Program) "
                "RETURN id(r) AS first, id(s) AS second"
            )
        assert all(row["first"] != row["second"] for row in result.rows)

    def test_per_path_mode_overrides_the_clause_mode(self) -> None:
        """Apply the per-path mode to a searched path."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH WALK p = ANY SHORTEST TRAIL "
                "(a:Program)-[:TRUSTS{1,2}]->(b:Program) "
                "RETURN length(p) AS n ORDER BY n"
            )
        assert self.path_lengths(result) == [1]

    def test_simple_and_acyclic_apply_before_selection(self) -> None:
        """Keep SIMPLE's closing node and reject it under ACYCLIC."""
        with self.cycle_graph() as graph:
            simple = graph.query(
                "MATCH p = ANY SHORTEST SIMPLE (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS{2,3}]->(b:Program {designation: 'Flynn'}) "
                "RETURN length(p) AS n"
            )
            acyclic = graph.query(
                "MATCH p = ANY SHORTEST ACYCLIC (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS{2,3}]->(b:Program {designation: 'Flynn'}) "
                "RETURN length(p) AS n"
            )
        assert self.path_lengths(simple) == [3]
        assert acyclic.rows == ()

    def test_budget_counts_rejected_candidates(self) -> None:
        """Charge expansions that a mode later rejects."""
        with self.self_loop_graph() as graph, pytest.raises(QueryBudgetExceededError):
            graph.query(
                "MATCH p = SHORTEST 2 TRAIL (a:Program)-[:TRUSTS{1,2}]->(b:Program) RETURN p",
                budget=QueryBudget(max_expansions=1),
            )


class TestSearchExecution(TestSearchFixtures):
    """Verify demand, optional match, subqueries, snapshots, and rollback."""

    def test_limit_reduces_expansions(self) -> None:
        """Stop partition discovery once a final LIMIT is satisfied."""
        with self.many_starts_graph(20) as graph:
            limited = graph.query(
                "MATCH p = ANY SHORTEST (a:Program)"
                "-[:TRUSTS{1,}]->(b:Place {designation: 'The Grid'}) "
                "RETURN p LIMIT 1",
                budget=QueryBudget(max_expansions=2),
            )
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    "MATCH p = ANY SHORTEST (a:Program)"
                    "-[:TRUSTS{1,}]->(b:Place {designation: 'The Grid'}) "
                    "RETURN p",
                    budget=QueryBudget(max_expansions=2),
                )
        assert len(limited.rows) == 1

    def test_optional_match_null_extends(self) -> None:
        """Preserve the input row when a search selection is empty."""
        with self.unreachable_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'}) "
                "OPTIONAL MATCH p = ANY SHORTEST (a)-[:TRUSTS*1..2]->"
                "(b:Program {designation: 'Quorra'}) RETURN b.designation AS name"
            )
        assert result.rows[0]["name"] is None

    def test_exists_stops_after_the_first_selected_row(self) -> None:
        """Let EXISTS consume only the first selected row."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'}) "
                "RETURN EXISTS { MATCH p = ALL SHORTEST (a)-[:TRUSTS*1..3]->"
                "(b:Program {designation: 'Quorra'}) } AS found"
            )
        assert result.rows[0]["found"] is True

    def test_exists_stops_before_count_must_finish(self) -> None:
        """Stop EXISTS after the first selected row while COUNT drains all."""
        query = (
            "MATCH (a:Program {designation: 'Flynn'}) RETURN __KIND__ { "
            "MATCH p = ANY SHORTEST (a)-[:TRUSTS{1,3}]->(b) } AS value"
        )
        with self.diamond_graph() as graph:
            exists = graph.query(
                query.replace("__KIND__", "EXISTS"),
                budget=QueryBudget(max_expansions=10),
            )
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    query.replace("__KIND__", "COUNT"),
                    budget=QueryBudget(max_expansions=10),
                )
            counted = graph.query(
                query.replace("__KIND__", "COUNT"),
                budget=QueryBudget(max_expansions=25),
            )
        assert exists.rows[0]["value"] is True
        assert counted.rows[0]["value"] == 3

    def test_count_consumes_every_selected_row(self) -> None:
        """Count both shortest routes from a subquery."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'}) "
                "RETURN COUNT { MATCH p = ALL SHORTEST (a)-[:TRUSTS*1..3]->"
                "(b:Program {designation: 'Quorra'}) } AS total"
            )
        assert result.rows[0]["total"] == 2

    def test_search_uses_the_statement_snapshot(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ignore a concurrent write during a search."""
        path = tmp_path / "search.db"
        original = DatabaseNeighborhood.edges
        write_done: list[bool] = []

        def inject_write(
            self: DatabaseNeighborhood,
            node_id: int,
            direction: object,
            labels: frozenset[str] | None,
        ) -> Iterator[tuple[Relationship, int]]:
            if not write_done:
                with Graph.open(str(path)) as other:
                    other.add_node("Program", designation="Rinzler")
                write_done.append(True)
            yield from original(self, node_id, direction, labels)  # type: ignore[arg-type]

        monkeypatch.setattr(DatabaseNeighborhood, "edges", inject_write)
        with Graph.open(str(path)) as graph:
            flynn = graph.add_node("Program", designation="Flynn")
            tron = graph.add_node("Program", designation="Tron")
            clu = graph.add_node("Program", designation="Clu")
            graph.add_relationship(flynn, "TRUSTS", tron)
            graph.add_relationship(tron, "TRUSTS", clu)
            graph.add_relationship(clu, "TRUSTS", flynn)
            result = graph.query(
                "MATCH p = ANY SHORTEST (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS{1,}]->(b:Program) "
                "RETURN count(DISTINCT b.designation) AS total"
            )
        assert write_done
        assert result.rows[0]["total"] == 3

    def test_memory_and_file_databases_agree(self, tmp_path: Path) -> None:
        """Return the same selected paths from memory and file storage."""
        path = tmp_path / "search.db"
        queries = [
            "MATCH p = ANY SHORTEST (a:Program {designation: 'Flynn'})"
            "-[:TRUSTS{1,3}]->(b:Program {designation: 'Quorra'}) "
            "RETURN length(p) AS n, [x IN nodes(p) | x.designation] AS names",
            "MATCH p = ALL SHORTEST (a:Program {designation: 'Flynn'})"
            "-[:TRUSTS{1,3}]->(b:Program {designation: 'Quorra'}) "
            "RETURN length(p) AS n, [x IN nodes(p) | x.designation] AS names",
            "MATCH p = SHORTEST 3 (a:Program {designation: 'Flynn'})"
            "-[:TRUSTS{1,3}]->(b:Program {designation: 'Quorra'}) "
            "RETURN length(p) AS n ORDER BY n",
        ]

        def populate(graph: Graph) -> None:
            flynn = graph.add_node("Program", designation="Flynn")
            tron = graph.add_node("Program", designation="Tron")
            clu = graph.add_node("Program", designation="Clu")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(flynn, "TRUSTS", tron)
            graph.add_relationship(tron, "TRUSTS", quorra)
            graph.add_relationship(flynn, "TRUSTS", clu)
            graph.add_relationship(clu, "TRUSTS", quorra)
            graph.add_relationship(tron, "TRUSTS", clu)

        with Graph.open(":memory:") as memory:
            populate(memory)
            memory_rows = [[dict(row) for row in memory.query(query).rows] for query in queries]
        with Graph.open(str(path)) as stored:
            populate(stored)
            stored_rows = [[dict(row) for row in stored.query(query).rows] for query in queries]
        assert memory_rows == stored_rows

    def test_search_write_rolls_back_on_budget_failure(self) -> None:
        """Roll back a write when a search exceeds the budget."""
        with self.cycle_graph() as graph:
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    "MATCH p = ANY SHORTEST (a:Program {designation: 'Flynn'})"
                    "-[:TRUSTS{1,}]->(b:Program) SET b.cycles = 1",
                    budget=QueryBudget(max_rows=0),
                )
            result = graph.query("MATCH (n:Program) RETURN n.cycles AS cycles")
        assert [row["cycles"] for row in result.rows] == [None, None, None]

    def test_shortest_zero_charges_no_expansions(self) -> None:
        """Return no rows for `SHORTEST 0` without touching the graph."""
        with self.star_graph(3) as graph:
            result = graph.query(
                "MATCH p = SHORTEST 0 (a:Program)-[:TRUSTS{1,}]->(b:Program) RETURN p",
                budget=QueryBudget(max_expansions=0),
            )
        assert result.rows == ()
