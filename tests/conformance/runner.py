# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Data-driven conformance corpus for the GQL profile."""

import dataclasses
import json
import pathlib
import typing
from collections.abc import Mapping

from pygrafito import Graph, PygrafitoError
from pygrafito.model import Value


@dataclasses.dataclass(frozen=True, slots=True)
class NodeSpec:
    """One fixture node.

    Parameters
    ----------
    handle : str
        Stable handle used by relationships.
    labels : tuple[str, ...]
        Labels attached to the node.
    properties : Mapping[str, Value]
        Typed properties attached to the node.
    """

    handle: str
    labels: tuple[str, ...]
    properties: Mapping[str, Value]


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipSpec:
    """One fixture relationship.

    Parameters
    ----------
    start : str
        Handle of the first endpoint.
    end : str
        Handle of the second endpoint.
    labels : tuple[str, ...]
        Labels attached to the relationship.
    directed : bool
        Whether the relationship is directed.
    properties : Mapping[str, Value]
        Typed properties attached to the relationship.
    """

    start: str
    end: str
    labels: tuple[str, ...]
    directed: bool
    properties: Mapping[str, Value]


@dataclasses.dataclass(frozen=True, slots=True)
class Fixture:
    """One named graph fixture.

    Parameters
    ----------
    nodes : tuple[NodeSpec, ...]
        Nodes in declaration order.
    relationships : tuple[RelationshipSpec, ...]
        Relationships in declaration order.
    """

    nodes: tuple[NodeSpec, ...]
    relationships: tuple[RelationshipSpec, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Case:
    """One conformance case.

    Parameters
    ----------
    name : str
        Unique kebab-case identifier.
    feature : str
        Feature id derived from the conformance matrix.
    fixture : str
        Name of the graph fixture the case runs against.
    query : str
        Statement text.
    params : Mapping[str, Value]
        Optional parameter mapping.
    expect : Mapping[str, object]
        Expected rows or expected error.
    tags : tuple[str, ...]
        Classification tags such as ``canonical``, ``alias``, or ``gated``.
    """

    name: str
    feature: str
    fixture: str
    query: str
    params: Mapping[str, Value]
    expect: Mapping[str, object]
    tags: tuple[str, ...]

    @property
    def gated(self) -> bool:
        """Report whether the case documents a gated construct.

        Returns
        -------
        bool
            ``True`` when ``gated`` is one of the tags.
        """
        return "gated" in self.tags


class Corpus:
    """Load and execute the conformance corpus.

    Parameters
    ----------
    path : pathlib.Path
        Path to the corpus JSON document.
    """

    def __init__(self, path: pathlib.Path) -> None:
        self._path = path
        self._fixtures, self._cases = self._load(path)

    @property
    def cases(self) -> tuple[Case, ...]:
        """Return every case in document order.

        Returns
        -------
        tuple[Case, ...]
            Loaded cases.
        """
        return self._cases

    @property
    def fixtures(self) -> Mapping[str, Fixture]:
        """Return the named fixture library.

        Returns
        -------
        Mapping[str, Fixture]
            Fixture name to fixture.
        """
        return self._fixtures

    def check(self, case: Case) -> None:
        """Execute one case and assert its expectation.

        Parameters
        ----------
        case : Case
            Case to check.

        Raises
        ------
        AssertionError
            If the result or the error does not match the expectation.
        """
        try:
            rows = self.run(case)
        except PygrafitoError as error:
            self._check_error(case, error)
            return
        expected = case.expect.get("rows")
        if expected is None:
            raise AssertionError(f"{case.name} [{case.feature}]: expected an error, got rows")
        assert rows == expected, f"{case.name} [{case.feature}]: {rows!r} != {expected!r}"

    def run(self, case: Case) -> list[dict[str, object]]:
        """Build the fixture and execute one case.

        Parameters
        ----------
        case : Case
            Case to execute.

        Returns
        -------
        list[dict[str, object]]
            Projected rows as plain mappings.
        """
        fixture = self._fixtures[case.fixture]
        with Graph.open(":memory:") as graph:
            self._build(graph, fixture)
            result = graph.query(case.query, dict(case.params))
            return [dict(row) for row in result.rows]

    @staticmethod
    def _build(graph: Graph, fixture: Fixture) -> None:
        """Create every fixture element in one graph.

        Parameters
        ----------
        graph : Graph
            Writable graph that receives the fixture.
        fixture : Fixture
            Fixture to create.
        """
        created = {}
        for node in fixture.nodes:
            created[node.handle] = graph.add_node(*node.labels, **node.properties)
        for relationship in fixture.relationships:
            graph.add_relationship(
                created[relationship.start],
                relationship.labels,
                created[relationship.end],
                directed=relationship.directed,
                **relationship.properties,
            )

    @staticmethod
    def _check_error(case: Case, error: PygrafitoError) -> None:
        """Assert one expected error.

        Parameters
        ----------
        case : Case
            Case whose expectation is checked.
        error : PygrafitoError
            Raised error.

        Raises
        ------
        AssertionError
            If the error type or fragment does not match.
        """
        expected = case.expect.get("error")
        if not isinstance(expected, dict):
            raise AssertionError(f"{case.name} [{case.feature}]: unexpected {error!r}")
        type_name = expected.get("type")
        assert type(error).__name__ == type_name, (
            f"{case.name} [{case.feature}]: {type(error).__name__} != {type_name}"
        )
        fragment = expected.get("contains")
        if fragment is not None:
            assert fragment in str(error), (
                f"{case.name} [{case.feature}]: {fragment!r} not in {str(error)!r}"
            )

    @classmethod
    def _load(
        cls,
        path: pathlib.Path,
    ) -> tuple[Mapping[str, Fixture], tuple[Case, ...]]:
        """Parse the corpus document.

        Parameters
        ----------
        path : pathlib.Path
            Path to the corpus JSON document.

        Returns
        -------
        tuple[Mapping[str, Fixture], tuple[Case, ...]]
            Fixture library and cases.
        """
        payload = typing.cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        raw_fixtures = typing.cast("dict[str, object]", payload["fixtures"])
        fixtures = {
            name: cls._fixture(typing.cast("dict[str, object]", document))
            for name, document in raw_fixtures.items()
        }
        raw_cases = typing.cast("list[object]", payload["cases"])
        cases = tuple(cls._case(typing.cast("dict[str, object]", item)) for item in raw_cases)
        return fixtures, cases

    @classmethod
    def _fixture(cls, document: Mapping[str, object]) -> Fixture:
        """Parse one fixture document.

        Parameters
        ----------
        document : Mapping[str, object]
            Raw fixture.

        Returns
        -------
        Fixture
            Parsed fixture.
        """
        nodes = tuple(
            NodeSpec(
                handle=typing.cast("str", node["handle"]),
                labels=tuple(typing.cast("list[str]", node["labels"])),
                properties=typing.cast("Mapping[str, Value]", node.get("properties", {})),
            )
            for node in typing.cast("list[dict[str, object]]", document["nodes"])
        )
        relationships = tuple(
            RelationshipSpec(
                start=typing.cast("str", relationship["start"]),
                end=typing.cast("str", relationship["end"]),
                labels=tuple(typing.cast("list[str]", relationship["labels"])),
                directed=typing.cast("bool", relationship.get("directed", True)),
                properties=typing.cast("Mapping[str, Value]", relationship.get("properties", {})),
            )
            for relationship in typing.cast("list[dict[str, object]]", document["relationships"])
        )
        return Fixture(nodes=nodes, relationships=relationships)

    @classmethod
    def _case(cls, document: Mapping[str, object]) -> Case:
        """Parse one case document.

        Parameters
        ----------
        document : Mapping[str, object]
            Raw case.

        Returns
        -------
        Case
            Parsed case.
        """
        return Case(
            name=typing.cast("str", document["name"]),
            feature=typing.cast("str", document["feature"]),
            fixture=typing.cast("str", document["fixture"]),
            query=typing.cast("str", document["query"]),
            params=typing.cast("Mapping[str, Value]", document.get("params", {})),
            expect=typing.cast("Mapping[str, object]", document["expect"]),
            tags=tuple(typing.cast("list[str]", document.get("tags", []))),
        )
