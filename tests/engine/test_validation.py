# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Tests for traversal validation and snapshot consistency."""

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
    """Provide an in-memory graph for validation tests."""

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
    def build_chain(graph: Graph) -> dict[str, Node]:
        """Build a three-node directed chain.

        Parameters
        ----------
        graph : Graph
            Graph to populate.

        Returns
        -------
        dict[str, Node]
            Nodes keyed by name.
        """
        nodes = {name: graph.add_node(name) for name in ("start", "middle", "end")}
        graph.add_relationship(nodes["start"], "NEXT", nodes["middle"])
        graph.add_relationship(nodes["middle"], "NEXT", nodes["end"])
        return nodes


class TestDepthValidation(_GraphTestCase):
    """Verify depth and range validation."""

    def test_traverse_negative_depth(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(ValidationError):
            graph.traverse(node, max_depth=-1)

    def test_shortest_path_negative_depth(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(ValidationError):
            graph.shortest_path(node, node, max_depth=-1)

    def test_paths_negative_min_depth(self, graph: Graph) -> None:
        nodes = self.build_chain(graph)
        with pytest.raises(ValidationError):
            graph.paths(nodes["start"], nodes["end"], min_depth=-1, max_depth=2)

    def test_paths_negative_max_depth(self, graph: Graph) -> None:
        nodes = self.build_chain(graph)
        with pytest.raises(ValidationError):
            graph.paths(nodes["start"], nodes["end"], max_depth=-1)

    def test_paths_inverted_depth_range(self, graph: Graph) -> None:
        nodes = self.build_chain(graph)
        with pytest.raises(ValidationError):
            graph.paths(nodes["start"], nodes["end"], min_depth=3, max_depth=2)

    def test_paths_invalid_direction(self, graph: Graph) -> None:
        nodes = self.build_chain(graph)
        with pytest.raises(ValidationError):
            graph.paths(
                nodes["start"],
                nodes["end"],
                max_depth=2,
                direction=typing.cast(Direction, "both"),
            )

    def test_paths_invalid_type_filter(self, graph: Graph) -> None:
        nodes = self.build_chain(graph)
        with pytest.raises(ValidationError):
            graph.paths(nodes["start"], nodes["end"], max_depth=2, types=[""])

    def test_paths_non_integer_depth(self, graph: Graph) -> None:
        nodes = self.build_chain(graph)
        with pytest.raises(ValidationError):
            graph.paths(
                nodes["start"],
                nodes["end"],
                max_depth=typing.cast(int, "2"),
            )

    def test_paths_non_string_type(self, graph: Graph) -> None:
        nodes = self.build_chain(graph)
        with pytest.raises(ValidationError):
            graph.paths(
                nodes["start"],
                nodes["end"],
                max_depth=2,
                types=[typing.cast(str, 1)],
            )


class TestMissingNodes(_GraphTestCase):
    """Verify missing-node errors across traversal operations."""

    def test_traverse_missing_start(self, graph: Graph) -> None:
        with pytest.raises(NotFoundError):
            graph.traverse(999, max_depth=1)

    def test_shortest_path_missing_start(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(NotFoundError):
            graph.shortest_path(999, node)

    def test_shortest_path_missing_end(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(NotFoundError):
            graph.shortest_path(node, 999)

    def test_paths_missing_start(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(NotFoundError):
            graph.paths(999, node, max_depth=1)

    def test_paths_missing_end(self, graph: Graph) -> None:
        node = graph.add_node()
        with pytest.raises(NotFoundError):
            graph.paths(node, 999, max_depth=1)


class TestTraversalSnapshot(_GraphTestCase):
    """Verify that writes after traversal starts do not alter results."""

    def test_traverse_ignores_new_relationship(self, graph: Graph) -> None:
        start = graph.add_node("start")
        middle = graph.add_node("middle")
        graph.add_relationship(start, "NEXT", middle)
        iterator = graph.traverse(start, max_depth=5)
        first = next(iterator)
        assert first.node == middle
        later = graph.add_node("later")
        graph.add_relationship(middle, "NEXT", later)
        remaining = list(iterator)
        assert later.id not in {step.node.id for step in remaining}
        assert remaining == []

    def test_traverse_ignores_deleted_node(self, graph: Graph) -> None:
        start = graph.add_node("start")
        target = graph.add_node("target")
        graph.add_relationship(start, "NEXT", target)
        iterator = graph.traverse(start, max_depth=2)
        graph.delete(target, detach=True)
        steps = list(iterator)
        assert [step.node.id for step in steps] == [target.id]

    def test_traverse_ignores_new_labels_and_properties(
        self,
        graph: Graph,
    ) -> None:
        start = graph.add_node("start")
        target = graph.add_node("target", name="before")
        graph.add_relationship(start, "NEXT", target)
        iterator = graph.traverse(start, max_depth=2)
        graph.set_properties(target, name="after")
        graph.add_labels(target, "Changed")
        step = next(iterator)
        assert step.node["name"] == "before"
        assert step.node.labels == frozenset({"target"})

    def test_paths_ignore_new_route(self, graph: Graph) -> None:
        start = graph.add_node("start")
        end = graph.add_node("end")
        graph.add_relationship(start, "NEXT", end)
        iterator = graph.paths(start, end, max_depth=3)
        middle = graph.add_node("middle")
        graph.add_relationship(start, "NEXT", middle)
        graph.add_relationship(middle, "NEXT", end)
        paths = list(iterator)
        assert len(paths) == 1
        assert paths[0].nodes == (start, end)

    def test_paths_ignore_deleted_relationship(self, graph: Graph) -> None:
        start = graph.add_node("start")
        middle = graph.add_node("middle")
        end = graph.add_node("end")
        graph.add_relationship(start, "NEXT", middle)
        relationship = graph.add_relationship(middle, "NEXT", end)
        iterator = graph.paths(start, end, max_depth=3)
        graph.delete(relationship)
        paths = list(iterator)
        assert len(paths) == 1
        assert paths[0].nodes == (start, middle, end)

    def test_new_relationships_are_visible_to_later_traversals(
        self,
        graph: Graph,
    ) -> None:
        start = graph.add_node()
        middle = graph.add_node()
        later = graph.add_node()
        graph.add_relationship(start, "NEXT", middle)
        first_steps = list(graph.traverse(start, max_depth=5))
        graph.add_relationship(middle, "NEXT", later)
        second_steps = list(graph.traverse(start, max_depth=5))
        assert later.id not in {step.node.id for step in first_steps}
        assert later.id in {step.node.id for step in second_steps}
