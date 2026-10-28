# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Run every case in the GQL conformance corpus."""

import dataclasses
import pathlib
import typing

import pytest

from tests.conformance.runner import Case, Corpus


class TestConformanceCorpus:
    """Execute the corpus against the current frontend."""

    DIRECTORY: typing.ClassVar[pathlib.Path] = pathlib.Path(__file__).resolve().parent / (
        "conformance"
    )
    CASES_PATH: typing.ClassVar[pathlib.Path] = DIRECTORY / "cases.json"

    @classmethod
    def corpus(cls) -> Corpus:
        """Load the corpus document.

        Returns
        -------
        Corpus
            Loaded corpus.
        """
        return Corpus(cls.CASES_PATH)

    def test_every_fixture_name_is_unique(self) -> None:
        """Require every fixture name to be unique."""
        corpus = self.corpus()
        assert len(corpus.fixtures) == len(set(corpus.fixtures))

    @pytest.mark.parametrize(
        "case",
        Corpus(CASES_PATH).cases,
        ids=lambda case: case.name,
    )
    def test_case(self, case: Case) -> None:
        """Execute one corpus case.

        Parameters
        ----------
        case : Case
            Case supplied by the parametrization.
        """
        self.corpus().check(case)

    def test_mismatch_names_the_case_and_feature(self) -> None:
        """Require a mismatch to report the case name and feature id."""
        corpus = self.corpus()
        case = dataclasses.replace(
            corpus.cases[0],
            expect={"rows": [{"name": "Clu"}]},
        )
        with pytest.raises(AssertionError, match=r"match-program-designations \[match"):
            corpus.check(case)
