# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Count named entities by source film and label."""

import argparse
import collections
import dataclasses
import typing

from examples.support.dataset import Dataset
from pygrafito import Graph


@dataclasses.dataclass(frozen=True, slots=True)
class SourceCount:
    """One source and label count.

    Parameters
    ----------
    source : str
        Film handle.
    label : str
        Entity label.
    count : int
        Number of entities carrying both.
    """

    source: str
    label: str
    count: int


class AggregateBySource:
    """Group the curated graph by source film and label."""

    @classmethod
    def run(cls) -> tuple[SourceCount, ...]:
        """Count entities per source and label.

        Returns
        -------
        tuple[SourceCount, ...]
            Counts ordered by source, then descending count, then label.
        """
        counts: collections.Counter[tuple[str, str]] = collections.Counter()
        with Graph.open(":memory:") as graph:
            Dataset.seed(Dataset.load("grid"), graph)
            for node in graph.find_nodes():
                sources = node.get("sources")
                if not isinstance(sources, list):
                    continue
                for source in sources:
                    for label in node.labels:
                        counts[(str(source), label)] += 1
        ordered = sorted(
            counts.items(),
            key=lambda item: (item[0][0], -item[1], item[0][1]),
        )
        return tuple(
            SourceCount(source=source, label=label, count=count)
            for (source, label), count in ordered
        )

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the per-source counts.

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
        rows = cls.run()
        print(f"{'source':<16}{'label':<16}{'entities':>10}")
        for row in rows:
            print(f"{row.source:<16}{row.label:<16}{row.count:>10}")
        return 0


if __name__ == "__main__":
    raise SystemExit(AggregateBySource.main())
