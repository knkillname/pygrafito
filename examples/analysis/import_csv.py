# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Import typed program rows from CSV."""

import argparse
import dataclasses
import pathlib
import typing

from examples.support.dataset import Dataset
from pygrafito import Graph, ImportSummary


@dataclasses.dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of the CSV import.

    Parameters
    ----------
    summary : ImportSummary
        Import counts.
    programs : tuple[tuple[str, int], ...]
        Imported designations and cycles.
    """

    summary: ImportSummary
    programs: tuple[tuple[str, int], ...]


class ImportCsv:
    """Import program rows through ``Graph.import_file``."""

    STATEMENT: typing.ClassVar[str] = (
        "UNWIND $rows AS row "
        "CREATE (n:Program {designation: row.designation, cycles: toInteger(row.cycles)})"
    )

    @classmethod
    def run(cls, path: str | pathlib.Path | None = None) -> ImportResult:
        """Import the CSV fixture or a caller-supplied file.

        Parameters
        ----------
        path : str | pathlib.Path | None, optional
            CSV file, by default the bundled ``examples/data/programs.csv``.

        Returns
        -------
        ImportResult
            Import counts and typed rows.
        """
        source = pathlib.Path(path) if path is not None else Dataset.DATA_DIRECTORY / "programs.csv"
        with Graph.open(":memory:") as graph:
            summary = graph.import_file(source, cls.STATEMENT)
            programs = tuple(
                sorted(
                    (str(node["designation"]), cycles)
                    for node in graph.find_nodes("Program")
                    if isinstance((cycles := node.get("cycles")), int)
                    and not isinstance(cycles, bool)
                )
            )
        return ImportResult(summary=summary, programs=programs)

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the import summary.

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
        parser.add_argument("--path", help="CSV file to import")
        arguments = parser.parse_args(argv)
        result = cls.run(arguments.path)
        print(
            f"rows={result.summary.rows} batches={result.summary.batches} "
            f"created={result.summary.mutations.created_nodes}"
        )
        for designation, cycles in result.programs:
            print(f"{designation:<16}{cycles:>6}")
        return 0


if __name__ == "__main__":
    raise SystemExit(ImportCsv.main())
