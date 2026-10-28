# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Read the published SQL views with the standard library."""

import argparse
import dataclasses
import json
import pathlib
import sqlite3
import tempfile
import typing

from examples.build import Build


@dataclasses.dataclass(frozen=True, slots=True)
class ViewSnapshot:
    """Rows read from the read-only views.

    Parameters
    ----------
    nodes : int
        Number of rows in ``graph_nodes``.
    relationships : int
        Number of rows in ``graph_relationships``.
    node_labels : tuple[str, ...]
        Labels of the first node row.
    relationship_labels : tuple[str, ...]
        Labels of the first relationship row.
    directed : bool
        Whether the first relationship is directed.
    """

    nodes: int
    relationships: int
    node_labels: tuple[str, ...]
    relationship_labels: tuple[str, ...]
    directed: bool


class SqlViews:
    """Query the graph through SQLite's read-only views."""

    @classmethod
    def run(cls) -> ViewSnapshot:
        """Build a temporary Grid and read its views read-only.

        Returns
        -------
        ViewSnapshot
            Counts and first-row metadata.
        """
        with tempfile.TemporaryDirectory() as directory:
            database = pathlib.Path(directory) / "grid.db"
            Build.build("grid", output=database)
            reader = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
            try:
                nodes = int(reader.execute("SELECT count(*) FROM graph_nodes").fetchone()[0])
                relationships = int(
                    reader.execute("SELECT count(*) FROM graph_relationships").fetchone()[0]
                )
                node_labels = json.loads(
                    reader.execute("SELECT labels FROM graph_nodes ORDER BY id LIMIT 1").fetchone()[
                        0
                    ]
                )
                relationship = reader.execute(
                    "SELECT labels, directed FROM graph_relationships ORDER BY id LIMIT 1"
                ).fetchone()
            finally:
                reader.close()
        return ViewSnapshot(
            nodes=nodes,
            relationships=relationships,
            node_labels=tuple(str(label) for label in node_labels),
            relationship_labels=tuple(str(label) for label in json.loads(relationship[0])),
            directed=bool(relationship[1]),
        )

    @classmethod
    def main(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Print the view snapshot.

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
        snapshot = cls.run()
        print(f"graph_nodes        {snapshot.nodes}")
        print(f"graph_relationships {snapshot.relationships}")
        print(f"first node labels   {list(snapshot.node_labels)}")
        print(f"first rel labels    {list(snapshot.relationship_labels)}")
        print(f"first rel directed  {snapshot.directed}")
        return 0


if __name__ == "__main__":
    raise SystemExit(SqlViews.main())
