# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for bounded matching of quantified relationship patterns."""

from collections.abc import Iterator

import pytest

from pygrafito import Graph, Relationship
from pygrafito.engine.query.results import QueryResult
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import Path


class _PatternGraph:
    """Provide a TRON fixture with diamond, cycle, parallel, and self-loop."""

    @pytest.fixture
    def graph(self) -> Iterator[Graph]:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node("ISO", "Program", designation="Quorra", cycles=37)
            tron = graph.add_node("Program", designation="Tron", cycles=40)
            clu = graph.add_node("Program", designation="Clu")
            rinzler = graph.add_node("Program", designation="Rinzler", cycles=36.0)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2021)
            graph.add_relationship(kevin, "ALLIES_WITH", tron, since_cycle=2020)
            graph.add_relationship(quorra, "ALLIES_WITH", clu, since_cycle=2020)
            graph.add_relationship(tron, "ALLIES_WITH", clu, since_cycle=2020)
            graph.add_relationship(clu, "OBSERVES", clu)
            graph.add_relationship(clu, "OBSERVES", rinzler)
            graph.add_relationship(rinzler, "OBSERVES", clu)
            yield graph

    @staticmethod
    def values(result: QueryResult) -> list[tuple[QueryValue, ...]]:
        return [tuple(row.values()) for row in result]

    def designations(self, result: QueryResult) -> list[str]:
        return [str(value) for (value,) in self.values(result)]


class TestBoundedPatterns(_PatternGraph):
    """Verify hop bounds, filters, uniqueness, and path values."""

    def test_exact_length(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*2]->(b) "
            "RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == ["Clu", "Clu", "Clu"]

    def test_bounded_range(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*1..2]->(b) "
            "RETURN count(*) AS total"
        )
        assert self.values(result) == [(6,)]

    def test_zero_hop_includes_the_start(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*0..1]->(b) "
            "RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == ["Kevin Flynn", "Quorra", "Quorra", "Tron"]

    def test_every_hop_applies_the_property_filter(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})"
            "-[:ALLIES_WITH*1..2 {since_cycle: 2020}]->(b) "
            "RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == ["Clu", "Clu", "Quorra", "Tron"]

    def test_direction_is_applied_per_hop(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Clu'})<-[r:ALLIES_WITH*1..2]-(b) "
            "RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == [
            "Kevin Flynn",
            "Kevin Flynn",
            "Kevin Flynn",
            "Quorra",
            "Tron",
        ]

    def test_trails_are_relationship_unique(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Clu'})-[r:OBSERVES*1..4]->(b) RETURN max(size(r)) AS longest"
        )
        assert self.values(result) == [(3,)]

    def test_nodes_may_repeat(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Clu'})-[r:OBSERVES*3..3]->(b) "
            "RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == ["Clu", "Clu"]

    def test_relationship_variable_binds_a_list(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[r:ALLIES_WITH*2..2]->(b) "
            "RETURN r, size(r) AS length"
        )
        relationships = result.rows[0]["r"]
        assert isinstance(relationships, list)
        assert all(isinstance(item, Relationship) for item in relationships)
        assert len(relationships) == 2
        assert result.rows[0]["length"] == 2

    def test_path_includes_expanded_relationships(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH p = (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*2..2]->(b) "
            "RETURN p ORDER BY b.designation"
        )
        for row in result.rows:
            path = row["p"]
            assert isinstance(path, Path)
            assert len(path.nodes) == len(path.relationships) + 1
            assert path.nodes[0]["designation"] == "Kevin Flynn"

    def test_size_counts_the_relationship_list(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[r:ALLIES_WITH*1..2]->(b) "
            "RETURN DISTINCT size(r) AS length ORDER BY length"
        )
        assert self.values(result) == [(1,), (2,)]

    def test_zero_hop_relationship_list_is_empty(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[r:ALLIES_WITH*0..0]->(b) "
            "RETURN size(r) AS hops"
        )
        assert self.values(result) == [(0,)]

    def test_zero_hop_path_has_one_node(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH p = (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*0..0]->(b) RETURN p"
        )
        path = result.rows[0]["p"]
        assert isinstance(path, Path)
        assert len(path.nodes) == 1
        assert path.relationships == ()

    def test_cartesian_with_a_quantified_pattern(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*1..1]->(b), "
            "(c:ISO) RETURN count(*) AS total"
        )
        assert self.values(result) == [(3,)]


class TestEngineParity(_PatternGraph):
    """Verify the SQL and pattern-engine paths agree on fixed patterns."""

    def test_fixed_pattern_matches_through_both_paths(self, graph: Graph) -> None:
        sql = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH]->(b), "
            "(b)-[:ALLIES_WITH]->(c) "
            "RETURN b.designation AS b, c.designation AS c ORDER BY b.designation"
        )
        engine = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*1..1]->(b), "
            "(b)-[:ALLIES_WITH]->(c) "
            "RETURN b.designation AS b, c.designation AS c ORDER BY b.designation"
        )
        assert self.values(sql) == self.values(engine)

    def test_explain_reports_the_start_node_index(self, graph: Graph) -> None:
        graph.create_node_index("designation")
        plan = graph.explain(
            "MATCH (a:Program {designation: 'Quorra'})-[:ALLIES_WITH*1..2]->(b) RETURN b"
        )
        assert any("pygrafito_idx_node_" in line for line in plan)
        assert any("QUANTIFIED PATTERN" in line for line in plan)
