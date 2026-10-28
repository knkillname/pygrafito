# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Show how direction changes reachability."""

import argparse
import dataclasses
import typing

from examples.support.dataset import Dataset
from pygrafito import Direction, Graph, Node


@dataclasses.dataclass(frozen=True, slots=True)
class DirectionReport:
    """Direction-sensitive traversal result.

    Parameters
    ----------
    created_out : tuple[str, ...]
        Nodes reached from Kevin Flynn along outgoing CREATED edges.
    created_in : tuple[str, ...]
        Nodes reaching Clu along incoming CREATED edges.
    created_out_from_target : tuple[str, ...]
        Nodes reached from Clu along outgoing CREATED edges.
    alliance_from_ram : tuple[str, ...]
        Nodes reached from Ram along outgoing ALLIES_WITH edges.
    """

    created_out: tuple[str, ...]
    created_in: tuple[str, ...]
    created_out_from_target: tuple[str, ...]
    alliance_from_ram: tuple[str, ...]


class DirectionDemo:
    """Compare outgoing, incoming, and undirected traversal."""

    @classmethod
    def run(cls) -> DirectionReport:
        """Traverse the Grid in three directions.

        Returns
        -------
        DirectionReport
            Designations reached in each direction.
        """
        with Graph.open(":memory:") as graph:
            Dataset.seed(Dataset.load("grid"), graph)
            kevin = next(iter(graph.find_nodes(designation="Kevin Flynn")))
            clu = next(iter(graph.find_nodes(designation="Clu")))
            ram = next(iter(graph.find_nodes(designation="Ram")))
            created_out = cls._names(graph, kevin, "CREATED", Direction.OUTGOING)
            created_in = cls._names(graph, clu, "CREATED", Direction.INCOMING)
            created_out_from_target = cls._names(graph, clu, "CREATED", Direction.OUTGOING)
            alliance_from_ram = cls._names(graph, ram, "ALLIES_WITH", Direction.OUTGOING)
        return DirectionReport(
            created_out=created_out,
            created_in=created_in,
            created_out_from_target=created_out_from_target,
            alliance_from_ram=alliance_from_ram,
        )

    @classmethod
    def _names(
        cls,
        graph: Graph,
        start: Node,
        label: str,
        direction: Direction,
    ) -> tuple[str, ...]:
        """Return designations reached in one direction.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        label : str
            Relationship label filter.
        direction : Direction
            Traversal direction.

        Returns
        -------
        tuple[str, ...]
            Reached designations in traversal order.
        """
        return tuple(
            str(step.node["designation"])
            for step in graph.traverse(
                start,
                max_depth=1,
                direction=direction,
                labels=[label],
            )
        )

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the direction report.

        Parameters
        ----------
        argv : typing.Sequence[str] | None, optional
            Argument list, by default ``None``.

        Returns
        -------
        int
            Process exit code.
        """
        argparse.ArgumentParser(description=__doc__).parse_args(argv)
        report = cls.run()
        print(f"Kevin Flynn -CREATED-> {list(report.created_out)}")
        print(f"Clu <-CREATED- {list(report.created_in)}")
        print(f"Clu -CREATED-> {list(report.created_out_from_target)}")
        print(f"Ram -ALLIES_WITH- {list(report.alliance_from_ram)} (undirected edge)")
        return 0


if __name__ == "__main__":
    raise SystemExit(DirectionDemo.main())
