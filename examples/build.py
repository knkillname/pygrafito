# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Build example datasets into databases or version 2 snapshots."""

import dataclasses
import pathlib
import typing

from examples.support.dataset import Dataset, DatasetError, Synthetic
from pygrafito import Graph


@dataclasses.dataclass(frozen=True, slots=True)
class BuildResult:
    """Outcome of one dataset build.

    Parameters
    ----------
    name : str
        Dataset name.
    nodes : int
        Number of created nodes.
    relationships : int
        Number of created relationships.
    path : pathlib.Path | None
        Output path, or ``None`` for an in-memory build.
    """

    name: str
    nodes: int
    relationships: int
    path: pathlib.Path | None


@dataclasses.dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One discoverable dataset or lane.

    Parameters
    ----------
    name : str
        Dataset or lane name.
    description : str
        One-line description.
    """

    name: str
    description: str


class Build:
    """Build curated and synthetic datasets."""

    FORMATS: typing.ClassVar[tuple[str, ...]] = ("db", "jsonl")
    CATALOG: typing.ClassVar[tuple[CatalogEntry, ...]] = (
        CatalogEntry("grid", "curated franchise graph across three sources"),
        CatalogEntry("cast", "weighted co-occurrence and dialogue-turn aggregates"),
        CatalogEntry("places", "containment hierarchy and scene transitions"),
        CatalogEntry("all", "grid, cast, and places merged by shared handles"),
        CatalogEntry("synthetic", "seeded scale graph shared with the benchmark harness"),
    )
    LANES: typing.ClassVar[tuple[CatalogEntry, ...]] = (
        CatalogEntry("tours/", "shell narratives in .gql, classified by GQL profile tier"),
        CatalogEntry("analysis/", "tables, CSV import, SQL views, and snapshot export"),
        CatalogEntry("algorithms/", "reachability, trails, shortest paths, and scaling"),
    )

    @classmethod
    def build(
        cls,
        name: str,
        *,
        output: str | pathlib.Path | None = None,
        format: str = "db",
        nodes: int = 200,
        relationships: int = 600,
        seed: int = 0,
        overwrite: bool = False,
    ) -> BuildResult:
        """Build one dataset.

        Parameters
        ----------
        name : str
            Dataset name, including ``synthetic``.
        output : str | pathlib.Path | None, optional
            Destination path, by default in-memory only.
        format : str, optional
            ``db`` or ``jsonl``, by default ``db``.
        nodes : int, optional
            Synthetic node count, by default 200.
        relationships : int, optional
            Synthetic relationship count, by default 600.
        seed : int, optional
            Synthetic vocabulary seed, by default 0.
        overwrite : bool, optional
            Whether an existing destination may be replaced, by default ``False``.

        Returns
        -------
        BuildResult
            Counts and the output path.

        Raises
        ------
        DatasetError
            If the name, format, destination, or counts are invalid.
        """
        if format not in cls.FORMATS:
            message = f"unknown output format {format!r}; expected db or jsonl"
            raise DatasetError(message)
        if name not in (*Dataset.NAMES, "synthetic"):
            available = ", ".join((*Dataset.NAMES, "synthetic"))
            message = f"unknown dataset {name!r}; expected {available}"
            raise DatasetError(message)
        destination = pathlib.Path(output) if output is not None else None
        if destination is not None and destination.exists() and not overwrite:
            message = f"output already exists: {destination}"
            raise DatasetError(message)
        if name == "synthetic":
            return cls._build_synthetic(
                destination,
                format=format,
                nodes=nodes,
                relationships=relationships,
                seed=seed,
                overwrite=overwrite,
            )
        document = Dataset.load(name)
        if destination is None:
            with Graph.open(":memory:") as graph:
                summary = Dataset.seed(document, graph)
            return BuildResult(name, summary.nodes, summary.relationships, None)
        if format == "db":
            cls._prepare_database(destination, overwrite)
            graph = Graph.open(destination)
            try:
                summary = Dataset.seed(document, graph)
                Dataset.apply_schema(document, graph)
            finally:
                graph.close()
            return BuildResult(name, summary.nodes, summary.relationships, destination)
        with Graph.open(":memory:") as graph:
            summary = Dataset.seed(document, graph)
            graph.export_jsonl(destination, overwrite=overwrite)
        return BuildResult(name, summary.nodes, summary.relationships, destination)

    @classmethod
    def _build_synthetic(
        cls,
        destination: pathlib.Path | None,
        *,
        format: str,
        nodes: int,
        relationships: int,
        seed: int,
        overwrite: bool,
    ) -> BuildResult:
        """Build the synthetic fixture.

        Parameters
        ----------
        destination : pathlib.Path | None
            Output path, or ``None`` for in-memory only.
        format : str
            ``db`` or ``jsonl``.
        nodes : int
            Node count.
        relationships : int
            Relationship count.
        seed : int
            Vocabulary seed.
        overwrite : bool
            Whether an existing destination may be replaced.

        Returns
        -------
        BuildResult
            Counts and the output path.
        """
        generator = Synthetic(nodes, relationships, seed)
        if destination is None:
            with Graph.open(":memory:") as graph:
                created = generator.build(graph)
            return BuildResult("synthetic", len(created), relationships, None)
        if format == "db":
            cls._prepare_database(destination, overwrite)
            graph = Graph.open(destination)
            try:
                created = generator.build(graph)
            finally:
                graph.close()
            return BuildResult("synthetic", len(created), relationships, destination)
        with Graph.open(":memory:") as graph:
            created = generator.build(graph)
            graph.export_jsonl(destination, overwrite=overwrite)
        return BuildResult("synthetic", len(created), relationships, destination)

    @classmethod
    def _prepare_database(cls, destination: pathlib.Path, overwrite: bool) -> None:
        """Remove an existing database before replacing it.

        Parameters
        ----------
        destination : pathlib.Path
            Database path.
        overwrite : bool
            Whether replacement is allowed.

        Raises
        ------
        DatasetError
            If the destination exists and replacement is not allowed.
        """
        if not destination.exists():
            return
        if not overwrite:
            message = f"output already exists: {destination}"
            raise DatasetError(message)
        for suffix in ("", "-wal", "-shm"):
            path = destination if not suffix else destination.with_name(destination.name + suffix)
            path.unlink(missing_ok=True)

    @classmethod
    def describe(cls) -> tuple[str, ...]:
        """Return the catalog lines printed by the front door.

        Returns
        -------
        tuple[str, ...]
            Dataset, lane, and command descriptions.
        """
        lines = ["Datasets:"]
        lines.extend(f"  {entry.name:<12}{entry.description}" for entry in cls.CATALOG)
        lines.append("Lanes:")
        lines.extend(f"  {entry.name:<12}{entry.description}" for entry in cls.LANES)
        lines.append("Commands:")
        lines.extend(
            (
                "  python -m examples build grid --output grid.db",
                "  python -m examples build all --output all.jsonl --format jsonl",
                "  python -m examples build synthetic --nodes 5000 --relationships 15000",
                "  pygrafito grid.db -f examples/tours/01-match.gql",
                "  python -m examples.analysis.rank_by_degree",
                "  python -m examples.algorithms.trails_vs_walks",
            )
        )
        return tuple(lines)

    @classmethod
    def summary(cls, result: BuildResult) -> str:
        """Format a build result for the console.

        Parameters
        ----------
        result : BuildResult
            Completed build.

        Returns
        -------
        str
            Human-readable summary.
        """
        destination = f" -> {result.path}" if result.path is not None else " (in memory)"
        return (
            f"built {result.name}: {result.nodes} nodes, "
            f"{result.relationships} relationships{destination}"
        )
