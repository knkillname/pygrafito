# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Constructs the profile lists as gated and the change that implements each."""

import typing


class Gated:
    """Name each gated construct and the follow-up change that implements it."""

    OPEN_BOUND: str = "open-bound"
    ORDINALITY: str = "ordinality"
    NO_BINDINGS: str = "no-bindings"
    LET: str = "let"
    NEXT: str = "next"
    GROUP_BY: str = "group-by"

    UNBOUNDED: str = "add-gql-unbounded-traversal"
    COMPOSITION: str = "add-gql-composition"

    ENTRIES: typing.ClassVar[dict[str, tuple[str, str]]] = {
        OPEN_BOUND: ("an open-ended quantifier", UNBOUNDED),
        ORDINALITY: ("WITH ORDINALITY and WITH OFFSET", COMPOSITION),
        NO_BINDINGS: ("RETURN NO BINDINGS", COMPOSITION),
        LET: ("LET", COMPOSITION),
        NEXT: ("NEXT", COMPOSITION),
        GROUP_BY: ("GROUP BY", COMPOSITION),
    }

    @classmethod
    def message(cls, key: str) -> str:
        """Return the error message for one gated construct.

        Parameters
        ----------
        key : str
            Gated construct key.

        Returns
        -------
        str
            Message naming the construct and its follow-up change.
        """
        construct, change = cls.ENTRIES[key]
        return (
            f"{construct} is part of the target GQL profile but is not implemented "
            f"in this release; it lands with {change}"
        )
