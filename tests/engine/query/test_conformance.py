# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Table-driven conformance suite for the dialect."""

import dataclasses
from collections.abc import Iterator
from typing import ClassVar

import pytest

from pygrafito import Graph
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import Path


@dataclasses.dataclass(frozen=True, slots=True)
class Case:
    """One conformance query and its expected rows."""

    query: str
    expected: tuple[tuple[QueryValue, ...], ...]
    parameters: dict[str, QueryValue] = dataclasses.field(default_factory=dict)


class TestConformance:
    """Execute representative queries against a fixed TRON graph."""

    CASES: ClassVar[tuple[Case, ...]] = (
        Case(
            "MATCH (n:Program:ISO {designation: 'Quorra'}) RETURN n.designation",
            (("Quorra",),),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'})-[r:ALLIES_WITH]->(b) "
            "RETURN type(r) AS kind, b.designation AS name ORDER BY name",
            (("ALLIES_WITH", "Quorra"), ("ALLIES_WITH", "Quorra")),
        ),
        Case(
            "MATCH (a {designation: 'Clu'})<-[r:ALLIES_WITH]-(b) "
            "RETURN b.designation ORDER BY b.designation",
            (("Quorra",), ("Tron",)),
        ),
        Case(
            "MATCH (a)-[r:OBSERVES]-(b) RETURN a.designation AS name ORDER BY name",
            (("Clu",), ("Rinzler",)),
        ),
        Case(
            "MATCH (n:Program) WHERE n.cycles >= 37 AND n.cycles < 40 "
            "RETURN n.designation ORDER BY n.designation",
            (("Quorra",),),
        ),
        Case(
            "MATCH (n:Program) WHERE n.designation IN ['Quorra', 'Tron'] "
            "RETURN n.designation ORDER BY n.designation",
            (("Quorra",), ("Tron",)),
        ),
        Case(
            "MATCH (n:Program) WHERE n.designation STARTS WITH 'Tr' RETURN n.designation",
            (("Tron",),),
        ),
        Case(
            "MATCH (n:Program) WHERE n.cycles IS NULL RETURN n.designation ORDER BY n.designation",
            (("Clu",), ("Sam Flynn",)),
        ),
        Case(
            "MATCH (n:Program) WHERE n.cycles IS NOT NULL RETURN count(*) AS total",
            ((4,),),
        ),
        Case(
            "MATCH (n:Program {designation: 'Quorra'}) "
            "RETURN n.designation AS name, n.cycles + 1 AS next",
            (("Quorra", 38),),
        ),
        Case(
            "MATCH (n) RETURN DISTINCT labels(n) AS labels ORDER BY labels",
            (
                (["ISO", "Program"],),
                (["Program"],),
                (["System"],),
            ),
        ),
        Case(
            "MATCH (n:Program) RETURN count(*) AS rows, count(n.cycles) AS cycles, "
            "sum(n.cycles) AS total, avg(n.cycles) AS average, "
            "min(n.cycles) AS low, max(n.cycles) AS high",
            ((6, 4, 149.0, 37.25, 36, 40.0),),
        ),
        Case(
            "MATCH (n:Program) RETURN count(DISTINCT n.cycles) AS cycles",
            ((3,),),
        ),
        Case(
            "MATCH (n:Missing) RETURN count(*) AS rows, collect(n.designation) AS names, "
            "sum(n.cycles) AS total, avg(n.cycles) AS average, "
            "min(n.cycles) AS low, max(n.cycles) AS high",
            ((0, [], 0, None, None, None),),
        ),
        Case(
            "MATCH (n) RETURN labels(n) AS labels, count(*) AS total ORDER BY labels",
            (
                (["ISO", "Program"], 1),
                (["Program"], 5),
                (["System"], 1),
            ),
        ),
        Case(
            "MATCH (n:Program) RETURN n.designation ORDER BY n.cycles ASC, n.designation ASC",
            (
                ("Kevin Flynn",),
                ("Rinzler",),
                ("Quorra",),
                ("Tron",),
                ("Clu",),
                ("Sam Flynn",),
            ),
        ),
        Case(
            "MATCH (n:Program) RETURN n.designation ORDER BY n.cycles DESC, n.designation ASC",
            (
                ("Clu",),
                ("Sam Flynn",),
                ("Tron",),
                ("Quorra",),
                ("Kevin Flynn",),
                ("Rinzler",),
            ),
        ),
        Case(
            "MATCH (n:Program) RETURN n.designation ORDER BY n.designation SKIP 2 LIMIT 2",
            (("Quorra",), ("Rinzler",)),
        ),
        Case(
            "MATCH (n:Program) WHERE n.cycles > $minimum "
            "RETURN n.designation ORDER BY n.designation",
            (("Quorra",), ("Tron",)),
            {"minimum": 36},
        ),
        Case(
            "MATCH (n:Program {designation: 'Quorra'}) "
            "RETURN labels(n) AS labels, toInteger('36') AS converted",
            ((["ISO", "Program"], 36),),
        ),
        Case(
            "MATCH (n:Program) WHERE NOT n.cycles = 36 OR n.designation = 'Clu' "
            "RETURN n.designation ORDER BY n.designation",
            (("Clu",), ("Quorra",), ("Tron",)),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH]->(b), "
            "(b)-[:ALLIES_WITH]->(c) RETURN c.designation",
            (("Clu",), ("Clu",)),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'})-[:TRUSTS]->(b), "
            "(b)-[:ALLIES_WITH]->(c) RETURN b.designation, c.designation",
            (("Tron", "Clu"),),
        ),
        Case(
            "MATCH (a:System), (b:Program) RETURN count(*) AS total",
            ((6,),),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'}) MATCH (a)-[:TRUSTS]->(b) RETURN b.designation",
            (("Tron",),),
        ),
        Case(
            "MATCH (a {designation: 'Sam Flynn'}) MATCH (a)-[:TRUSTS]->(b) "
            "RETURN count(*) AS total",
            ((0,),),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'}) "
            "OPTIONAL MATCH (a)-[:ALLIES_WITH]->(b) RETURN count(*) AS total",
            ((2,),),
        ),
        Case(
            "MATCH (a {designation: 'Sam Flynn'}) "
            "OPTIONAL MATCH (a)-[:TRUSTS]->(b) RETURN b.designation",
            ((None,),),
        ),
        Case(
            "MATCH (a {designation: 'Sam Flynn'}) "
            "OPTIONAL MATCH (a)-[:TRUSTS]->(b) "
            "RETURN a.designation, b.designation",
            (("Sam Flynn", None),),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'}) "
            "OPTIONAL MATCH (a)-[:ALLIES_WITH]->(b) WHERE b.cycles > 40 "
            "RETURN b.designation",
            ((None,),),
        ),
        Case(
            "MATCH (a {designation: 'Sam Flynn'}) OPTIONAL MATCH (a)-[:TRUSTS]->(b) "
            "MATCH (a) WHERE b.designation = 'Tron' RETURN b",
            (),
        ),
        Case(
            "OPTIONAL MATCH (n:Missing) RETURN n.designation",
            ((None,),),
        ),
        Case(
            "MATCH (a)-[:ALLIES_WITH]->(b) WITH a, count(*) AS friends "
            "WHERE friends > 1 RETURN a.designation",
            (("Kevin Flynn",),),
        ),
        Case(
            "MATCH (a)-[:ALLIES_WITH]->(b) WITH a.designation AS name, count(*) AS friends "
            "ORDER BY friends DESC, name LIMIT 1 RETURN name, friends",
            (("Kevin Flynn", 2),),
        ),
        Case(
            "MATCH (a)-[:ALLIES_WITH]->(b) WITH a.designation AS name, count(*) AS friends "
            "ORDER BY name SKIP 1 LIMIT 2 RETURN name",
            (("Quorra",), ("Tron",)),
        ),
        Case(
            "MATCH (n:Program) WITH n.cycles AS cycles, count(*) AS total "
            "RETURN cycles, total ORDER BY total, cycles",
            ((37, 1), (40, 1), (36, 2), (None, 2)),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*2]->(b) RETURN count(*) AS total",
            ((2,),),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*1..2]->(b) "
            "RETURN count(*) AS total",
            ((4,),),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*0..1]->(b) "
            "RETURN count(*) AS total",
            ((3,),),
        ),
        Case(
            "MATCH (a {designation: 'Kevin Flynn'})-[r:ALLIES_WITH*2..2]->(b) "
            "RETURN DISTINCT size(r) AS length",
            ((2,),),
        ),
        Case(
            "MATCH (a {designation: 'Clu'})<-[r:ALLIES_WITH*1..2]-(b) "
            "RETURN b.designation ORDER BY b.designation",
            (("Kevin Flynn",), ("Kevin Flynn",), ("Quorra",), ("Tron",)),
        ),
    )

    @pytest.fixture
    def graph(self) -> Iterator[Graph]:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node("Program", "ISO", designation="Quorra", cycles=37)
            tron = graph.add_node("Program", designation="Tron", cycles=40)
            clu = graph.add_node("Program", designation="Clu")
            rinzler = graph.add_node("Program", designation="Rinzler", cycles=36.0)
            graph.add_node("Program", designation="Sam Flynn")
            graph.add_node("System", designation="The Grid")
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            graph.add_relationship(kevin, "TRUSTS", tron)
            graph.add_relationship(quorra, "ALLIES_WITH", clu)
            graph.add_relationship(tron, "ALLIES_WITH", clu)
            graph.add_relationship(clu, "OBSERVES", clu)
            graph.add_relationship(rinzler, "OBSERVES", rinzler)
            graph.add_relationship(clu, "TRUSTS", kevin)
            yield graph

    @pytest.mark.parametrize("case", CASES, ids=lambda case: case.query[:40])
    def test_conformance(self, graph: Graph, case: Case) -> None:
        result = graph.query(case.query, case.parameters)
        assert tuple(tuple(row.values()) for row in result) == case.expected

    def test_write_conformance(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Kevin Flynn'}) "
            "SET n.cycles = 37 RETURN n.cycles AS cycles"
        )
        assert tuple(tuple(row.values()) for row in result) == ((37,),)
        assert result.summary.properties_set == 1

    def test_write_deduplication_conformance(self, graph: Graph) -> None:
        result = graph.query("MATCH (a)-[:ALLIES_WITH]->(b {designation: 'Clu'}) SET b.cycles = 1")
        assert result.summary.properties_set == 1
        clu = next(iter(graph.find_nodes("Program", designation="Clu")))
        assert clu["cycles"] == 1

    def test_create_conformance(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Kevin Flynn'}) "
            "CREATE (m:ISO {designation: 'Quorra'}) RETURN m.designation AS name"
        )
        assert tuple(tuple(row.values()) for row in result) == (("Quorra",),)
        assert result.summary.created_nodes == 1

    def test_path_conformance(self, graph: Graph) -> None:
        result = graph.query("MATCH p = (a {designation: 'Kevin Flynn'})-[:TRUSTS]->(b) RETURN p")
        path = result.rows[0]["p"]
        assert isinstance(path, Path)
        assert [node["designation"] for node in path.nodes] == ["Kevin Flynn", "Tron"]
        assert [relationship.rel_type for relationship in path.relationships] == ["TRUSTS"]

    def test_quantified_path_conformance(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH p = (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH*2..2]->(b) RETURN p"
        )
        for row in result.rows:
            path = row["p"]
            assert isinstance(path, Path)
            assert len(path.nodes) == 3
            assert len(path.relationships) == 2
            assert path.nodes[0]["designation"] == "Kevin Flynn"
            assert path.nodes[-1]["designation"] == "Clu"

    def test_injection_conformance(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Quorra' OR 1=1 --")
        result = graph.query(
            "MATCH (n:Program) WHERE n.designation = $name RETURN n.designation",
            {"name": "Quorra' OR 1=1 --"},
        )
        assert tuple(tuple(row.values()) for row in result) == (("Quorra' OR 1=1 --",),)
