# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Tests for relationship-unique path enumeration."""

import itertools
from collections.abc import Iterable, Iterator

import pytest

from pygrafito import Graph
from pygrafito.engine.traversal import AdjacencySnapshot, TrailEnumerator
from pygrafito.model import (
    Direction,
    Node,
    Relationship,
    ValidationError,
)


class _GraphTestCase:
    """Provide an in-memory graph for path tests."""

    @pytest.fixture
    def graph(self) -> Iterator[Graph]:
        """Open an in-memory graph for one test.

        Yields
        ------
        Graph
            Graph under test.
        """
        with Graph.open(":memory:") as graph:
            yield graph

    @staticmethod
    def build_diamond(graph: Graph) -> dict[str, Node]:
        """Build a diamond with two two-hop routes.

        Parameters
        ----------
        graph : Graph
            Graph to populate.

        Returns
        -------
        dict[str, Node]
            Nodes keyed by name.
        """
        nodes = {
            name: graph.add_node("Node", name=name) for name in ("start", "left", "right", "end")
        }
        graph.add_relationship(nodes["start"], "ROUTE", nodes["left"])
        graph.add_relationship(nodes["start"], "ROUTE", nodes["right"])
        graph.add_relationship(nodes["left"], "ROUTE", nodes["end"])
        graph.add_relationship(nodes["right"], "ROUTE", nodes["end"])
        return nodes


class TestTwoRoutes(_GraphTestCase):
    """Verify that distinct routes produce distinct paths."""

    def test_two_route_diamond(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        paths = list(graph.paths(nodes["start"], nodes["end"], max_depth=2))
        assert len(paths) == 2
        assert {paths[0].nodes[1]["name"], paths[1].nodes[1]["name"]} == {
            "left",
            "right",
        }
        assert all(path.length == 2 for path in paths)
        assert all(path.start == nodes["start"] for path in paths)
        assert all(path.end == nodes["end"] for path in paths)

    def test_depth_range_excludes_shortcut(self, graph: Graph) -> None:
        start = graph.add_node("start")
        middle = graph.add_node("middle")
        end = graph.add_node("end")
        graph.add_relationship(start, "NEXT", end)
        graph.add_relationship(start, "NEXT", middle)
        graph.add_relationship(middle, "NEXT", end)
        paths = list(graph.paths(start, end, min_depth=2, max_depth=2))
        assert len(paths) == 1
        assert paths[0].nodes == (start, middle, end)

    def test_depth_range_includes_both_lengths(self, graph: Graph) -> None:
        start = graph.add_node()
        middle = graph.add_node()
        end = graph.add_node()
        graph.add_relationship(start, "NEXT", end)
        graph.add_relationship(start, "NEXT", middle)
        graph.add_relationship(middle, "NEXT", end)
        paths = list(graph.paths(start, end, min_depth=1, max_depth=2))
        assert sorted(path.length for path in paths) == [1, 2]


class TestTrailSemantics(_GraphTestCase):
    """Verify node repetition and relationship uniqueness."""

    def test_node_may_repeat(self, graph: Graph) -> None:
        first = graph.add_node("A")
        second = graph.add_node("B")
        third = graph.add_node("C")
        graph.add_relationship(first, "NEXT", second)
        graph.add_relationship(second, "NEXT", third)
        graph.add_relationship(third, "NEXT", first)
        paths = list(
            graph.paths(first, first, min_depth=3, max_depth=3),
        )
        assert len(paths) == 1
        assert paths[0].nodes == (first, second, third, first)
        assert paths[0].length == 3

    def test_relationship_may_not_repeat(self, graph: Graph) -> None:
        node = graph.add_node()
        graph.add_relationship(node, "SELF", node)
        assert list(graph.paths(node, node, min_depth=2, max_depth=3)) == []

    def test_two_relationships_can_form_a_cycle(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        graph.add_relationship(first, "NEXT", second)
        graph.add_relationship(second, "NEXT", first)
        paths = list(graph.paths(first, first, min_depth=2, max_depth=2))
        assert len(paths) == 1
        assert paths[0].nodes == (first, second, first)
        assert [relationship.rel_type for relationship in paths[0].relationships] == [
            "NEXT",
            "NEXT",
        ]

    def test_self_loop_path(self, graph: Graph) -> None:
        node = graph.add_node()
        graph.add_relationship(node, "SELF", node)
        paths = list(graph.paths(node, node, min_depth=1, max_depth=1))
        assert len(paths) == 1
        assert paths[0].length == 1
        assert paths[0].nodes == (node, node)

    def test_zero_length_path_when_allowed(self, graph: Graph) -> None:
        node = graph.add_node()
        paths = list(graph.paths(node, node, min_depth=0, max_depth=0))
        assert len(paths) == 1
        assert paths[0].length == 0


class TestParallelRelationships(_GraphTestCase):
    """Verify that parallel relationships are distinct trails."""

    def test_parallel_relationships_produce_distinct_paths(
        self,
        graph: Graph,
    ) -> None:
        first = graph.add_node()
        second = graph.add_node()
        first_relationship = graph.add_relationship(first, "KNOWS", second)
        second_relationship = graph.add_relationship(first, "KNOWS", second)
        paths = list(graph.paths(first, second, max_depth=1))
        assert len(paths) == 2
        assert {path.relationships[0].id for path in paths} == {
            first_relationship.id,
            second_relationship.id,
        }
        assert all(path.nodes == (first, second) for path in paths)


class TestLimits(_GraphTestCase):
    """Verify lazy generation and result limits."""

    def test_limit_caps_results(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        paths = list(graph.paths(nodes["start"], nodes["end"], max_depth=2, limit=1))
        assert len(paths) == 1

    def test_zero_limit_yields_nothing(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        assert list(graph.paths(nodes["start"], nodes["end"], max_depth=2, limit=0)) == []

    def test_negative_limit_rejected(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        with pytest.raises(ValidationError):
            graph.paths(nodes["start"], nodes["end"], max_depth=2, limit=-1)

    def test_is_lazy_and_stops_early(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        iterator = graph.paths(nodes["start"], nodes["end"], max_depth=2)
        first = next(iterator)
        assert first.length == 2
        remaining = list(graph.paths(nodes["start"], nodes["end"], max_depth=2))
        assert len(remaining) == 2

    def test_max_depth_is_required(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        with pytest.raises(TypeError):
            graph.paths(nodes["start"], nodes["end"])  # type: ignore[call-arg]


class _CountingSnapshot(AdjacencySnapshot):
    """Count adjacency calls to observe lazy generation."""

    def __init__(
        self,
        nodes: Iterable[Node],
        relationships: Iterable[Relationship],
    ) -> None:
        super().__init__(nodes, relationships)
        self.edge_calls = 0

    def edges(
        self,
        node_id: int,
        direction: Direction,
        rel_types: frozenset[str] | None,
    ) -> Iterator[tuple[Relationship, int]]:
        self.edge_calls += 1
        yield from super().edges(node_id, direction, rel_types)


class TestEarlyStop(_GraphTestCase):
    """Verify that stopping iteration prevents further path computation."""

    def test_consuming_one_path_does_not_compute_the_next(self) -> None:
        start = Node(id=1, labels=frozenset({"start"}))
        left = Node(id=2)
        right = Node(id=3)
        end = Node(id=4)
        relationships = (
            Relationship(id=1, rel_type="ROUTE", start_id=1, end_id=2),
            Relationship(id=2, rel_type="ROUTE", start_id=1, end_id=3),
            Relationship(id=3, rel_type="ROUTE", start_id=2, end_id=4),
            Relationship(id=4, rel_type="ROUTE", start_id=3, end_id=4),
        )
        snapshot = _CountingSnapshot((start, left, right, end), relationships)
        full_snapshot = _CountingSnapshot((start, left, right, end), relationships)
        full_count = len(list(TrailEnumerator(full_snapshot, start, end, 1, 2)))
        assert full_count == 2
        enumerator = TrailEnumerator(snapshot, start, end, 1, 2)
        iterator = iter(enumerator)
        paths = list(itertools.islice(iterator, 1))
        assert len(paths) == 1
        calls_after_first = snapshot.edge_calls
        assert calls_after_first < full_snapshot.edge_calls
