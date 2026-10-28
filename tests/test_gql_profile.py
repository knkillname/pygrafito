# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Verify the published GQL profile contract."""

import re
import typing
from pathlib import Path

from tests.conformance.runner import Corpus


class TestGqlProfile:
    """Check that the profile page stays complete and internally consistent."""

    ROOT: typing.ClassVar[Path] = Path(__file__).resolve().parents[1]
    PROFILE: typing.ClassVar[Path] = ROOT / "docs" / "reference" / "gql-profile.md"
    INDEX: typing.ClassVar[Path] = ROOT / "docs" / "index.md"
    CORPUS: typing.ClassVar[Path] = ROOT / "tests" / "conformance" / "cases.json"
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
    FEATURE_OVERRIDES: typing.ClassVar[dict[str, str]] = {
        "`-->`, `<--`, `--` for `->`, `<-`, `-`": "edge-direction-aliases",
        "`:A:B` for `:A&B`": "label-conjunction-alias",
        "`{n,m}` quantifier": "quantifier",
        "Legacy `*n..m` quantifier": "legacy-quantifier",
    }

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

    def test_every_corpus_feature_exists_in_the_matrix(self) -> None:
        """Require every corpus case to name a matrix feature."""
        features = self._features()
        for case in Corpus(self.CORPUS).cases:
            assert case.feature in features, f"{case.name} names {case.feature!r}"

    def test_every_supported_row_has_a_case(self) -> None:
        """Require at least one corpus case for each supported row."""
        covered = {case.feature for case in Corpus(self.CORPUS).cases}
        missing = {
            feature for feature, status in self._features().items() if status == "supported"
        } - covered
        assert not missing, f"supported rows without a case: {sorted(missing)}"

    def test_gated_cases_expect_a_follow_up_change(self) -> None:
        """Require a gated case to name the change that implements it."""
        for case in Corpus(self.CORPUS).cases:
            if not case.gated:
                continue
            expected = case.expect.get("error")
            assert isinstance(expected, dict), case.name
            fragment = str(expected.get("contains", ""))
            assert "add-gql-" in fragment or "harden-for-1.0" in fragment, case.name

    def test_deferred_rows_have_no_cases(self) -> None:
        """Require deferred and out-of-profile rows to carry no corpus cases."""
        features = self._features()
        for case in Corpus(self.CORPUS).cases:
            assert features[case.feature] not in {"deferred", "out of profile"}, case.name

    @classmethod
    def _features(cls) -> dict[str, str]:
        """Return the matrix feature id and status pairs.

        Returns
        -------
        dict[str, str]
            Feature id to status.
        """
        features: dict[str, str] = {}
        for row in cls._matrix_rows(cls.PROFILE.read_text(encoding="utf-8")):
            feature = cls._feature_id(row[0])
            assert feature not in features, f"duplicate feature id {feature!r}"
            features[feature] = row[2]
        return features

    @classmethod
    def _feature_id(cls, label: str) -> str:
        """Derive the stable feature id from a matrix label.

        Parameters
        ----------
        label : str
            First cell of one matrix row.

        Returns
        -------
        str
            Kebab-case feature id.
        """
        override = cls.FEATURE_OVERRIDES.get(label)
        if override is not None:
            return override
        return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")

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
