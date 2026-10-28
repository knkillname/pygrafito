# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Count the work of one query execution and enforce its budget."""

import time
import typing
from collections.abc import Callable

from pygrafito.model import QueryBudget, QueryBudgetExceededError


class BudgetTracker:
    """Accumulate per-execution counters and raise when a limit is reached.

    Parameters
    ----------
    budget : QueryBudget
        Limits to enforce for one execution.
    clock : Callable[[], float], optional
        Monotonic clock, by default ``time.monotonic``. Tests may inject one.
    """

    CHECK_INTERVAL: typing.ClassVar[int] = 1024
    EXPANSIONS: typing.ClassVar[str] = "expansions"
    ROWS: typing.ClassVar[str] = "rows"
    SECONDS: typing.ClassVar[str] = "seconds"

    def __init__(
        self,
        budget: QueryBudget,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._budget = budget
        self._clock = clock
        self._started = clock()
        self._expansions = 0
        self._rows = 0

    @property
    def expansions(self) -> int:
        """Return the relationship expansions counted so far.

        Returns
        -------
        int
            Number of counted expansions.
        """
        return self._expansions

    @property
    def rows(self) -> int:
        """Return the intermediate rows counted so far.

        Returns
        -------
        int
            Number of counted rows.
        """
        return self._rows

    def consume_expansions(self, count: int = 1) -> None:
        """Count relationship expansions and enforce the expansion limit.

        Parameters
        ----------
        count : int, optional
            Expansions to add, by default one.

        Raises
        ------
        QueryBudgetExceededError
            If the expansion or wall-clock limit is reached.
        """
        self._expansions += count
        limit = self._budget.max_expansions
        if limit is not None and self._expansions > limit:
            raise QueryBudgetExceededError(self.EXPANSIONS, limit)
        if self._crosses_interval(self._expansions, count):
            self.check_time()

    def consume_rows(self, count: int = 1) -> None:
        """Count intermediate rows and enforce the row limit.

        Parameters
        ----------
        count : int, optional
            Rows to add, by default one.

        Raises
        ------
        QueryBudgetExceededError
            If the row or wall-clock limit is reached.
        """
        self._rows += count
        limit = self._budget.max_rows
        if limit is not None and self._rows > limit:
            raise QueryBudgetExceededError(self.ROWS, limit)
        if self._crosses_interval(self._rows, count):
            self.check_time()

    def check_time(self) -> None:
        """Enforce the optional wall-clock limit.

        Raises
        ------
        QueryBudgetExceededError
            If the elapsed time reached the configured limit.
        """
        limit = self._budget.max_seconds
        if limit is None:
            return
        if self._clock() - self._started >= limit:
            raise QueryBudgetExceededError(self.SECONDS, limit)

    @classmethod
    def _crosses_interval(cls, total: int, count: int) -> bool:
        """Report whether a counter update crossed a clock-check boundary.

        Parameters
        ----------
        total : int
            Counter value after the update.
        count : int
            Amount the counter grew by.

        Returns
        -------
        bool
            ``True`` when the update spans a multiple of the check interval.
        """
        if count >= cls.CHECK_INTERVAL:
            return True
        return total % cls.CHECK_INTERVAL < count


__all__ = ["BudgetTracker"]
