# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for WALK, TRAIL, SIMPLE, and ACYCLIC path matching."""

from pygrafito import Graph, QueryResult


class TestPathModeFixtures:
    """Build the directed cycle and self-loop fixtures shared by the tests."""

    @staticmethod
    def cycle_graph() -> Graph:
        """Return a graph with a directed three-program cycle.

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
    def self_loop_graph() -> Graph:
        """Return a graph with one program and a self-loop.

        Returns
        -------
        Graph
            Quorra with a TRUSTS self-loop.
        """
        graph = Graph.open(":memory:")
        quorra = graph.add_node("Program", designation="Quorra")
        graph.add_relationship(quorra, "TRUSTS", quorra)
        return graph

    @staticmethod
    def diamond_graph() -> Graph:
        """Return a graph with two routes from Flynn to the Grid.

        Returns
        -------
        Graph
            Flynn -> Tron -> Grid and Flynn -> Clu -> Grid.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        clu = graph.add_node("Program", designation="Clu")
        grid = graph.add_node("Place", designation="The Grid")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(flynn, "TRUSTS", clu)
        graph.add_relationship(tron, "TRUSTS", grid)
        graph.add_relationship(clu, "TRUSTS", grid)
        return graph

    @staticmethod
    def parallel_graph() -> Graph:
        """Return a graph with two parallel TRUSTS relationships.

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
    def destinations(result: QueryResult) -> list[object]:
        """Return the ``name`` column of a query result.

        Parameters
        ----------
        result : QueryResult
            Query result to read.

        Returns
        -------
        list[object]
            Projected names in row order.
        """
        rows = result.rows
        return [row["name"] for row in rows]


class TestQuantifiedPathModes(TestPathModeFixtures):
    """Check the modes through the in-memory quantified matcher."""

    def test_walk_reuses_a_relationship(self) -> None:
        """Allow a four-hop walk around a three-edge cycle."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH WALK (a:Program {designation: 'Flynn'})-[:TRUSTS*4]->(b) "
                "RETURN b.designation AS name"
            )
        assert result.rows

    def test_trail_rejects_reusing_a_relationship(self) -> None:
        """Reject the four-hop route that reuses its first relationship."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS*4]->(b) "
                "RETURN b.designation AS name"
            )
        assert result.rows == ()

    def test_trail_allows_a_closed_three_edge_path(self) -> None:
        """Allow a closed path that uses three distinct relationships."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS*3]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.destinations(result) == ["Flynn"]

    def test_simple_allows_a_closed_path(self) -> None:
        """Allow SIMPLE to return to the start node at the end."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH SIMPLE (a:Program {designation: 'Flynn'})-[:TRUSTS*3]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.destinations(result) == ["Flynn"]

    def test_acyclic_rejects_a_closed_path(self) -> None:
        """Reject ACYCLIC when the path returns to its start."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH ACYCLIC (a:Program {designation: 'Flynn'})-[:TRUSTS*3]->(b) "
                "RETURN b.designation AS name"
            )
        assert result.rows == ()

    def test_simple_rejects_a_mid_path_repeat(self) -> None:
        """Reject SIMPLE when a node repeats before the path ends."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH SIMPLE (a:Program {designation: 'Flynn'})-[:TRUSTS*4]->(b) "
                "RETURN b.designation AS name"
            )
        assert result.rows == ()

    def test_legacy_quantifier_stays_a_trail(self) -> None:
        """Keep the legacy quantifier's TRAIL default without a mode."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS*4]->(b) "
                "RETURN b.designation AS name"
            )
        assert result.rows == ()


class TestCompiledPathModes(TestPathModeFixtures):
    """Check the modes through the indexed fixed-length compiler."""

    def test_walk_reuses_a_self_loop(self) -> None:
        """Allow the same self-loop at two positions under WALK."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH WALK (a:Program {designation: 'Quorra'})-[r:TRUSTS]->(b)-[s:TRUSTS]->(c) "
                "RETURN c.designation AS name"
            )
        assert self.destinations(result) == ["Quorra"]

    def test_trail_rejects_a_reused_self_loop(self) -> None:
        """Reject the same self-loop at two positions under TRAIL."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Quorra'})-[r:TRUSTS]->(b)-[s:TRUSTS]->(c) "
                "RETURN c.designation AS name"
            )
        assert result.rows == ()

    def test_simple_allows_a_closed_fixed_path(self) -> None:
        """Allow the start and end node to match under SIMPLE."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH SIMPLE (a:Program {designation: 'Flynn'})-[:TRUSTS]->(b)"
                "-[:TRUSTS]->(c)-[:TRUSTS]->(d) RETURN d.designation AS name"
            )
        assert self.destinations(result) == ["Flynn"]

    def test_acyclic_rejects_a_closed_fixed_path(self) -> None:
        """Reject the start and end node matching under ACYCLIC."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH ACYCLIC (a:Program {designation: 'Flynn'})-[:TRUSTS]->(b)"
                "-[:TRUSTS]->(c)-[:TRUSTS]->(d) RETURN d.designation AS name"
            )
        assert result.rows == ()

    def test_default_walk_matches_the_quantified_result(self) -> None:
        """Keep the compiled and in-memory paths consistent under WALK."""
        with self.self_loop_graph() as graph:
            fixed = graph.query(
                "MATCH (a:Program {designation: 'Quorra'})-[r:TRUSTS]->(b)-[s:TRUSTS]->(c) "
                "RETURN c.designation AS name"
            )
            quantified = graph.query(
                "MATCH WALK (a:Program {designation: 'Quorra'})-[:TRUSTS*2]->(c) "
                "RETURN c.designation AS name"
            )
        assert self.destinations(fixed) == self.destinations(quantified)


class TestPathModeCoverage(TestPathModeFixtures):
    """Cover the diamond and parallel-relationship fixtures for each mode."""

    def test_diamond_two_routes_survive_every_mode(self) -> None:
        """Return both two-hop routes under each mode."""
        with self.diamond_graph() as graph:
            for mode in ("WALK", "TRAIL", "SIMPLE", "ACYCLIC"):
                result = graph.query(
                    f"MATCH {mode} (a:Program {{designation: 'Flynn'}})-[:TRUSTS*2]->(b) "
                    "RETURN b.designation AS name"
                )
                assert self.destinations(result) == ["The Grid", "The Grid"], mode

    def test_parallel_relationships_are_distinct_matches(self) -> None:
        """Match both parallel relationships as separate rows."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[r:TRUSTS]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.destinations(result) == ["Tron", "Tron"]


class TestCanonicalQuantifier(TestPathModeFixtures):
    """Check the closed canonical quantifier forms end to end."""

    def test_exact_count(self) -> None:
        """Match exactly two hops."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS{2}]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.destinations(result) == ["Clu"]

    def test_bounded_range(self) -> None:
        """Match one through three hops."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS{1,3}]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.destinations(result) == ["Tron", "Clu", "Flynn"]

    def test_upper_bound_only_includes_zero_hops(self) -> None:
        """Include the zero-hop match for an upper-bound-only quantifier."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS{,2}]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.destinations(result) == ["Flynn", "Tron", "Clu"]

    def test_canonical_default_walks_while_legacy_trails(self) -> None:
        """Use WALK for the canonical form and TRAIL for the legacy form."""
        with self.cycle_graph() as graph:
            canonical = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS{4}]->(b) "
                "RETURN b.designation AS name"
            )
            legacy = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS*4]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.destinations(canonical) == ["Tron"]
        assert legacy.rows == ()
