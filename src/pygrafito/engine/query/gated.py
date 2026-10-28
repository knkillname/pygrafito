# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Constructs the profile lists as gated and the change that implements each."""

import typing


class Gated:
    """Name each gated construct and the follow-up change that implements it."""

    QUANTIFIER: str = "quantifier"
    PATH_MODE: str = "path-mode"
    DIRECTION: str = "direction"
    ORDINALITY: str = "ordinality"
    NO_BINDINGS: str = "no-bindings"
    LET: str = "let"
    NEXT: str = "next"
    GROUP_BY: str = "group-by"

    PATH_SEMANTICS: str = "add-gql-path-semantics"
    COMPOSITION: str = "add-gql-composition"

    ENTRIES: typing.ClassVar[dict[str, tuple[str, str]]] = {
        QUANTIFIER: ("the {n,m} quantifier", PATH_SEMANTICS),
        PATH_MODE: ("an explicit path mode", PATH_SEMANTICS),
        DIRECTION: ("the <~, ~>, and <-> direction forms", PATH_SEMANTICS),
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
