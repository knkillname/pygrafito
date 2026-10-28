# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Write a CSV report and a JSONL snapshot from the curated graph."""

import argparse
import csv
import dataclasses
import pathlib
import typing

from examples.support.dataset import Dataset
from pygrafito import Graph


@dataclasses.dataclass(frozen=True, slots=True)
class Report:
    """Paths and rows produced by the report.

    Parameters
    ----------
    csv_path : pathlib.Path
        Written CSV report.
    snapshot_path : pathlib.Path
        Written JSONL snapshot.
    rows : tuple[tuple[str, int], ...]
        Program designations and cycles.
    """

    csv_path: pathlib.Path
    snapshot_path: pathlib.Path
    rows: tuple[tuple[str, int], ...]


class ExportReport:
    """Build the Grid and write a CSV report plus a snapshot."""

    @classmethod
    def run(cls, output: str | pathlib.Path | None = None) -> Report:
        """Write the report files.

        Parameters
        ----------
        output : str | pathlib.Path | None, optional
            Destination directory, by default ``examples-report`` beside the current directory.

        Returns
        -------
        Report
            Written paths and report rows.
        """
        directory = pathlib.Path(output) if output is not None else pathlib.Path("examples-report")
        directory.mkdir(parents=True, exist_ok=True)
        csv_path = directory / "report.csv"
        snapshot_path = directory / "grid.jsonl"
        with Graph.open(":memory:") as graph:
            Dataset.seed(Dataset.load("grid"), graph)
            rows = tuple(
                sorted(
                    (str(node["designation"]), cycles)
                    for node in graph.find_nodes("Program")
                    if isinstance((cycles := node.get("cycles")), int)
                    and not isinstance(cycles, bool)
                )
            )
            graph.export_jsonl(snapshot_path, overwrite=True)
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("designation", "cycles"))
            writer.writerows(rows)
        return Report(csv_path=csv_path, snapshot_path=snapshot_path, rows=rows)

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the written report paths.

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
        parser.add_argument("--output", help="destination directory")
        arguments = parser.parse_args(argv)
        report = cls.run(arguments.output)
        print(f"wrote {len(report.rows)} rows to {report.csv_path}")
        print(f"wrote snapshot to {report.snapshot_path}")
        return 0


if __name__ == "__main__":
    raise SystemExit(ExportReport.main())
