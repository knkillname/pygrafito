# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Time bounded traversal over increasing synthetic graph sizes."""

import argparse
import dataclasses
import time
import typing

from examples.support.dataset import Synthetic
from pygrafito import Graph


@dataclasses.dataclass(frozen=True, slots=True)
class ScalingRow:
    """One scaling measurement.

    Parameters
    ----------
    nodes : int
        Graph node count.
    relationships : int
        Graph relationship count.
    depth : int
        Traversal depth.
    reached : int
        Nodes reached at the requested depth.
    milliseconds : float
        Elapsed traversal time in milliseconds.
    """

    nodes: int
    relationships: int
    depth: int
    reached: int
    milliseconds: float


class Scaling:
    """Measure traversal over a synthetic graph."""

    @classmethod
    def run(cls, nodes: int = 1000, seed: int = 0, depth: int = 2) -> ScalingRow:
        """Time one traversal.

        Parameters
        ----------
        nodes : int, optional
            Node count, by default 1000.
        seed : int, optional
            Vocabulary seed, by default 0.
        depth : int, optional
            Traversal depth, by default 2.

        Returns
        -------
        ScalingRow
            Counts and elapsed time.
        """
        relationships = nodes * 3
        with Graph.open(":memory:") as graph:
            created = Synthetic(nodes, relationships, seed).build(graph)
            started = time.perf_counter()
            reached = sum(1 for _ in graph.traverse(created[0], max_depth=depth)) if created else 0
            milliseconds = (time.perf_counter() - started) * 1000
        return ScalingRow(
            nodes=nodes,
            relationships=relationships,
            depth=depth,
            reached=reached,
            milliseconds=milliseconds,
        )

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the scaling row.

        Parameters
        ----------
        argv : typing.Sequence[str] | None, optional
            Argument list, by default ``None``.

        Returns
        -------
        int
            Process exit code.
        """
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--nodes", type=int, default=1000)
        parser.add_argument("--seed", type=int, default=0)
        parser.add_argument("--depth", type=int, default=2)
        arguments = parser.parse_args(argv)
        row = cls.run(arguments.nodes, arguments.seed, arguments.depth)
        print(
            f"nodes={row.nodes} relationships={row.relationships} depth={row.depth} "
            f"reached={row.reached} elapsed={row.milliseconds:.2f}ms"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(Scaling.main())
