# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Property tests for row and file imports."""

import pathlib
import tempfile
import typing

import hypothesis
import hypothesis.strategies
import pytest

from pygrafito import Graph, PygrafitoError

STATEMENT = "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})"
FAILING_STATEMENT = (
    "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) SET n.bad = row.bad"
)
ALPHABET = "abcXYZ019_\"'\\\n\t$.[]{}: ,éΩ☃"


class TestImportProperties:
    """Verify batching, atomicity, and total input errors."""

    DESIGNATION: typing.ClassVar[hypothesis.strategies.SearchStrategy[str]] = (
        hypothesis.strategies.text(alphabet=ALPHABET, min_size=1, max_size=10)
    )
    ROWS: typing.ClassVar[hypothesis.strategies.SearchStrategy[list[dict[str, str]]]] = (
        hypothesis.strategies.lists(
            hypothesis.strategies.fixed_dictionaries({"designation": DESIGNATION}),
            max_size=8,
        )
    )

    @hypothesis.given(
        rows=ROWS,
        batch_size=hypothesis.strategies.integers(min_value=1, max_value=5),
    )
    def test_in_memory_import_matches_rows(
        self,
        rows: list[dict[str, str]],
        batch_size: int,
    ) -> None:
        """Report every row and batch and create each distinct designation once."""
        with Graph.open(":memory:") as graph:
            summary = graph.import_rows(STATEMENT, rows, batch_size=batch_size)
            found = {
                str(node["designation"])
                for node in graph.find_nodes("Program")
                if "designation" in node
            }
        assert summary.rows == len(rows)
        expected_batches = (len(rows) + batch_size - 1) // batch_size if rows else 0
        assert summary.batches == expected_batches
        assert summary.mutations.created_nodes == len({row["designation"] for row in rows})
        assert found == {row["designation"] for row in rows}

    @classmethod
    def row(cls, designation: str) -> dict[str, object]:
        """Build one valid import row.

        Parameters
        ----------
        designation : str
            Program designation.

        Returns
        -------
        dict[str, object]
            Row mapping.
        """
        return {"designation": designation}

    @classmethod
    def assert_failure(
        cls,
        prefix: list[str],
        suffix: list[str],
        *,
        atomic: bool,
    ) -> None:
        """Run one failing import and check the rollback boundary."""
        rows: list[dict[str, object]] = [
            *(cls.row(designation) for designation in prefix),
            {"designation": "Bad", "bad": {"nested": 1}},
            *(cls.row(designation) for designation in suffix),
        ]
        with Graph.open(":memory:") as graph:
            with pytest.raises(PygrafitoError) as caught:
                graph.import_rows(FAILING_STATEMENT, rows, batch_size=1, atomic=atomic)
            found = {
                str(node["designation"])
                for node in graph.find_nodes("Program")
                if "designation" in node
            }
        notes = getattr(caught.value, "__notes__", [])
        row = len(prefix) + 1
        assert any(f"row {row}" in note and f"batch {row}" in note for note in notes)
        if atomic:
            assert found == set()
        else:
            assert found == set(prefix)

    @hypothesis.given(
        prefix=hypothesis.strategies.lists(
            hypothesis.strategies.text(alphabet=ALPHABET, min_size=1, max_size=10),
            max_size=5,
        ),
        suffix=hypothesis.strategies.lists(
            hypothesis.strategies.text(alphabet=ALPHABET, min_size=1, max_size=10),
            max_size=5,
        ),
    )
    def test_atomic_failure_rolls_back_every_batch(
        self,
        prefix: list[str],
        suffix: list[str],
    ) -> None:
        """Leave no rows when an atomic import fails."""
        self.assert_failure(prefix, suffix, atomic=True)

    @hypothesis.given(
        prefix=hypothesis.strategies.lists(
            hypothesis.strategies.text(alphabet=ALPHABET, min_size=1, max_size=10),
            max_size=5,
        ),
        suffix=hypothesis.strategies.lists(
            hypothesis.strategies.text(alphabet=ALPHABET, min_size=1, max_size=10),
            max_size=5,
        ),
    )
    def test_non_atomic_failure_keeps_committed_prefix(
        self,
        prefix: list[str],
        suffix: list[str],
    ) -> None:
        """Keep the batches that committed before a non-atomic failure."""
        self.assert_failure(prefix, suffix, atomic=False)

    @hypothesis.given(text=hypothesis.strategies.text(alphabet=ALPHABET, max_size=120))
    def test_arbitrary_csv_is_a_library_error(self, text: str) -> None:
        """Return a summary or raise a library error for arbitrary CSV."""
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "rows.csv"
            path.write_text(text, encoding="utf-8")
            with Graph.open(":memory:") as graph:
                try:
                    graph.import_file(path, STATEMENT, format="csv")
                except PygrafitoError:
                    return

    @hypothesis.given(text=hypothesis.strategies.text(alphabet=ALPHABET, max_size=120))
    def test_arbitrary_jsonl_is_a_library_error(self, text: str) -> None:
        """Return a summary or raise a library error for arbitrary JSONL."""
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "rows.jsonl"
            path.write_text(text, encoding="utf-8")
            with Graph.open(":memory:") as graph:
                try:
                    graph.import_file(path, STATEMENT, format="jsonl")
                except PygrafitoError:
                    return
