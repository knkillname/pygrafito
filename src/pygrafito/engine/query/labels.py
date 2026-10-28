# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Label-expression helpers shared by the parser and the pattern engine."""

from collections.abc import Iterable

from pygrafito.engine.query.ast import (
    LabelAnd,
    LabelExpression,
    LabelName,
    LabelNot,
    LabelWildcard,
)


class LabelExpressions:
    """Evaluate and normalize label expressions."""

    @classmethod
    def conjunction(cls, expression: LabelExpression | None) -> tuple[str, ...] | None:
        """Return the labels of a pure conjunction.

        Parameters
        ----------
        expression : LabelExpression | None
            Parsed label expression.

        Returns
        -------
        tuple[str, ...] | None
            Sorted label names when the expression is only names joined by
            ``&``; ``None`` otherwise.
        """
        names = cls._conjunction_names(expression)
        return None if names is None else tuple(names)

    @classmethod
    def matches(cls, expression: LabelExpression, labels: Iterable[str]) -> bool:
        """Evaluate one label expression against an element's labels.

        Parameters
        ----------
        expression : LabelExpression
            Expression to evaluate.
        labels : Iterable[str]
            Labels carried by the element.

        Returns
        -------
        bool
            ``True`` when the expression matches.
        """
        present = frozenset(labels)
        return cls._matches(expression, present)

    @classmethod
    def _conjunction_names(cls, expression: LabelExpression | None) -> list[str] | None:
        """Collect the names of a pure conjunction.

        Parameters
        ----------
        expression : LabelExpression | None
            Expression to inspect.

        Returns
        -------
        list[str] | None
            Names in source order, or ``None`` for any other shape.
        """
        if expression is None:
            return []
        if isinstance(expression, LabelName):
            return [expression.name]
        if isinstance(expression, LabelAnd):
            left = cls._conjunction_names(expression.left)
            right = cls._conjunction_names(expression.right)
            if left is None or right is None:
                return None
            return left + right
        return None

    @classmethod
    def _matches(cls, expression: LabelExpression, present: frozenset[str]) -> bool:
        """Evaluate one expression against a label set.

        Parameters
        ----------
        expression : LabelExpression
            Expression to evaluate.
        present : frozenset[str]
            Labels carried by the element.

        Returns
        -------
        bool
            ``True`` when the expression matches.
        """
        if isinstance(expression, LabelName):
            return expression.name in present
        if isinstance(expression, LabelWildcard):
            return True
        if isinstance(expression, LabelNot):
            return not cls._matches(expression.operand, present)
        if isinstance(expression, LabelAnd):
            return cls._matches(expression.left, present) and cls._matches(
                expression.right, present
            )
        return cls._matches(expression.left, present) or cls._matches(expression.right, present)
