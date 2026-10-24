# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for how much a traversal reads."""

from collections.abc import Callable

import pytest

from pygrafito import Graph, Node
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository


class _FailOnRead:
    """Stand-in for a repository read that must never happen."""

    def __call__(self, *arguments: object, **keywords: object) -> None:
        message = "a traversal read the whole graph"
        raise AssertionError(message)


class TestWholeGraphReads:
    """Verify traversal entry points never load the full graph."""

    def test_entry_points_avoid_whole_graph_reads(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn")
            quorra = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            monkeypatch.setattr(NodeRepository, "all", _FailOnRead())
            monkeypatch.setattr(RelationshipRepository, "all", _FailOnRead())

            steps = list(graph.traverse(kevin, max_depth=1))
            assert [step.node.id for step in steps] == [quorra.id]

            path = graph.shortest_path(kevin, quorra)
            assert path is not None
            assert path.length == 1

            assert len(list(graph.paths(kevin, quorra, max_depth=1))) == 1


class _RecordingCall:
    """Wrap a callable and record the arguments of each call.

    Parameters
    ----------
    target : Callable[..., object]
        Callable to invoke.
    recorded : list[tuple[object, ...]]
        Destination for the positional arguments of each call.
    """

    def __init__(
        self,
        target: Callable[..., object],
        recorded: list[tuple[object, ...]],
    ) -> None:
        self._target = target
        self._recorded = recorded

    def __call__(self, *arguments: object, **keywords: object) -> object:
        self._recorded.append(arguments)
        return self._target(*arguments, **keywords)


class TestReadScope:
    """Verify only in-region elements are read."""

    @staticmethod
    def build(graph: Graph) -> dict[str, Node]:
        """Build two components plus an isolated node.

        Parameters
        ----------
        graph : Graph
            Graph to populate.

        Returns
        -------
        dict[str, Node]
            Nodes keyed by name.
        """
        kevin = graph.add_node("Program", designation="Kevin Flynn")
        quorra = graph.add_node("Program", designation="Quorra")
        tron = graph.add_node("Program", designation="Tron")
        clu = graph.add_node("Agent", designation="Clu")
        rinzler = graph.add_node("Agent", designation="Rinzler")
        graph.add_relationship(kevin, "ALLIES_WITH", quorra)
        graph.add_relationship(quorra, "ALLIES_WITH", tron)
        graph.add_relationship(clu, "TRUSTS", clu)
        return {
            "kevin": kevin,
            "quorra": quorra,
            "tron": tron,
            "clu": clu,
            "rinzler": rinzler,
        }

    @staticmethod
    def instrument(
        graph: Graph,
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
        """Record node batch reads and frontier reads.

        Parameters
        ----------
        graph : Graph
            Graph whose repositories are instrumented.
        monkeypatch : pytest.MonkeyPatch
            Fixture used to replace the methods.

        Returns
        -------
        tuple[list[tuple[object, ...]], list[tuple[object, ...]]]
            Recorded node reads and recorded frontier reads.
        """
        node_reads: list[tuple[object, ...]] = []
        frontier_reads: list[tuple[object, ...]] = []
        monkeypatch.setattr(
            graph._nodes,
            "get_many",
            _RecordingCall(graph._nodes.get_many, node_reads),
        )
        monkeypatch.setattr(
            graph._relationships,
            "frontier",
            _RecordingCall(graph._relationships.frontier, frontier_reads),
        )
        return node_reads, frontier_reads

    @staticmethod
    def node_ids(reads: list[tuple[object, ...]]) -> set[int]:
        """Collect every node id requested through batch reads.

        Parameters
        ----------
        reads : list[tuple[object, ...]]
            Recorded calls.

        Returns
        -------
        set[int]
            Requested node identifiers.
        """
        requested: set[int] = set()
        for arguments in reads:
            for node_id in arguments[0]:  # type: ignore[attr-defined]
                requested.add(int(node_id))
        return requested

    @staticmethod
    def frontier_ids(reads: list[tuple[object, ...]]) -> set[int]:
        """Collect every node id used as a frontier.

        Parameters
        ----------
        reads : list[tuple[object, ...]]
            Recorded calls.

        Returns
        -------
        set[int]
            Frontier node identifiers.
        """
        requested: set[int] = set()
        for arguments in reads:
            for node_id in arguments[0]:  # type: ignore[attr-defined]
                requested.add(int(node_id))
        return requested

    def test_traverse_depth_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with Graph.open(":memory:") as graph:
            nodes = self.build(graph)
            node_reads, frontier_reads = self.instrument(graph, monkeypatch)
            list(graph.traverse(nodes["kevin"], max_depth=1))
            assert self.node_ids(node_reads) == {nodes["quorra"].id}
            assert self.frontier_ids(frontier_reads) == {nodes["kevin"].id}

    def test_traverse_depth_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with Graph.open(":memory:") as graph:
            nodes = self.build(graph)
            node_reads, frontier_reads = self.instrument(graph, monkeypatch)
            list(graph.traverse(nodes["kevin"], max_depth=2))
            assert self.node_ids(node_reads) == {
                nodes["quorra"].id,
                nodes["tron"].id,
            }
            assert self.frontier_ids(frontier_reads) == {
                nodes["kevin"].id,
                nodes["quorra"].id,
            }

    def test_paths_reads_only_the_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with Graph.open(":memory:") as graph:
            nodes = self.build(graph)
            node_reads, frontier_reads = self.instrument(graph, monkeypatch)
            list(graph.paths(nodes["kevin"], nodes["tron"], max_depth=2))
            assert self.node_ids(node_reads) == {
                nodes["quorra"].id,
                nodes["tron"].id,
            }
            assert self.frontier_ids(frontier_reads) == {
                nodes["kevin"].id,
                nodes["quorra"].id,
            }

    def test_shortest_path_reads_only_the_search(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with Graph.open(":memory:") as graph:
            nodes = self.build(graph)
            node_reads, frontier_reads = self.instrument(graph, monkeypatch)
            path = graph.shortest_path(nodes["kevin"], nodes["tron"])
            assert path is not None
            assert path.length == 2
            assert nodes["clu"].id not in self.node_ids(node_reads)
            assert nodes["rinzler"].id not in self.node_ids(node_reads)
            touched = self.node_ids(node_reads) | self.frontier_ids(frontier_reads)
            assert touched <= {
                nodes["kevin"].id,
                nodes["quorra"].id,
                nodes["tron"].id,
            }
