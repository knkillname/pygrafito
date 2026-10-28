# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for clause-level match modes."""

import typing

import pytest

from pygrafito import Graph, QueryBudgetExceededError, QueryResult
from pygrafito.model import QueryBudget


class TestMatchModeFixtures:
    """Build the TRON graphs used by the match-mode tests."""

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
            Flynn with two separate TRUSTS relationships to Tron.
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
    def scalar(result: QueryResult) -> int:
        """Return the ``total`` column of a one-row result.

        Parameters
        ----------
        result : QueryResult
            Query result to read.

        Returns
        -------
        int
            Total from the first row.
        """
        return typing.cast(int, result.rows[0]["total"])

    @staticmethod
    def pairs(result: QueryResult) -> list[tuple[int, int]]:
        """Return the relationship-id columns in row order.

        Parameters
        ----------
        result : QueryResult
            Query result to read.

        Returns
        -------
        list[tuple[int, int]]
            Pairs of relationship ids.
        """
        return [(typing.cast(int, row["r"]), typing.cast(int, row["s"])) for row in result.rows]


class TestFixedMatchModes(TestMatchModeFixtures):
    """Verify the SQL matcher applies the clause rule."""

    TWO_PATTERNS = "MATCH (a)-[r:TRUSTS]->(b), (c)-[s:TRUSTS]->(d) "
    SHARED = "FILTER id(r) = id(s) RETURN count(*) AS total"
    PAIRS = (
        "MATCH (a)-[r:TRUSTS]->(b), (c)-[s:TRUSTS]->(d) RETURN id(r) AS r, id(s) AS s ORDER BY r, s"
    )

    def test_default_allows_a_shared_relationship(self) -> None:
        """Keep the current repeatable behavior without a keyword."""
        with self.parallel_graph() as graph:
            result = graph.query(self.TWO_PATTERNS + self.SHARED)
        assert self.scalar(result) == 2

    def test_repeatable_elements_allows_a_shared_relationship(self) -> None:
        """Accept an explicit repeatable mode with the same result."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH REPEATABLE ELEMENTS (a)-[r:TRUSTS]->(b), (c)-[s:TRUSTS]->(d) "
                "FILTER id(r) = id(s) RETURN count(*) AS total"
            )
        assert self.scalar(result) == 2

    def test_different_edges_rejects_a_shared_relationship(self) -> None:
        """Reject every pair that binds one relationship twice."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS]->(b), (c)-[s:TRUSTS]->(d) "
                "FILTER id(r) = id(s) RETURN count(*) AS total"
            )
        assert self.scalar(result) == 0

    def test_parallel_relationships_stay_distinct(self) -> None:
        """Allow two different parallel relationships in one clause."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS]->(b), (c)-[s:TRUSTS]->(d) "
                "RETURN id(r) AS r, id(s) AS s ORDER BY r, s"
            )
        assert self.pairs(result) == [(1, 2), (2, 1)]

    def test_self_loop_consumes_one_relationship(self) -> None:
        """Reject the same self-loop at two positions."""
        with self.self_loop_graph() as graph:
            shared = graph.query(self.TWO_PATTERNS + self.SHARED)
            different = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS]->(b), (c)-[s:TRUSTS]->(d) "
                "FILTER id(r) = id(s) RETURN count(*) AS total"
            )
        assert self.scalar(shared) == 1
        assert self.scalar(different) == 0

    def test_nodes_may_repeat(self) -> None:
        """Allow a route that revisits a node without reusing an edge."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS]->(b), (b)-[s:TRUSTS]->(c), "
                "(c)-[t:TRUSTS]->(a) RETURN count(*) AS total"
            )
        assert self.scalar(result) == 3

    def test_already_unique_clause_is_unchanged(self) -> None:
        """Keep rows and order when no relationship could repeat."""
        query = (
            "MATCH {mode}(a:Program {{designation: 'Flynn'}})-[r:TRUSTS]->(b) "
            "RETURN b.designation AS name ORDER BY name"
        )
        with self.cycle_graph() as graph:
            default = graph.query(query.format(mode=""))
            different = graph.query(query.format(mode="DIFFERENT EDGES "))
        assert default.rows == different.rows


class TestPathModeIntersection(TestMatchModeFixtures):
    """Verify path modes and the match mode both apply."""

    def test_walk_with_different_edges_rejects_reuse(self) -> None:
        """Forbid an edge-reusing walk when the clause says DIFFERENT EDGES."""
        with self.self_loop_graph() as graph:
            walk = graph.query("MATCH WALK (a)-[r:TRUSTS*2]->(b) RETURN count(*) AS total")
            different = graph.query(
                "MATCH DIFFERENT EDGES WALK (a)-[r:TRUSTS*2]->(b) RETURN count(*) AS total"
            )
        assert self.scalar(walk) == 1
        assert self.scalar(different) == 0

    def test_trail_and_different_edges_agree(self) -> None:
        """Keep the TRAIL result when the clause adds DIFFERENT EDGES."""
        with self.cycle_graph() as graph:
            trail = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS*4]->(b) "
                "RETURN count(*) AS total"
            )
            different = graph.query(
                "MATCH DIFFERENT EDGES TRAIL (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*4]->(b) RETURN count(*) AS total"
            )
        assert self.scalar(trail) == 0
        assert self.scalar(different) == 0

    def test_repeatable_loosens_trail_only_across_paths(self) -> None:
        """Allow two TRAIL paths to share a node pair under repeatable elements."""
        with self.parallel_graph() as graph:
            repeatable = graph.query(
                "MATCH REPEATABLE ELEMENTS TRAIL (a)-[r:TRUSTS]->(b), "
                "TRAIL (c)-[s:TRUSTS]->(d) RETURN count(*) AS total"
            )
            different = graph.query(
                "MATCH DIFFERENT EDGES TRAIL (a)-[r:TRUSTS]->(b), "
                "TRAIL (c)-[s:TRUSTS]->(d) RETURN count(*) AS total"
            )
        assert self.scalar(repeatable) == 4
        assert self.scalar(different) == 2

    def test_simple_keeps_its_closed_path_rule(self) -> None:
        """Allow SIMPLE's closing node when every edge is distinct."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES SIMPLE (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*3]->(b) RETURN count(*) AS total"
            )
        assert self.scalar(result) == 1

    def test_acyclic_keeps_its_closed_path_rule(self) -> None:
        """Reject ACYCLIC's closing node even when every edge is distinct."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES ACYCLIC (a:Program {designation: 'Flynn'})"
                "-[:TRUSTS*3]->(b) RETURN count(*) AS total"
            )
        assert self.scalar(result) == 0


class TestQuantifiedMatchModes(TestMatchModeFixtures):
    """Verify the pattern engine applies the clause rule."""

    def test_quantified_clause_rejects_cross_pattern_reuse(self) -> None:
        """Return only edge-disjoint quantified pairs on the parallel fixture."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS*1]->(b), (c)-[s:TRUSTS*1]->(d) "
                "RETURN id(r[0]) AS r, id(s[0]) AS s ORDER BY r, s"
            )
        assert self.pairs(result) == [(1, 2), (2, 1)]

    def test_quantified_clause_rejects_reuse_across_segments(self) -> None:
        """Forbid reusing one relationship across segments of a clause."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS*1]->(b), (c)-[s:TRUSTS*1]->(d) "
                "RETURN count(*) AS total"
            )
        assert self.scalar(result) == 0

    def test_quantified_parallel_route_stays_distinct(self) -> None:
        """Keep the two parallel edges as distinct quantified matches."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS*1]->(b) RETURN count(*) AS total"
            )
        assert self.scalar(result) == 2

    def test_mixed_clause_uses_one_matcher(self) -> None:
        """Agree between the fixed and mixed clause forms."""
        with self.parallel_graph() as graph:
            fixed = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS]->(b), (c)-[s:TRUSTS*1]->(d) "
                "RETURN id(r) AS r, id(s[0]) AS s ORDER BY r, s"
            )
            mixed = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS*1]->(b), (c)-[s:TRUSTS]->(d) "
                "RETURN id(r[0]) AS r, id(s) AS s ORDER BY r, s"
            )
        assert self.pairs(fixed) == self.pairs(mixed)

    def test_optional_different_edges_null_extends(self) -> None:
        """Preserve the input row when no edge-disjoint match exists."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Quorra'}) "
                "OPTIONAL MATCH DIFFERENT EDGES (a)-[r:TRUSTS]->(b), "
                "(a)-[s:TRUSTS]->(c) RETURN b.designation AS first"
            )
        assert result.rows[0]["first"] is None

    def test_rejected_candidates_count_against_the_budget(self) -> None:
        """Charge expansions before the match-mode check."""
        with self.parallel_graph() as graph, pytest.raises(QueryBudgetExceededError):
            graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS*1]->(b), (c)-[s:TRUSTS*1]->(d) "
                "RETURN count(*) AS total",
                budget=QueryBudget(max_expansions=1),
            )


class TestMatchModeScope(TestMatchModeFixtures):
    """Verify the mode is scoped to its own clause."""

    def test_later_clause_may_rebind_an_earlier_edge(self) -> None:
        """Allow a later DIFFERENT EDGES clause to reuse an earlier binding."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH ()-[r:TRUSTS]->() WITH r "
                "MATCH DIFFERENT EDGES (a)-[s:TRUSTS]->(b) "
                "RETURN id(r) AS r, id(s) AS s"
            )
        assert any(row["r"] == row["s"] for row in result.rows)

    def test_repeatable_and_different_stages_keep_the_default(self) -> None:
        """Keep a default clause unconstrained after a different one."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH DIFFERENT EDGES (a)-[r:TRUSTS]->(b) "
                "MATCH (c)-[s:TRUSTS]->(d) "
                "FILTER id(r) = id(s) RETURN count(*) AS total"
            )
        assert self.scalar(result) > 0
