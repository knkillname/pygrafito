# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Front door for the example datasets and lanes."""

import argparse
import collections.abc

from examples.build import Build


class Main:
    """Parse arguments and dispatch the example front door."""

    @classmethod
    def run(cls, argv: collections.abc.Sequence[str] | None = None) -> int:
        """Run the front door.

        Parameters
        ----------
        argv : collections.abc.Sequence[str] | None, optional
            Argument list, by default ``None`` for ``sys.argv``.

        Returns
        -------
        int
            Process exit code.
        """
        parser = cls._parser()
        arguments = parser.parse_args(argv)
        if arguments.action is None or arguments.action == "list":
            for line in Build.describe():
                print(line)
            return 0
        if arguments.action == "build":
            try:
                result = Build.build(
                    arguments.dataset,
                    output=arguments.output,
                    format=arguments.format,
                    nodes=arguments.nodes,
                    relationships=arguments.relationships,
                    seed=arguments.seed,
                    overwrite=arguments.overwrite,
                )
            except Exception as error:
                parser.error(str(error))
            print(Build.summary(result))
            return 0
        parser.error(f"unknown action: {arguments.action}")
        return 2

    @classmethod
    def _parser(cls) -> argparse.ArgumentParser:
        """Build the argument parser.

        Returns
        -------
        argparse.ArgumentParser
            Configured parser.
        """
        parser = argparse.ArgumentParser(
            prog="python -m examples",
            description="Build pygrafito example datasets and explore the lanes.",
        )
        parser.add_argument(
            "action",
            nargs="?",
            choices=("list", "build"),
            help="list the catalog or build a dataset",
        )
        parser.add_argument(
            "dataset",
            nargs="?",
            help="dataset name for the build action",
        )
        parser.add_argument("-o", "--output", help="destination database or snapshot path")
        parser.add_argument(
            "--format",
            choices=Build.FORMATS,
            default="db",
            help="output format for --output (default: db)",
        )
        parser.add_argument("--nodes", type=int, default=200, help="synthetic node count")
        parser.add_argument(
            "--relationships",
            type=int,
            default=600,
            help="synthetic relationship count",
        )
        parser.add_argument("--seed", type=int, default=0, help="synthetic vocabulary seed")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="replace an existing output path",
        )
        return parser


if __name__ == "__main__":
    raise SystemExit(Main.run())
