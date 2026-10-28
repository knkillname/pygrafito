# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Verify the published GQL profile contract."""

import typing
from pathlib import Path


class TestGqlProfile:
    """Check that the profile page stays complete and internally consistent."""

    ROOT: typing.ClassVar[Path] = Path(__file__).resolve().parents[1]
    PROFILE: typing.ClassVar[Path] = ROOT / "docs" / "reference" / "gql-profile.md"
    INDEX: typing.ClassVar[Path] = ROOT / "docs" / "index.md"
    TIERS: typing.ClassVar[tuple[str, ...]] = (
        "Canonical GQL",
        "Synthetic alias",
        "Compatibility construct",
        "pygrafito extension",
        "Out of profile",
    )
    STATUSES: typing.ClassVar[frozenset[str]] = frozenset(
        {"supported", "gated", "deferred", "out of profile"}
    )
    MATRIX_HEADER: typing.ClassVar[str] = "| Feature | Tier | Status |"

    def test_profile_page_exists_and_is_in_reference_navigation(self) -> None:
        """Require the profile page and its reference toctree entry."""
        assert self.PROFILE.exists()
        index = self.INDEX.read_text(encoding="utf-8")
        assert "reference/gql-profile" in index

    def test_profile_lists_every_tier(self) -> None:
        """Require the five classification tiers on the profile page."""
        text = self.PROFILE.read_text(encoding="utf-8")
        for tier in self.TIERS:
            assert tier in text, tier

    def test_conformance_matrix_uses_only_profile_statuses(self) -> None:
        """Require the matrix status column to use the four declared statuses."""
        rows = self._matrix_rows(self.PROFILE.read_text(encoding="utf-8"))
        assert rows
        statuses = {row[2] for row in rows}
        assert statuses
        assert statuses <= self.STATUSES, statuses - self.STATUSES

    def test_matrix_names_every_tier(self) -> None:
        """Require the matrix to cover each tier."""
        rows = self._matrix_rows(self.PROFILE.read_text(encoding="utf-8"))
        tiers = {row[1] for row in rows}
        assert set(self.TIERS) <= tiers

    @classmethod
    def _matrix_rows(cls, text: str) -> list[list[str]]:
        """Return the conformance matrix rows.

        Parameters
        ----------
        text : str
            Profile page contents.

        Returns
        -------
        list[list[str]]
            Cell values for each matrix row, excluding the header and separator.
        """
        lines = text.splitlines()
        start = next(
            (index for index, line in enumerate(lines) if line.startswith(cls.MATRIX_HEADER)),
            None,
        )
        assert start is not None, "conformance matrix header is missing"
        rows: list[list[str]] = []
        for line in lines[start + 1 :]:
            if not line.startswith("|"):
                break
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(cell.startswith("---") or cell == "" for cell in cells):
                continue
            rows.append(cells)
        return rows
