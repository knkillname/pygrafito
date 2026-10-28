# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Verify the published GQL profile contract."""

import importlib
import re
import typing
from pathlib import Path

from tests.conformance.runner import Corpus


class TestGqlProfile:
    """Check that the profile page stays complete and internally consistent."""

    ROOT: typing.ClassVar[Path] = Path(__file__).resolve().parents[1]
    PROFILE: typing.ClassVar[Path] = ROOT / "docs" / "reference" / "gql-profile.md"
    REFERENCE: typing.ClassVar[Path] = ROOT / "docs" / "reference" / "query-language.md"
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
    INVENTORY_HEADER: typing.ClassVar[str] = "| Construct | Tier | Status |"
    SURFACE_TESTS: typing.ClassVar[dict[str, str]] = {
        "TestOutOfProfileSurface": "tests.engine.query.test_out_of_profile",
    }
    GATED_PROSE: typing.ClassVar[tuple[str, ...]] = (
        "## gated constructs",
        "gated for 1.0",
        "when they land",
        "once open quantifiers land",
        "remains gated",
        "remain gated",
    )
    FEATURE_OVERRIDES: typing.ClassVar[dict[str, str]] = {
        "-->, <--, -- for ->, <-, -": "edge-direction-aliases",
        ":A:B for :A&B": "label-conjunction-alias",
        "{n,m} quantifier": "quantifier",
        "Legacy *n..m quantifier": "legacy-quantifier",
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

    def test_rejection_cases_name_out_of_profile_rows(self) -> None:
        """Require every rejection case to document an out-of-profile row."""
        features = self._features()
        for case in Corpus(self.CORPUS).cases:
            if not case.rejection:
                continue
            assert features[case.feature] == "out of profile", case.name

    def test_release_gate(self) -> None:
        """Require the profile to satisfy every release-gate check."""
        problems = self._gate_problems(
            self.PROFILE.read_text(encoding="utf-8"),
            self.REFERENCE.read_text(encoding="utf-8"),
        )
        assert not problems, problems

    def test_gate_detects_a_gated_row(self) -> None:
        """Require the gate to fail when a row becomes gated."""
        text = self.PROFILE.read_text(encoding="utf-8")
        broken = text.replace(
            "| `MATCH` and `OPTIONAL MATCH` | Canonical GQL | supported |",
            "| `MATCH` and `OPTIONAL MATCH` | Canonical GQL | gated |",
            1,
        )
        problems = self._gate_problems(broken, self.REFERENCE.read_text(encoding="utf-8"))
        assert any("gated" in problem for problem in problems)

    def test_gate_detects_missing_evidence(self) -> None:
        """Require the gate to fail when a row has no evidence."""
        text = self.PROFILE.read_text(encoding="utf-8")
        broken = text.replace(
            "| None | match-program-designations |",
            "| None | — |",
            1,
        )
        problems = self._gate_problems(broken, self.REFERENCE.read_text(encoding="utf-8"))
        assert any("evidence" in problem for problem in problems)

    def test_gate_detects_unresolvable_evidence(self) -> None:
        """Require the gate to fail when evidence names nothing."""
        text = self.PROFILE.read_text(encoding="utf-8")
        broken = text.replace(
            "rejection:select-statement-is-rejected",
            "rejection:select-that-does-not-exist",
            1,
        )
        problems = self._gate_problems(broken, self.REFERENCE.read_text(encoding="utf-8"))
        assert any("select-that-does-not-exist" in problem for problem in problems)

    def test_gate_detects_inventory_drift(self) -> None:
        """Require the gate to fail when inventory status disagrees."""
        text = self.PROFILE.read_text(encoding="utf-8")
        broken = text.replace(
            "| `SELECT` | Out of profile | out of profile | `SELECT` |",
            "| `SELECT` | Out of profile | supported | `SELECT` |",
            1,
        )
        problems = self._gate_problems(broken, self.REFERENCE.read_text(encoding="utf-8"))
        assert any("inventory" in problem for problem in problems)

    def test_gate_detects_gated_prose(self) -> None:
        """Require the gate to fail when the reference describes a gated surface."""
        reference = self.REFERENCE.read_text(encoding="utf-8") + "\n## Gated constructs\n"
        problems = self._gate_problems(
            self.PROFILE.read_text(encoding="utf-8"),
            reference,
        )
        assert any("gated" in problem for problem in problems)

    @classmethod
    def _gate_problems(cls, profile_text: str, reference_text: str) -> list[str]:
        """Return the release-gate problems in a profile and reference pair.

        Parameters
        ----------
        profile_text : str
            Profile page contents.
        reference_text : str
            Query-language reference contents.

        Returns
        -------
        list[str]
            One description per failed gate check.
        """
        problems: list[str] = []
        rows = cls._matrix_rows(profile_text)
        features = {cls._feature_id(row[0]): row[2] for row in rows}
        evidence = {cls._feature_id(row[0]): row[5] for row in rows}
        corpus = Corpus(cls.CORPUS)
        case_names = {case.name for case in corpus.cases}
        rejection_names = {case.name for case in corpus.cases if case.rejection}

        for feature, status in features.items():
            if status in {"gated", "deferred"}:
                problems.append(f"{feature} is {status}")
            value = evidence.get(feature, "")
            if not value:
                problems.append(f"{feature} has no evidence")
                continue
            tokens = [token.strip() for token in value.split(",")]
            if status == "supported":
                missing = [token for token in tokens if token not in case_names]
                if missing:
                    problems.append(f"{feature} evidence is unresolved: {missing}")
                continue
            if status == "out of profile":
                unresolved = [
                    token
                    for token in tokens
                    if cls._resolve_evidence(token, rejection_names) is not None
                ]
                if unresolved:
                    problems.append(f"{feature} evidence is unresolved: {unresolved}")

        for problem in cls._inventory_problems(profile_text, features):
            problems.append(problem)

        lowered = reference_text.lower()
        for phrase in cls.GATED_PROSE:
            if phrase in lowered:
                problems.append(f"the reference still says {phrase!r}")

        return problems

    @classmethod
    def _inventory_problems(
        cls,
        profile_text: str,
        features: dict[str, str],
    ) -> list[str]:
        """Return inventory rows whose status disagrees with the matrix.

        Parameters
        ----------
        profile_text : str
            Profile page contents.
        features : dict[str, str]
            Matrix feature id to status.

        Returns
        -------
        list[str]
            One description per drifted inventory row.
        """
        problems: list[str] = []
        rows = cls._table_rows(profile_text, cls.INVENTORY_HEADER)
        for row in rows:
            status = row[2]
            if status not in {"supported", "out of profile"}:
                continue
            owners = [
                cls._feature_id(cls._normalize(part))
                for part in row[3].split(";")
                if cls._feature_id(cls._normalize(part)) in features
            ]
            if not owners:
                problems.append(f"inventory row {row[0]!r} has no matrix owner")
                continue
            for owner in owners:
                if features[owner] != status:
                    problems.append(
                        f"inventory says {status} for {owner}, matrix says {features[owner]}"
                    )
        return problems

    @classmethod
    def _resolve_evidence(cls, token: str, rejection_names: set[str]) -> str | None:
        """Resolve one out-of-profile evidence token.

        Parameters
        ----------
        token : str
            Evidence token, such as ``rejection:<case>`` or ``test:<Class>::<method>``.
        rejection_names : set[str]
            Corpus case names tagged as rejections.

        Returns
        -------
        str | None
            The unresolved token, or ``None`` when it resolves.
        """
        if token == "rejected forms":
            return None
        if token.startswith("rejection:"):
            return None if token.split(":", 1)[1] in rejection_names else token
        if token.startswith("test:"):
            parts = token.split(":", 1)[1].split("::")
            module_name = cls.SURFACE_TESTS.get(parts[0]) if parts else None
            if module_name is None:
                return token
            target: object = importlib.import_module(module_name)
            for part in parts:
                target = getattr(target, part, None)
                if target is None:
                    return token
            return None
        return token

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
        override = cls.FEATURE_OVERRIDES.get(label.replace("`", "").strip())
        if override is not None:
            return override
        return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")

    @classmethod
    def _normalize(cls, name: str) -> str:
        """Strip table formatting from a matrix or inventory label.

        Parameters
        ----------
        name : str
            Cell contents.

        Returns
        -------
        str
            Label without surrounding backticks or whitespace.
        """
        return name.replace("`", "").strip()

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
        return cls._table_rows(text, cls.MATRIX_HEADER)

    @classmethod
    def _table_rows(cls, text: str, header: str) -> list[list[str]]:
        """Return the rows of one profile table.

        Parameters
        ----------
        text : str
            Profile page contents.
        header : str
            Opening text of the table header.

        Returns
        -------
        list[list[str]]
            Cell values for each row, excluding the header and separator.
        """
        lines = text.splitlines()
        start = next(
            (index for index, line in enumerate(lines) if line.startswith(header)),
            None,
        )
        assert start is not None, f"table header is missing: {header}"
        rows: list[list[str]] = []
        for line in lines[start + 1 :]:
            if not line.startswith("|"):
                break
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(cell.startswith("---") or cell == "" for cell in cells):
                continue
            rows.append(cells)
        return rows
