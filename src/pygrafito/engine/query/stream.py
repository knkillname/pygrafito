# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Pull-based row delivery for statements that can stop early."""

import contextlib
import dataclasses
import typing
from collections.abc import Iterator

from pygrafito.engine.query.ast import PathPattern
from pygrafito.engine.query.semantic import (
    Analysis,
    FilterStage,
    LetStage,
    MatchStage,
    NextBoundary,
    OptionalMatchStage,
    UnwindStage,
    WithStage,
    WriteStage,
    YieldStage,
)


class RowStream[T]:
    """Iterate rows and close the producing generator when done.

    Parameters
    ----------
    source : Iterator[T]
        Rows to deliver.
    """

    def __init__(self, source: Iterator[T]) -> None:
        self._source = source

    def __iter__(self) -> typing.Self:
        """Return this stream as its own iterator.

        Returns
        -------
        typing.Self
            The stream itself.
        """
        return self

    def __next__(self) -> T:
        """Return the next row.

        Returns
        -------
        T
            Next produced row.

        Raises
        ------
        StopIteration
            When the source is exhausted.
        """
        return next(self._source)

    def close(self) -> None:
        """Close the source and release its expansion state."""
        close = getattr(self._source, "close", None)
        if close is None:
            return
        with contextlib.suppress(Exception):
            close()

    def __enter__(self) -> typing.Self:
        """Enter the stream context.

        Returns
        -------
        typing.Self
            The stream itself.
        """
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        """Close the stream when the context ends.

        Parameters
        ----------
        exc_type : object
            Exception type, or ``None``.
        exc : object
            Exception instance, or ``None``.
        traceback : object
            Traceback, or ``None``.
        """
        self.close()


class Demand:
    """Track the rows a final ``SKIP`` and ``LIMIT`` still need.

    Parameters
    ----------
    skip : int | None
        Rows to discard before the first result row, or ``None``.
    limit : int | None
        Result rows still allowed, or ``None`` for no limit.
    """

    def __init__(self, skip: int | None = None, limit: int | None = None) -> None:
        self._skip = 0 if skip is None else skip
        self._remaining = limit

    @property
    def remaining(self) -> int | None:
        """Return the result rows still needed.

        Returns
        -------
        int | None
            Rows still allowed, or ``None`` for no limit.
        """
        return self._remaining

    def wants(self) -> bool:
        """Report whether another input row can still produce a result.

        Returns
        -------
        bool
            ``True`` while the limit is not exhausted.
        """
        return self._remaining is None or self._remaining > 0

    def accept(self) -> bool:
        """Consume one input row and report whether it becomes a result.

        Returns
        -------
        bool
            ``True`` for a result row, ``False`` for a skipped row.
        """
        if self._skip:
            self._skip -= 1
            return False
        if self._remaining is not None:
            self._remaining -= 1
        return True


@dataclasses.dataclass(frozen=True, slots=True)
class PlanShape:
    """Classify a statement for the early-stopping execution path.

    Parameters
    ----------
    analysis : Analysis
        Static analysis of one linear statement.
    """

    analysis: Analysis

    @property
    def open_pattern(self) -> bool:
        """Report whether any match stage contains an open position.

        Returns
        -------
        bool
            ``True`` when a quantified position has no upper bound.
        """
        return any(
            self._is_open(pattern)
            for operation in self.analysis.operations
            if isinstance(operation, MatchStage | OptionalMatchStage)
            for pattern in operation.patterns
        )

    @property
    def streamable(self) -> bool:
        """Report whether the final result can stop before every row exists.

        Returns
        -------
        bool
            ``True`` when a plain read projection can consume rows lazily.
        """
        analysis = self.analysis
        if analysis.return_clause is None:
            return False
        if analysis.has_aggregates or analysis.grouping_explicit or analysis.sorts:
            return False
        if analysis.return_clause.distinct:
            return False
        return self.streamable_rows

    @property
    def streamable_rows(self) -> bool:
        """Report whether the read stages can deliver rows lazily.

        Returns
        -------
        bool
            ``True`` when no stage needs every input row first.
        """
        analysis = self.analysis
        if analysis.is_write or analysis.finish:
            return False
        for operation in analysis.operations:
            if isinstance(operation, NextBoundary | WriteStage):
                return False
            if not isinstance(
                operation,
                MatchStage
                | OptionalMatchStage
                | UnwindStage
                | WithStage
                | FilterStage
                | LetStage
                | YieldStage,
            ):
                return False
            if isinstance(operation, WithStage) and self._with_materializes(operation):
                return False
        return True

    @staticmethod
    def _with_materializes(stage: WithStage) -> bool:
        """Report whether a ``WITH`` stage needs every input row first.

        Parameters
        ----------
        stage : WithStage
            Stage to inspect.

        Returns
        -------
        bool
            ``True`` for aggregation, distinctness, ordering, or pagination.
        """
        return (
            stage.has_aggregates
            or stage.grouping_explicit
            or stage.distinct
            or bool(stage.order_by)
            or stage.skip is not None
            or stage.limit is not None
            or stage.segment_return
        )

    @staticmethod
    def _is_open(pattern: PathPattern) -> bool:
        """Report whether a path pattern has an open position.

        Parameters
        ----------
        pattern : PathPattern
            Pattern to inspect.

        Returns
        -------
        bool
            ``True`` when a quantified position has no upper bound.
        """
        return pattern.has_open_position()


__all__ = ["Demand", "PlanShape", "RowStream"]
