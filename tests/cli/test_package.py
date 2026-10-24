# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Smoke tests for the command-line package surface."""

import inspect

import pygrafito.cli
import pygrafito.cli.app
import pygrafito.cli.commands
import pygrafito.cli.formatting
import pygrafito.cli.reader
import pygrafito.cli.session
import pygrafito.cli.shell


class TestCliPackage:
    """Verify that the command-line modules import and expose the entry point."""

    def test_modules_import(self) -> None:
        modules = (
            pygrafito.cli,
            pygrafito.cli.app,
            pygrafito.cli.commands,
            pygrafito.cli.formatting,
            pygrafito.cli.reader,
            pygrafito.cli.session,
            pygrafito.cli.shell,
        )
        assert all(module.__name__.startswith("pygrafito.cli") for module in modules)

    def test_main_is_a_static_method(self) -> None:
        entry = inspect.getattr_static(pygrafito.cli.app.App, "main")
        assert isinstance(entry, staticmethod)
