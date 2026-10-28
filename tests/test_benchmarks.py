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

    ROOT: typing.ClassVar[Path] = Path(__file__).resolve().parents[1]

    def test_tiny_run(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.run",
                "--nodes",
                "40",
                "--relationships",
                "60",
                "--repeats",
                "1",
            ],
            cwd=self.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "scenario" in completed.stdout
        assert "insert" in completed.stdout
        assert "update" in completed.stdout
