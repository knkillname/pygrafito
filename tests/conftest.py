# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Shared test configuration for deterministic property tests."""

import os

import hypothesis


class HypothesisProfiles:
    """Register the gate and nightly Hypothesis profiles."""

    GATE: str = "gate"
    NIGHTLY: str = "nightly"
    GATE_EXAMPLES: int = 50
    NIGHTLY_EXAMPLES: int = 500

    @classmethod
    def register(cls) -> None:
        """Register both profiles and load the selected one.

        The gate profile is the default. The nightly workflow sets
        ``HYPOTHESIS_PROFILE=nightly`` for a longer run.
        """
        profiles = (
            (cls.GATE, cls.GATE_EXAMPLES),
            (cls.NIGHTLY, cls.NIGHTLY_EXAMPLES),
        )
        for name, examples in profiles:
            hypothesis.settings.register_profile(
                name,
                max_examples=examples,
                deadline=None,
                derandomize=True,
                database=None,
                suppress_health_check=[hypothesis.HealthCheck.too_slow],
            )
        selected = os.environ.get("HYPOTHESIS_PROFILE", cls.GATE)
        hypothesis.settings.load_profile(selected)


HypothesisProfiles.register()
