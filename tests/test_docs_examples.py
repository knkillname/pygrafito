# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Execute onboarding examples and syntax-check the documentation site."""

import ast
import contextlib
import io
import re
import typing
from collections.abc import Iterator
from pathlib import Path

import pytest


class TestDocumentationExamples:
    """Verify that documented Python examples are runnable or valid."""

    ROOT: typing.ClassVar[Path] = Path(__file__).resolve().parents[1]
    EXECUTABLE: typing.ClassVar[tuple[Path, ...]] = (
        ROOT / "docs" / "index.md",
        ROOT / "docs" / "getting-started" / "quickstart.md",
    )
    ONBOARDING: typing.ClassVar[tuple[Path, ...]] = EXECUTABLE
    EXECUTABLE_GLOBS: typing.ClassVar[tuple[str, ...]] = ("docs/guides/*.md",)
    PARSE_GLOBS: typing.ClassVar[tuple[str, ...]] = ("docs/reference/*.md", "docs/api/*.md")
    PYTHON_FENCE: typing.ClassVar[re.Pattern[str]] = re.compile(
        r"```python\n(.*?)```",
        flags=re.DOTALL,
    )

    @classmethod
    def executable_pages(cls) -> Iterator[Path]:
        """Yield pages whose Python fences must run.

        Yields
        ------
        Path
            Markdown page with complete, executable examples.
        """
        yield from (path for path in cls.EXECUTABLE if path.exists())
        for pattern in cls.EXECUTABLE_GLOBS:
            yield from sorted(cls.ROOT.glob(pattern))

    @classmethod
    def parsed_pages(cls) -> Iterator[Path]:
        """Yield reference and API pages whose fences must parse.

        Yields
        ------
        Path
            Markdown page whose snippets may be fragments.
        """
        for pattern in cls.PARSE_GLOBS:
            yield from sorted(cls.ROOT.glob(pattern))

    @classmethod
    def snippets(cls, page: Path) -> tuple[str, ...]:
        """Return the Python fences of one page.

        Parameters
        ----------
        page : Path
            Markdown page to inspect.

        Returns
        -------
        tuple[str, ...]
            Source text of each fenced Python block.
        """
        return tuple(cls.PYTHON_FENCE.findall(page.read_text(encoding="utf-8")))

    def test_onboarding_pages_have_python_examples(self) -> None:
        """Require the landing page and quickstart to contain runnable examples."""
        for page in self.ONBOARDING:
            assert self.snippets(page), f"{page} has no Python example"

    def test_onboarding_examples_execute(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Run every Python fence in the landing page, quickstart, and guides.

        Parameters
        ----------
        monkeypatch : pytest.MonkeyPatch
            Fixture used to isolate the working directory.
        tmp_path : Path
            Temporary directory used as the working directory.
        """
        monkeypatch.chdir(tmp_path)
        for page in self.executable_pages():
            for index, snippet in enumerate(self.snippets(page)):
                namespace: dict[str, object] = {"__name__": "__docs__"}
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        exec(compile(snippet, f"{page}[{index}]", "exec"), namespace)
                    except Exception as error:
                        message = f"{page} snippet {index} failed"
                        raise AssertionError(message) from error

    def test_reference_examples_parse(self) -> None:
        """Parse every Python fence in reference and API pages."""
        for page in self.parsed_pages():
            for index, snippet in enumerate(self.snippets(page)):
                try:
                    ast.parse(snippet, filename=f"{page}[{index}]")
                except SyntaxError as error:
                    message = f"{page} snippet {index} is not valid Python"
                    raise AssertionError(message) from error
