# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Show relationship-unique trails on a directed cycle."""

import argparse
import dataclasses
import typing

from pygrafito import Direction, Graph


@dataclasses.dataclass(frozen=True, slots=True)
class TrailReport:
    """Trail enumeration result.

    Parameters
    ----------
    trails : int
        Number of relationship-unique trails.
    lengths : tuple[int, ...]
        Lengths of the enumerated trails.
    walk_example : int
        A walk length that would reuse a relationship.
    """

    trails: int
    lengths: tuple[int, ...]
    walk_example: int


class TrailsVersusWalks:
    """Contrast relationship-unique trails with unrestricted walks."""

    NOTE: typing.ClassVar[str] = (
        "paths() enumerates relationship-unique trails. The query language defaults to WALK, so "
        "use MATCH TRAIL when you want the same relationship-unique behavior; the legacy "
        "quantifier keeps its TRAIL default."
    )

    @classmethod
    def run(cls, max_depth: int = 6) -> TrailReport:
        """Enumerate trails around a directed three-node cycle.

        Parameters
        ----------
        max_depth : int, optional
            Maximum trail depth, by default 6.

        Returns
        -------
        TrailReport
            Trail count, lengths, and a walk example.
        """
        with Graph.open(":memory:") as graph:
            yori = graph.add_node("Program", designation="Yori")
            dumont = graph.add_node("Program", designation="Dumont")
            ram = graph.add_node("Program", designation="Ram")
            graph.add_relationship(yori, "ALLIES_WITH", dumont)
            graph.add_relationship(dumont, "ALLIES_WITH", ram)
            graph.add_relationship(ram, "ALLIES_WITH", yori)
            trails = tuple(
                graph.paths(
                    yori,
                    yori,
                    max_depth=max_depth,
                    min_depth=1,
                    direction=Direction.OUTGOING,
                )
            )
        lengths = tuple(trail.length for trail in trails)
        return TrailReport(trails=len(trails), lengths=lengths, walk_example=max_depth)

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the trail report.

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
        parser.add_argument("--max-depth", type=int, default=6)
        arguments = parser.parse_args(argv)
        report = cls.run(arguments.max_depth)
        print(f"trails: {report.trails} (lengths {list(report.lengths)})")
        print(f"a {report.walk_example}-hop walk would reuse a relationship")
        print(cls.NOTE)
        return 0


if __name__ == "__main__":
    raise SystemExit(TrailsVersusWalks.main())
