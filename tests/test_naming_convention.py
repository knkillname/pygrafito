# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Guard graph-building tests against generic placeholder fixtures."""

import ast
import typing
from collections.abc import Iterator
from pathlib import Path


class TestNamingConvention:
    """Verify that graph fixtures use TRON names."""

    ROOT: typing.ClassVar[Path] = Path(__file__).resolve().parent
    SELF: typing.ClassVar[Path] = Path(__file__).resolve()
    MARKERS: typing.ClassVar[tuple[str, ...]] = (
        "Graph.open",
        "NodeRepository",
        "RelationshipRepository",
    )
    BANNED: typing.ClassVar[frozenset[str]] = frozenset(
        {
            "Ada",
            "Grace",
            "Bob",
            "Alice",
            "Carol",
            "Dave",
            "Person",
            "Employee",
            "Manager",
            "KNOWS",
            "LIKES",
            "ROUTE",
        }
    )

    @classmethod
    def graph_test_files(cls) -> Iterator[Path]:
        """Yield test files that build or query a graph.

        Yields
        ------
        Path
            Test file that references a graph-building API.
        """
        for path in sorted(cls.ROOT.rglob("*.py")):
            if path.resolve() == cls.SELF:
                continue
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in cls.MARKERS):
                yield path

    @classmethod
    def violations(cls, path: Path) -> list[tuple[int, str]]:
        """Find banned placeholder strings in one test file.

        Parameters
        ----------
        path : Path
            Python file to inspect.

        Returns
        -------
        list[tuple[int, str]]
            Line numbers and banned strings found in the file.
        """
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in cls.BANNED
            ):
                found.append((node.lineno, node.value))
        return found

    def test_graph_tests_use_tron_fixtures(self) -> None:
        """Report every graph-building test that still uses placeholders."""
        reports = {
            str(path.relative_to(self.ROOT)): violations
            for path in self.graph_test_files()
            if (violations := self.violations(path))
        }
        assert not reports, reports

    def test_scanner_detects_violation(self, tmp_path: Path) -> None:
        """Prove the scanner catches a banned placeholder.

        Parameters
        ----------
        tmp_path : Path
            Temporary directory for the sample test file.
        """
        sample = tmp_path / "test_sample.py"
        sample.write_text(
            '"""Sample graph fixture."""\n\ngraph.add_node("Person")\n',
            encoding="utf-8",
        )
        assert self.violations(sample) == [(3, "Person")]
