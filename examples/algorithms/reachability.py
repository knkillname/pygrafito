# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Compare reachable nodes with the one shortest route."""

import argparse
import dataclasses
import typing

from examples.support.dataset import Dataset
from pygrafito import Direction, Graph


@dataclasses.dataclass(frozen=True, slots=True)
class ReachabilityReport:
    """Reachability and shortest-route results.

    Parameters
    ----------
    start : str
        Start designation.
    reachable : tuple[tuple[str, int], ...]
        Reachable designations with their shortest depth.
    route : tuple[str, ...]
        Designations along the shortest route.
    length : int
        Number of relationships in the route.
    """

    start: str
    reachable: tuple[tuple[str, int], ...]
    route: tuple[str, ...]
    length: int


class Reachability:
    """Compare breadth-first reachability with a shortest path."""

    START: typing.ClassVar[str] = "Real World"
    END: typing.ClassVar[str] = "I/O Tower"

    @classmethod
    def run(cls) -> ReachabilityReport:
        """Traverse the places network and choose one route.

        Returns
        -------
        ReachabilityReport
            Depths and the shortest route.
        """
        with Graph.open(":memory:") as graph:
            Dataset.seed(Dataset.load("places"), graph)
            start = next(iter(graph.find_nodes(designation=cls.START)))
            end = next(iter(graph.find_nodes(designation=cls.END)))
            reachable = tuple(
                (str(step.node["designation"]), step.depth)
                for step in graph.traverse(start, max_depth=4, direction=Direction.BOTH)
            )
            path = graph.shortest_path(start, end, direction=Direction.BOTH, max_depth=4)
            route = tuple(str(node["designation"]) for node in path.nodes) if path else ()
            length = path.length if path else 0
        return ReachabilityReport(
            start=str(start["designation"]),
            reachable=reachable,
            route=route,
            length=length,
        )

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the reachability report.

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
        print(f"from {report.start}")
        for name, depth in report.reachable:
            print(f"  depth {depth}: {name}")
        print(f"shortest route ({report.length} hops): {' -> '.join(report.route)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(Reachability.main())
