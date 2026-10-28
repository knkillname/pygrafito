# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Find the shortest route through the places network."""

import argparse
import dataclasses
import typing

from examples.support.dataset import Dataset
from pygrafito import Direction, Graph


@dataclasses.dataclass(frozen=True, slots=True)
class PathReport:
    """Shortest-route result.

    Parameters
    ----------
    route : tuple[str, ...]
        Designations along the route.
    length : int
        Number of relationships.
    routes : int
        Number of trails found within the same depth bound, capped at ten.
    """

    route: tuple[str, ...]
    length: int
    routes: int


class ShortestPath:
    """Use bidirectional BFS and compare it with bounded trails."""

    START: typing.ClassVar[str] = "Flynn's Arcade"
    END: typing.ClassVar[str] = "I/O Tower"

    @classmethod
    def run(cls) -> PathReport:
        """Find a shortest route between two places.

        Returns
        -------
        PathReport
            Route, length, and alternate trail count.
        """
        with Graph.open(":memory:") as graph:
            Dataset.seed(Dataset.load("places"), graph)
            start = next(iter(graph.find_nodes(designation=cls.START)))
            end = next(iter(graph.find_nodes(designation=cls.END)))
            path = graph.shortest_path(start, end, direction=Direction.BOTH, max_depth=6)
            route = tuple(str(node["designation"]) for node in path.nodes) if path else ()
            length = path.length if path else 0
            routes = len(
                tuple(
                    graph.paths(
                        start,
                        end,
                        max_depth=6,
                        direction=Direction.BOTH,
                        limit=10,
                    )
                )
            )
        return PathReport(route=route, length=length, routes=routes)

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the route.

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
        print(f"shortest route ({report.length} hops): {' -> '.join(report.route)}")
        print(f"bounded trails found: {report.routes} (limit 10)")
        return 0


if __name__ == "__main__":
    raise SystemExit(ShortestPath.main())
