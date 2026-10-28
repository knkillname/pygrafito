# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for shortest-path evaluation."""

import typing
from collections.abc import Iterator

import pytest

from pygrafito import Graph
from pygrafito.model import (
    Direction,
    Node,
    NotFoundError,
    ValidationError,
)


class _GraphTestCase:
    """Provide an in-memory graph for shortest-path tests."""

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
        nodes = {name: graph.add_node(name) for name in ("Grid", "Safehouse", "Outlands", "Portal")}
        graph.add_relationship(nodes["Grid"], "GRID_LINK", nodes["Safehouse"])
        graph.add_relationship(nodes["Grid"], "GRID_LINK", nodes["Outlands"])
        graph.add_relationship(nodes["Safehouse"], "GRID_LINK", nodes["Portal"])
        graph.add_relationship(nodes["Outlands"], "GRID_LINK", nodes["Portal"])
        return nodes


class TestShortestRoute(_GraphTestCase):
    """Verify shortest path selection."""

    def test_diamond_route_has_two_relationships(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        path = graph.shortest_path(nodes["Grid"], nodes["Portal"])
        assert path is not None
        assert path.length == 2
        assert path.start == nodes["Grid"]
        assert path.end == nodes["Portal"]
        assert path.nodes[0].id == nodes["Grid"].id
        assert path.nodes[-1].id == nodes["Portal"].id

    def test_direct_route_beats_longer_route(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        third = graph.add_node()
        graph.add_relationship(first, "GRID_LINK", second)
        graph.add_relationship(second, "GRID_LINK", third)
        graph.add_relationship(first, "PORTAL_LINK", third)
        path = graph.shortest_path(first, third)
        assert path is not None
        assert path.length == 1
        assert path.nodes == (first, third)

    def test_parallel_relationships_produce_one_hop(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        graph.add_relationship(first, "ALLIES_WITH", second)
        graph.add_relationship(first, "ALLIES_WITH", second)
        path = graph.shortest_path(first, second)
        assert path is not None
        assert path.length == 1
        assert len(path.relationships) == 1

    def test_self_loop_does_not_shorten_same_node(self, graph: Graph) -> None:
        node = graph.add_node()
        graph.add_relationship(node, "RECURSES", node)
        path = graph.shortest_path(node, node)
        assert path is not None
        assert path.length == 0
        assert path.nodes == (node,)


class TestNoPath(_GraphTestCase):
    """Verify unreachable and bounded results."""

    def test_unreachable_returns_none(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        assert graph.shortest_path(first, second) is None

    def test_reverse_direction_is_not_followed(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        graph.add_relationship(first, "GRID_LINK", second)
        assert graph.shortest_path(second, first) is None

    def test_max_depth_too_small_returns_none(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        assert graph.shortest_path(nodes["Grid"], nodes["Portal"], max_depth=1) is None

    def test_max_depth_allows_exact_path(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        path = graph.shortest_path(nodes["Grid"], nodes["Portal"], max_depth=2)
        assert path is not None
        assert path.length == 2

    def test_zero_max_depth_returns_none(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        assert graph.shortest_path(nodes["Grid"], nodes["Portal"], max_depth=0) is None


class TestSameNode(_GraphTestCase):
    """Verify zero-length paths."""

    def test_same_node_zero_length(self, graph: Graph) -> None:
        node = graph.add_node("Program")
        path = graph.shortest_path(node, node)
        assert path is not None
        assert path.length == 0
        assert path.start == node
        assert path.end == node
        assert path.nodes == (node,)
        assert path.relationships == ()


class TestIncomingAndBoth(_GraphTestCase):
    """Verify path shape when following relationships backwards."""

    def test_incoming_path_is_ordered_from_start_to_end(
        self,
        graph: Graph,
    ) -> None:
        first = graph.add_node()
        second = graph.add_node()
        third = graph.add_node()
        first_to_second = graph.add_relationship(first, "GRID_LINK", second)
        second_to_third = graph.add_relationship(second, "GRID_LINK", third)
        path = graph.shortest_path(
            third,
            first,
            direction=Direction.INCOMING,
        )
        assert path is not None
        assert path.nodes == (third, second, first)
        assert path.relationships == (second_to_third, first_to_second)
        assert path.start == third
        assert path.end == first

    def test_both_direction(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        graph.add_relationship(first, "GRID_LINK", second)
        path = graph.shortest_path(second, first, direction=Direction.BOTH)
        assert path is not None
        assert path.nodes == (second, first)

    def test_incoming_from_wrong_end_returns_none(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        graph.add_relationship(first, "GRID_LINK", second)
        assert graph.shortest_path(first, second, direction=Direction.INCOMING) is None


class TestTypeFilter(_GraphTestCase):
    """Verify relationship type restrictions."""

    def test_label_filter_selects_longer_route(self, graph: Graph) -> None:
        start = graph.add_node()
        middle = graph.add_node()
        end = graph.add_node()
        graph.add_relationship(start, "TRUSTS", end)
        graph.add_relationship(start, "ALLIES_WITH", middle)
        graph.add_relationship(middle, "ALLIES_WITH", end)
        path = graph.shortest_path(start, end, labels=["ALLIES_WITH"])
        assert path is not None
        assert path.nodes == (start, middle, end)

    def test_empty_label_set_means_all_labels(self, graph: Graph) -> None:
        start = graph.add_node()
        end = graph.add_node()
        graph.add_relationship(start, "TRUSTS", end)
        path = graph.shortest_path(start, end, labels=[])
        assert path is not None
        assert path.length == 1


class TestValidation(_GraphTestCase):
    """Verify shortest-path input validation."""

    def test_missing_start_rejected(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(NotFoundError):
            graph.shortest_path(999, node)

    def test_missing_end_rejected(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(NotFoundError):
            graph.shortest_path(node, 999)

    def test_negative_max_depth_rejected(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(ValidationError):
            graph.shortest_path(node, node, max_depth=-1)

    def test_invalid_direction_rejected(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(ValidationError):
            graph.shortest_path(
                node,
                node,
                direction=typing.cast(Direction, "incoming"),
            )

    def test_invalid_label_filter_rejected(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(ValidationError):
            graph.shortest_path(node, node, labels=[""])

    def test_integer_endpoints_accepted(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        graph.add_relationship(first, "GRID_LINK", second)
        path = graph.shortest_path(first.id, second.id)
        assert path is not None
        assert path.length == 1
