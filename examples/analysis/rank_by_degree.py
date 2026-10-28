# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Rank programs by weighted degree over the cast aggregates."""

import argparse
import collections
import dataclasses
import typing

from examples.support.dataset import Dataset
from pygrafito import Graph


@dataclasses.dataclass(frozen=True, slots=True)
class Ranked:
    """One ranked program.

    Parameters
    ----------
    name : str
        Program designation.
    degree : int
        Sum of incident edge weights.
    """

    name: str
    degree: int


class RankByDegree:
    """Rank programs by the sum of their incident cast weights."""

    @classmethod
    def run(cls, limit: int = 10) -> tuple[Ranked, ...]:
        """Rank the programs in the cast dataset.

        Parameters
        ----------
        limit : int, optional
            Number of rows to return, by default 10.

        Returns
        -------
        tuple[Ranked, ...]
            Programs ordered by descending weighted degree, then name.

        Raises
        ------
        ValueError
            If the limit is negative.
        """
        if limit < 0:
            message = "limit must be non-negative"
            raise ValueError(message)
        with Graph.open(":memory:") as graph:
            Dataset.seed(Dataset.load("cast"), graph)
            programs = {node.id: str(node["designation"]) for node in graph.find_nodes("Program")}
            degrees: collections.Counter[int] = collections.Counter()
            for relationship in graph.find_relationships():
                raw_weight = relationship.get("weight")
                weight = (
                    raw_weight
                    if isinstance(raw_weight, int) and not isinstance(raw_weight, bool)
                    else 1
                )
                if relationship.start_id in programs:
                    degrees[relationship.start_id] += weight
                if relationship.end_id in programs:
                    degrees[relationship.end_id] += weight
        ranked = sorted(
            ((programs[node_id], degree) for node_id, degree in degrees.items()),
            key=lambda item: (-item[1], item[0]),
        )
        return tuple(Ranked(name, degree) for name, degree in ranked[:limit])

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the ranking.

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
        parser.add_argument("--limit", type=int, default=10)
        arguments = parser.parse_args(argv)
        rows = cls.run(arguments.limit)
        print(f"{'program':<24}{'weighted degree':>16}")
        for row in rows:
            print(f"{row.name:<24}{row.degree:>16}")
        return 0


if __name__ == "__main__":
    raise SystemExit(RankByDegree.main())
