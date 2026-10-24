# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Materialized query results and immutable result rows."""

import dataclasses
import typing
from collections.abc import Iterator, Mapping

from pygrafito.engine.query.values import QueryValue


@dataclasses.dataclass(frozen=True, slots=True)
class Row(Mapping[str, QueryValue]):
    """One immutable result row with lookup by column name.

    Parameters
    ----------
    columns : tuple[str, ...]
        Ordered column names shared by the result.
    row_values : tuple[QueryValue, ...]
        Projected values in column order.
    """

    columns: tuple[str, ...]
    row_values: tuple[QueryValue, ...]

    def __post_init__(self) -> None:
        """Materialize the row columns and values as tuples."""
        object.__setattr__(self, "columns", tuple(self.columns))
        object.__setattr__(self, "row_values", tuple(self.row_values))
        if len(self.columns) != len(self.row_values):
            message = "a result row must have exactly one value per column"
            raise ValueError(message)

    @typing.override
    def __getitem__(self, key: str) -> QueryValue:
        """Return the value of one named column.

        Parameters
        ----------
        key : str
            Column name.

        Returns
        -------
        QueryValue
            Projected value.

        Raises
        ------
        KeyError
            If the column does not exist.
        """
        try:
            index = self.columns.index(key)
        except ValueError as error:
            raise KeyError(key) from error
        return self.row_values[index]

    @typing.override
    def __iter__(self) -> Iterator[str]:
        """Iterate over column names.

        Returns
        -------
        Iterator[str]
            Column names in projection order.
        """
        return iter(self.columns)

    @typing.override
    def __len__(self) -> int:
        """Return the number of columns.

        Returns
        -------
        int
            Number of columns.
        """
        return len(self.columns)


@dataclasses.dataclass(frozen=True, slots=True)
class MutationSummary:
    """Counts of the changes applied by one statement.

    Parameters
    ----------
    created_nodes : int, optional
        Nodes created, by default zero.
    created_relationships : int, optional
        Relationships created, by default zero.
    deleted_nodes : int, optional
        Nodes deleted, by default zero.
    deleted_relationships : int, optional
        Relationships deleted, by default zero.
    properties_set : int, optional
        Property assignments applied, by default zero.
    properties_removed : int, optional
        Property removals applied, by default zero.
    labels_added : int, optional
        Label additions applied, by default zero.
    labels_removed : int, optional
        Label removals applied, by default zero.
    """

    created_nodes: int = 0
    created_relationships: int = 0
    deleted_nodes: int = 0
    deleted_relationships: int = 0
    properties_set: int = 0
    properties_removed: int = 0
    labels_added: int = 0
    labels_removed: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class QueryResult:
    """A materialized, immutable query result.

    Parameters
    ----------
    columns : tuple[str, ...]
        Ordered column names.
    rows : Sequence[Row]
        Result rows in output order.
    summary : MutationSummary, optional
        Counts of the changes applied by the statement, by default all zero.
    """

    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    summary: MutationSummary = dataclasses.field(default_factory=MutationSummary)

    def __post_init__(self) -> None:
        """Materialize the result columns and rows as tuples."""
        object.__setattr__(self, "columns", tuple(self.columns))
        object.__setattr__(self, "rows", tuple(self.rows))

    def __iter__(self) -> Iterator[Row]:
        """Iterate over result rows.

        Returns
        -------
        Iterator[Row]
            Rows in output order.
        """
        return iter(self.rows)

    def __len__(self) -> int:
        """Return the number of result rows.

        Returns
        -------
        int
            Number of rows.
        """
        return len(self.rows)


__all__ = [
    "MutationSummary",
    "QueryResult",
    "Row",
]
