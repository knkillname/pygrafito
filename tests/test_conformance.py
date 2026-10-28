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

    def test_rejection_case_runs_against_the_boundary(self) -> None:
        """Require a correctly shaped rejection case to pass."""
        corpus = self.corpus()
        case = dataclasses.replace(
            corpus.cases[0],
            query="SELECT 1",
            tags=("rejection",),
            expect={
                "error": {
                    "type": "QuerySemanticError",
                    "contains": "SELECT is not supported: use MATCH ... RETURN",
                }
            },
        )
        corpus.check(case)

    def test_rejection_case_must_expect_an_error(self) -> None:
        """Require a rejection case to declare an expected error."""
        corpus = self.corpus()
        case = dataclasses.replace(
            corpus.cases[0],
            query="SELECT 1",
            tags=("rejection",),
            expect={"rows": []},
        )
        with pytest.raises(AssertionError, match="must expect an error"):
            corpus.check(case)

    def test_rejection_case_must_use_the_boundary_shape(self) -> None:
        """Require a rejection case to assert the boundary message shape."""
        corpus = self.corpus()
        case = dataclasses.replace(
            corpus.cases[0],
            query="SELECT 1",
            tags=("rejection",),
            expect={"error": {"type": "QuerySemanticError", "contains": "SELECT"}},
        )
        with pytest.raises(AssertionError, match="is not supported"):
            corpus.check(case)

    def test_rejection_case_fails_when_the_statement_executes(self) -> None:
        """Require a rejection case to fail if no boundary error is raised."""
        corpus = self.corpus()
        case = dataclasses.replace(
            corpus.cases[0],
            query="MATCH (n:Program) RETURN n.designation AS name ORDER BY name",
            tags=("rejection",),
            expect={
                "error": {
                    "type": "QuerySemanticError",
                    "contains": "SELECT is not supported: use MATCH ... RETURN",
                }
            },
        )
        with pytest.raises(AssertionError, match="expected an error"):
            corpus.check(case)
