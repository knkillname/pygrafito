# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for distinct reachable-node traversal."""

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
    """Provide an in-memory graph for traversal tests."""

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


class TestDiamond(_GraphTestCase):
    """Verify diamond-shaped reachability."""

    def test_end_is_yielded_once_with_shortest_depth(
        self,
        graph: Graph,
    ) -> None:
        nodes = self.build_diamond(graph)
        steps = list(graph.traverse(nodes["Grid"], max_depth=2))
        by_id = {step.node.id: step.depth for step in steps}
        assert by_id == {
            nodes["Safehouse"].id: 1,
            nodes["Outlands"].id: 1,
            nodes["Portal"].id: 2,
        }
        assert [step.node.id for step in steps].count(nodes["Portal"].id) == 1

    def test_breadth_first_sequence_and_depths(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        names = {node.id: name for name, node in nodes.items()}
        steps = list(graph.traverse(nodes["Grid"], max_depth=2))
        assert [(names[step.node.id], step.depth) for step in steps] == [
            ("Safehouse", 1),
            ("Outlands", 1),
            ("Portal", 2),
        ]

    def test_depth_bound_excludes_far_nodes(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        steps = list(graph.traverse(nodes["Grid"], max_depth=1))
        assert {step.node.id for step in steps} == {
            nodes["Safehouse"].id,
            nodes["Outlands"].id,
        }

    def test_zero_depth_yields_nothing(self, graph: Graph) -> None:
        nodes = self.build_diamond(graph)
        assert list(graph.traverse(nodes["Grid"], max_depth=0)) == []


class TestCycle(_GraphTestCase):
    """Verify that cycles do not duplicate nodes."""

    def test_cycle_yields_each_node_once(self, graph: Graph) -> None:
        first = graph.add_node("Tron")
        second = graph.add_node("Clu")
        third = graph.add_node("Rinzler")
        graph.add_relationship(first, "GRID_LINK", second)
        graph.add_relationship(second, "GRID_LINK", third)
        graph.add_relationship(third, "GRID_LINK", first)
        graph.add_relationship(third, "GRID_LINK", second)
        steps = list(graph.traverse(first, max_depth=10))
        assert {step.node.id for step in steps} == {second.id, third.id}
        assert [step.node.id for step in steps] == [second.id, third.id]
        assert [step.depth for step in steps] == [1, 2]

    def test_self_loop_does_not_yield_start(self, graph: Graph) -> None:
        node = graph.add_node()
        graph.add_relationship(node, "RECURSES", node)
        assert list(graph.traverse(node, max_depth=5)) == []

    def test_parallel_relationships_yield_target_once(
        self,
        graph: Graph,
    ) -> None:
        first = graph.add_node()
        second = graph.add_node()
        graph.add_relationship(first, "ALLIES_WITH", second)
        graph.add_relationship(first, "ALLIES_WITH", second)
        steps = list(graph.traverse(first, max_depth=3))
        assert [step.node.id for step in steps] == [second.id]


class TestDepthChain(_GraphTestCase):
    """Verify depth bounds on a chain."""

    def test_chain_depth_bound(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        third = graph.add_node()
        fourth = graph.add_node()
        graph.add_relationship(first, "GRID_LINK", second)
        graph.add_relationship(second, "GRID_LINK", third)
        graph.add_relationship(third, "GRID_LINK", fourth)
        steps = list(graph.traverse(first, max_depth=2))
        assert {step.node.id for step in steps} == {second.id, third.id}
        assert {step.depth for step in steps} == {1, 2}


class TestDirection(_GraphTestCase):
    """Verify outgoing, incoming, and both directions."""

    def test_directions(self, graph: Graph) -> None:
        first = graph.add_node()
        second = graph.add_node()
        graph.add_relationship(first, "ALLIES_WITH", second)
        outgoing = list(graph.traverse(second, max_depth=2))
        incoming = list(graph.traverse(second, max_depth=2, direction=Direction.INCOMING))
        both = list(graph.traverse(second, max_depth=2, direction=Direction.BOTH))
        assert outgoing == []
        assert [step.node.id for step in incoming] == [first.id]
        assert [step.node.id for step in both] == [first.id]

    def test_invalid_direction_rejected(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(ValidationError):
            graph.traverse(
                node,
                max_depth=2,
                direction=typing.cast(Direction, "outgoing"),
            )


class TestTypeFilter(_GraphTestCase):
    """Verify relationship type filtering."""

    def test_type_filter(self, graph: Graph) -> None:
        start = graph.add_node()
        knows = graph.add_node()
        likes = graph.add_node()
        graph.add_relationship(start, "ALLIES_WITH", knows)
        graph.add_relationship(start, "TRUSTS", likes)
        filtered = list(graph.traverse(start, max_depth=1, types=["ALLIES_WITH"]))
        assert [step.node.id for step in filtered] == [knows.id]

    def test_empty_type_set_means_all_types(self, graph: Graph) -> None:
        start = graph.add_node()
        knows = graph.add_node()
        likes = graph.add_node()
        graph.add_relationship(start, "ALLIES_WITH", knows)
        graph.add_relationship(start, "TRUSTS", likes)
        steps = list(graph.traverse(start, max_depth=1, types=[]))
        assert {step.node.id for step in steps} == {knows.id, likes.id}

    def test_invalid_type_filter_rejected(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(ValidationError):
            graph.traverse(node, max_depth=1, types=[""])


class TestValidation(_GraphTestCase):
    """Verify traversal input validation and start exclusion."""

    def test_start_is_excluded(self, graph: Graph) -> None:
        start = graph.add_node()
        target = graph.add_node()
        graph.add_relationship(start, "GRID_LINK", target)
        steps = list(graph.traverse(start, max_depth=1))
        assert start.id not in {step.node.id for step in steps}

    def test_negative_depth_rejected(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(ValidationError):
            graph.traverse(node, max_depth=-1)

    def test_missing_start_rejected(self, graph: Graph) -> None:
        with pytest.raises(NotFoundError):
            graph.traverse(999, max_depth=1)

    def test_invalid_start_rejected(self, graph: Graph) -> None:
        with pytest.raises(ValidationError):
            graph.traverse(
                typing.cast(Node, "1"),
                max_depth=1,
            )

    def test_integer_start_accepted(self, graph: Graph) -> None:
        start = graph.add_node()
        target = graph.add_node()
        graph.add_relationship(start, "GRID_LINK", target)
        steps = list(graph.traverse(start.id, max_depth=1))
        assert [step.node.id for step in steps] == [target.id]
