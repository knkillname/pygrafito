# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Module entry point for ``python -m pygrafito``."""

from pygrafito.cli.app import App

if __name__ == "__main__":
    raise SystemExit(App.main())
