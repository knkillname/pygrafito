# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Smoke test for the benchmark harness."""

import subprocess
import sys
import typing
from pathlib import Path


class TestBenchmarkHarness:
    """Verify the harness runs end to end on a tiny dataset."""

    SCRIPT: typing.ClassVar[Path] = Path(__file__).resolve().parents[1] / "benchmarks" / "run.py"

    def test_tiny_run(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.SCRIPT),
                "--nodes",
                "40",
                "--relationships",
                "60",
                "--repeats",
                "1",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "scenario" in completed.stdout
        assert "insert" in completed.stdout
        assert "update" in completed.stdout
