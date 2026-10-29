# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests that a declared index never changes query results or ordering."""

import math

import pytest

from pygrafito import Graph


class TestIndexTransparency:
    """Compare statement results with and without a declared index."""

    REGRESSION_VALUES: tuple[float, ...] = (
        2.7710821668887726e-173,
        3.277095539246836e-284,
        1.6287812207021506e-109,
    )

    @staticmethod
    def seed(graph: Graph) -> None:
        """Populate one graph with the shared fixture.

        Parameters
        ----------
        graph : Graph
            Graph to populate.
        """
        kevin = graph.add_node(
            "Program",
            "ISO",
            designation="Kevin Flynn",
            cycles=36,
            active=True,
            tags=["ISO", "Program"],
        )
        quorra = graph.add_node(
            "Program",
            designation="Quorra",
            cycles=37,
            active=1,
            tags=["ISO"],
        )
        tron = graph.add_node(
            "Program",
            designation="Tron",
            cycles=36,
            active=False,
            tags=["Program", "ISO"],
        )
        graph.add_node("Program", designation="Clu")
        graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
        graph.add_relationship(quorra, "ALLIES_WITH", tron, since_cycle=2021)

    def compare(
        self,
        statement: str,
        *,
        node_key: str | None = None,
        relationship_key: str | None = None,
    ) -> None:
        """Run one statement against an indexed and an unindexed graph.

        Parameters
        ----------
        statement : str
            Statement to compare.
        node_key : str | None, optional
            Node property key to index in the indexed graph, by default none.
        relationship_key : str | None, optional
            Relationship property key to index in the indexed graph, by default
            none.
        """
        plain = Graph.open(":memory:")
        indexed = Graph.open(":memory:")
        try:
            for graph in (plain, indexed):
                self.seed(graph)
            if node_key is not None:
                indexed.create_node_index(node_key)
            if relationship_key is not None:
                indexed.create_relationship_index(relationship_key)
            expected = [tuple(row.values()) for row in plain.query(statement)]
            actual = [tuple(row.values()) for row in indexed.query(statement)]
            assert actual == expected
            assert bool(expected)
        finally:
            plain.close()
            indexed.close()

    def test_equality(self) -> None:
        self.compare(
            "MATCH (n:Program) WHERE n.cycles = 36 RETURN n.designation AS name",
            node_key="cycles",
        )

    def test_boolean_and_integer_stay_distinct(self) -> None:
        self.compare(
            "MATCH (n:Program) WHERE n.active = true RETURN n.designation AS name",
            node_key="active",
        )

    def test_list_order_is_significant(self) -> None:
        self.compare(
            "MATCH (n:Program) WHERE n.tags = ['Program', 'ISO'] RETURN n.designation AS name",
            node_key="tags",
        )

    def test_range(self) -> None:
        self.compare(
            "MATCH (n:Program) WHERE n.cycles > 36 RETURN n.designation AS name",
            node_key="cycles",
        )

    def test_relationship_property(self) -> None:
        self.compare(
            "MATCH (a)-[r:ALLIES_WITH]->(b) WHERE r.since_cycle >= 2021 "
            "RETURN b.designation AS name",
            relationship_key="since_cycle",
        )

    def test_ordering_is_stable(self) -> None:
        self.compare(
            "MATCH (n:Program) RETURN n.designation AS name ORDER BY n.cycles",
            node_key="cycles",
        )

    def test_lookup_api_matches(self) -> None:
        plain = Graph.open(":memory:")
        indexed = Graph.open(":memory:")
        try:
            for graph in (plain, indexed):
                self.seed(graph)
            indexed.create_node_index("cycles")
            assert [node.id for node in plain.find_nodes("Program", cycles=36)] == [
                node.id for node in indexed.find_nodes("Program", cycles=36)
            ]
        finally:
            plain.close()
            indexed.close()

    @classmethod
    def seed_real(cls, graph: Graph) -> None:
        """Populate a graph with tiny reals and their neighbors.

        Parameters
        ----------
        graph : Graph
            Graph to populate.
        """
        names = ("Quorra", "Tron", "Yori")
        neighbors = ("Rinzler", "Sark", "Dumont")
        for name, neighbor, value in zip(names, neighbors, cls.REGRESSION_VALUES, strict=True):
            graph.add_node("Program", designation=name, ratio=value)
            graph.add_node(
                "Program",
                designation=neighbor,
                ratio=math.nextafter(value, math.inf),
            )

    def test_real_equality_matches_before_and_after_the_index(self) -> None:
        graph = Graph.open(":memory:")
        try:
            self.seed_real(graph)
            before: dict[str, list[object]] = {}
            after: dict[str, list[object]] = {}
            for value in self.REGRESSION_VALUES:
                before[str(value)] = [
                    node["designation"] for node in graph.find_nodes("Program", ratio=value)
                ]
            graph.create_node_index("ratio")
            for value in self.REGRESSION_VALUES:
                after[str(value)] = [
                    node["designation"] for node in graph.find_nodes("Program", ratio=value)
                ]
            assert before == after
            assert all(len(names) == 1 for names in after.values())
        finally:
            graph.close()

    def test_real_gql_equality_matches_with_and_without_the_index(self) -> None:
        plain = Graph.open(":memory:")
        indexed = Graph.open(":memory:")
        try:
            for graph in (plain, indexed):
                self.seed_real(graph)
            indexed.create_node_index("ratio")
            statement = (
                "MATCH (n:Program) WHERE n.ratio = $value "
                "RETURN n.designation AS name ORDER BY name"
            )
            values = [
                value
                for item in self.REGRESSION_VALUES
                for value in (item, math.nextafter(item, math.inf))
            ]
            for value in values:
                expected = [row["name"] for row in plain.query(statement, {"value": value})]
                actual = [row["name"] for row in indexed.query(statement, {"value": value})]
                assert actual == expected
                assert len(expected) == 1
        finally:
            plain.close()
            indexed.close()

    def test_real_range_matches_with_and_without_the_index(self) -> None:
        plain = Graph.open(":memory:")
        indexed = Graph.open(":memory:")
        try:
            for graph in (plain, indexed):
                self.seed_real(graph)
            indexed.create_node_index("ratio")
            statement = (
                "MATCH (n:Program) WHERE n.ratio > $value "
                "RETURN n.designation AS name ORDER BY name"
            )
            for value in self.REGRESSION_VALUES:
                expected = [row["name"] for row in plain.query(statement, {"value": value})]
                actual = [row["name"] for row in indexed.query(statement, {"value": value})]
                assert actual == expected
                assert expected
        finally:
            plain.close()
            indexed.close()

    @pytest.mark.parametrize("key", ["cycles", "active", "tags", "designation"])
    def test_no_index_changes_row_count(self, key: str) -> None:
        plain = Graph.open(":memory:")
        indexed = Graph.open(":memory:")
        try:
            for graph in (plain, indexed):
                self.seed(graph)
            indexed.create_node_index(key)
            statement = "MATCH (n:Program) RETURN n.designation AS name"
            assert len(plain.query(statement).rows) == len(indexed.query(statement).rows)
        finally:
            plain.close()
            indexed.close()
