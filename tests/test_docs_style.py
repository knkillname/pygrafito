# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Structural checks for the documentation style contract."""

import pathlib
import re
import typing


class TestDocumentationStyle:
    """Verify the documentation style contract across the site."""

    ROOT: typing.ClassVar[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
    DOCS: typing.ClassVar[pathlib.Path] = ROOT / "docs"
    TLDR: typing.ClassVar[str] = ":::{admonition} tl;dr"
    CALLOUT: typing.ClassVar[re.Pattern[str]] = re.compile(
        r"^:::\{(?P<name>[A-Za-z-]+)\}(?: (?P<title>.+))?$",
        flags=re.MULTILINE,
    )
    CARD: typing.ClassVar[re.Pattern[str]] = re.compile(r"^:::\{grid-item-card\} (?P<title>.+)$")
    MERMAID: typing.ClassVar[re.Pattern[str]] = re.compile(
        r"^:::\{mermaid\}\n(?P<body>.*?)\n:::$",
        flags=re.MULTILINE | re.DOTALL,
    )
    EMOJI: typing.ClassVar[re.Pattern[str]] = re.compile(
        "[\U0001f300-\U0001faff\u2600-\u27bf\u2b00-\u2bff]"
    )
    FORBIDDEN_CALLOUTS: typing.ClassVar[frozenset[str]] = frozenset(
        {
            "attention",
            "caution",
            "danger",
            "error",
            "hint",
            "important",
            "note",
            "seealso",
            "todo",
        }
    )
    ALLOWED_ADMONITIONS: typing.ClassVar[frozenset[str]] = frozenset(
        {"In detail", "Remember", "tl;dr"}
    )
    ALLOWED_DIRECTIVES: typing.ClassVar[frozenset[str]] = frozenset(
        {"admonition", "tip", "warning"}
    )
    IGNORED_DIRECTIVES: typing.ClassVar[frozenset[str]] = frozenset(
        {
            "code-block",
            "eval-rst",
            "grid",
            "grid-item-card",
            "list-table",
            "mermaid",
            "toctree",
        }
    )

    @classmethod
    def pages(cls) -> typing.Iterator[pathlib.Path]:
        """Yield the reader-facing Markdown pages, excluding the generated API pages.

        Yields
        ------
        pathlib.Path
            Documentation page to inspect.
        """
        for page in sorted(cls.DOCS.rglob("*.md")):
            relative = page.relative_to(cls.DOCS)
            if any(part in {"api", "_build", "_static"} for part in relative.parts):
                continue
            yield page

    @classmethod
    def outside_fences(cls, page: pathlib.Path) -> typing.Iterator[str]:
        """Yield the lines of a page that are outside fenced code blocks.

        Parameters
        ----------
        page : pathlib.Path
            Page to inspect.

        Yields
        ------
        str
            Line outside a fenced code block.
        """
        in_fence = False
        for line in page.read_text(encoding="utf-8").splitlines():
            if line.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if not in_fence:
                yield line

    @classmethod
    def first_block(cls, page: pathlib.Path) -> str:
        """Return the first non-blank line after the page title.

        Parameters
        ----------
        page : pathlib.Path
            Page to inspect.

        Returns
        -------
        str
            First non-blank line after the H1.
        """
        lines = page.read_text(encoding="utf-8").splitlines()
        title = next(index for index, line in enumerate(lines) if line.startswith("# "))
        for line in lines[title + 1 :]:
            if line.strip():
                return line.strip()
        return ""

    @classmethod
    def headings(cls, page: pathlib.Path) -> typing.Iterator[str]:
        """Yield the Markdown headings outside fenced code blocks.

        Parameters
        ----------
        page : pathlib.Path
            Page to inspect.

        Yields
        ------
        str
            Heading line.
        """
        for line in cls.outside_fences(page):
            if line.startswith("#"):
                yield line

    @classmethod
    def callout_lines(cls, page: pathlib.Path) -> typing.Iterator[str]:
        """Yield the directive lines outside fenced code blocks.

        Parameters
        ----------
        page : pathlib.Path
            Page to inspect.

        Yields
        ------
        str
            Directive line.
        """
        for line in cls.outside_fences(page):
            match = cls.CALLOUT.match(line)
            if match is not None:
                yield line

    @classmethod
    def has_emoji(cls, text: str) -> bool:
        """Return whether a string contains an emoji.

        Parameters
        ----------
        text : str
            Text to inspect.

        Returns
        -------
        bool
            Whether the text contains an emoji.
        """
        return cls.EMOJI.search(text) is not None

    def test_every_page_opens_with_tldr(self) -> None:
        """Require a tl;dr block immediately after every reader-facing page title."""
        for page in self.pages():
            assert self.first_block(page) == self.TLDR, page

    def test_only_five_callout_types(self) -> None:
        """Require every callout to use one of the five approved types."""
        for page in self.pages():
            for line in self.callout_lines(page):
                match = self.CALLOUT.match(line)
                assert match is not None, (page, line)
                name = match.group("name")
                title = match.group("title")
                assert name not in self.FORBIDDEN_CALLOUTS, (page, line)
                if name in self.IGNORED_DIRECTIVES:
                    continue
                assert name in self.ALLOWED_DIRECTIVES, (page, line)
                if name == "admonition":
                    assert title in self.ALLOWED_ADMONITIONS, (page, line)

    def test_card_emoji_is_all_or_nothing(self) -> None:
        """Require every card in a grid to carry an emoji, or none to."""
        titles: list[str] = []
        for page in self.pages():
            for line in self.outside_fences(page):
                match = self.CARD.match(line)
                if match is not None:
                    titles.append(match.group("title"))
        if not titles:
            return
        decorated = [self.has_emoji(title) for title in titles]
        assert all(decorated) or not any(decorated), titles

    def test_no_emoji_in_headings(self) -> None:
        """Require headings to stay emoji-free so their anchors remain predictable."""
        for page in self.pages():
            for heading in self.headings(page):
                assert not self.has_emoji(heading), (page, heading)

    def test_diagrams_have_accessibility_metadata(self) -> None:
        """Require every diagram to carry alt text, a title, and a description."""
        for page in self.pages():
            for match in self.MERMAID.finditer(page.read_text(encoding="utf-8")):
                body = match.group("body")
                assert ":alt:" in body, page
                assert "accTitle:" in body, page
                assert "accDescr:" in body, page
