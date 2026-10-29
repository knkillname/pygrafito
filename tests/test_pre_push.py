# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the local verification command and the pre-push hook."""

import os
import pathlib
import shutil
import subprocess
import typing

import pytest


class _PosixShell:
    """Locate a POSIX shell that can run the verification scripts."""

    CANDIDATES: typing.ClassVar[tuple[str, ...]] = ("sh", "bash")
    WINDOWS_PATHS: typing.ClassVar[tuple[str, ...]] = (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\bin\sh.exe",
        r"C:\Program Files\Git\usr\bin\sh.exe",
    )

    @classmethod
    def find(cls) -> str | None:
        """Return the first available POSIX shell.

        Returns
        -------
        str | None
            Shell executable, or ``None`` when no shell is available.
        """
        for name in cls.CANDIDATES:
            target = shutil.which(name)
            if target is not None:
                return target
        for candidate in cls.WINDOWS_PATHS:
            path = pathlib.Path(candidate)
            if path.exists():
                return str(path)
        return None

    @classmethod
    def require(cls) -> str:
        """Return a POSIX shell or skip the current test.

        Returns
        -------
        str
            Shell executable.
        """
        shell = cls.find()
        if shell is None:
            pytest.skip(
                "a POSIX shell (Git Bash on Windows) is required for scripts/verify "
                "and the pre-push hook"
            )
        return shell


class _ScratchRepository:
    """Provide a temporary repository wired to a local bare remote."""

    ROOT: typing.ClassVar[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.origin = root / "origin.git"
        self.work = root / "work"
        self.home = root / "home"
        self.call_log = root / "calls.log"

    @classmethod
    def create(cls, root: pathlib.Path) -> "_ScratchRepository":
        """Create and initialize a temporary repository.

        Parameters
        ----------
        root : pathlib.Path
            Temporary directory for the remote, work tree, and logs.

        Returns
        -------
        _ScratchRepository
            Initialized repository.
        """
        _PosixShell.require()
        repository = cls(root)
        repository._initialize()
        return repository

    def _initialize(self) -> None:
        """Create the remote, work tree, hook, and initial commit."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.home.mkdir()
        subprocess.run(
            ["git", "init", "--bare", str(self.origin)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "init", "-b", "main", str(self.work)],
            check=True,
            capture_output=True,
            text=True,
        )
        self._install_hook()
        self._install_verify_stub()
        self.git("config", "user.name", "TRON Test")
        self.git("config", "user.email", "tron@example.invalid")
        self.git("config", "core.hooksPath", ".githooks")
        self.git("remote", "add", "origin", str(self.origin))
        self.write("README.md", "# Scratch\n")
        self.git("add", "README.md")
        self.git("commit", "-m", "Initial commit")
        self.git("push", "-u", "origin", "main")
        self.clear_log()

    def _install_hook(self) -> None:
        """Copy the real pre-push hook into the scratch repository."""
        hooks = self.work / ".githooks"
        hooks.mkdir(parents=True)
        shutil.copy2(self.ROOT / ".githooks" / "pre-push", hooks / "pre-push")

    def _install_verify_stub(self) -> None:
        """Install a verification stub that records its arguments."""
        scripts = self.work / "scripts"
        scripts.mkdir(parents=True)
        verify = scripts / "verify"
        verify.write_text(
            '#!/bin/sh\nprintf "verify [%s]\\n" "$*" >> "$CALL_LOG"\nexit "${VERIFY_STATUS:-0}"\n',
            encoding="utf-8",
        )
        verify.chmod(0o755)

    def _environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build an isolated process environment.

        Parameters
        ----------
        extra : dict[str, str] | None, optional
            Additional environment values, by default none.

        Returns
        -------
        dict[str, str]
            Environment for Git and the hook.
        """
        environment = dict(os.environ)
        environment.update(
            {
                "HOME": str(self.home),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "TRON Test",
                "GIT_AUTHOR_EMAIL": "tron@example.invalid",
                "GIT_COMMITTER_NAME": "TRON Test",
                "GIT_COMMITTER_EMAIL": "tron@example.invalid",
                "GIT_TERMINAL_PROMPT": "0",
                "CALL_LOG": str(self.call_log),
            }
        )
        environment.pop("PREGRAFITO_SKIP_SQLITE", None)
        if extra:
            environment.update(extra)
        return environment

    def git(
        self,
        *args: str,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one Git command in the scratch work tree.

        Parameters
        ----------
        *args : str
            Git arguments.
        check : bool, optional
            Whether to raise on a non-zero exit, by default ``True``.
        env : dict[str, str] | None, optional
            Extra environment values, by default none.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Completed command.
        """
        return subprocess.run(
            ["git", *args],
            cwd=self.work,
            env=self._environment(env),
            check=check,
            capture_output=True,
            text=True,
        )

    def write(self, relative: str, content: str) -> pathlib.Path:
        """Write one file inside the work tree.

        Parameters
        ----------
        relative : str
            Path relative to the work tree.
        content : str
            File content.

        Returns
        -------
        pathlib.Path
            Written path.
        """
        path = self.work / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def commit(self, relative: str, content: str, message: str) -> None:
        """Write and commit one file.

        Parameters
        ----------
        relative : str
            Path relative to the work tree.
        content : str
            File content.
        message : str
            Commit message.
        """
        self.write(relative, content)
        self.git("add", relative)
        self.git("commit", "-m", message)

    def push(
        self,
        *args: str,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one push against the local bare remote.

        Parameters
        ----------
        *args : str
            Additional push arguments.
        check : bool, optional
            Whether to raise on a non-zero exit, by default ``True``.
        env : dict[str, str] | None, optional
            Extra environment values, by default none.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Completed command.
        """
        return self.git("push", *args, check=check, env=env)

    def clear_log(self) -> None:
        """Reset the verification call log."""
        self.call_log.write_text("", encoding="utf-8")

    def calls(self) -> list[str]:
        """Return the recorded verification calls.

        Returns
        -------
        list[str]
            One line per verification invocation.
        """
        if not self.call_log.exists():
            return []
        return self.call_log.read_text(encoding="utf-8").splitlines()


class TestVerifyScript:
    """Verify the manual verification command and its flags."""

    ROOT: typing.ClassVar[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
    SCRIPT: typing.ClassVar[pathlib.Path] = ROOT / "scripts" / "verify"

    def _write_stub(self, path: pathlib.Path, content: str) -> None:
        """Write an executable shell stub.

        Parameters
        ----------
        path : pathlib.Path
            Stub path.
        content : str
            Shell source.
        """
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def _environment(
        self,
        tmp_path: pathlib.Path,
        *,
        hatch: bool = True,
        docker: bool = True,
        values: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], pathlib.Path]:
        """Build a PATH with command stubs and a call log.

        Parameters
        ----------
        tmp_path : pathlib.Path
            Temporary directory.
        hatch : bool, optional
            Whether to provide a hatch stub, by default ``True``.
        docker : bool, optional
            Whether to provide a docker stub, by default ``True``.
        values : dict[str, str] | None, optional
            Additional environment values, by default none.

        Returns
        -------
        tuple[dict[str, str], pathlib.Path]
            Process environment and call-log path.
        """
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        system_bin = tmp_path / "system-bin"
        system_bin.mkdir()
        for name in ("cat", "date", "dirname"):
            target = shutil.which(name)
            assert target is not None
            link = system_bin / name
            try:
                link.symlink_to(target)
            except OSError:
                shutil.copy2(target, link)
        call_log = tmp_path / "calls.log"
        call_log.write_text("", encoding="utf-8")
        if hatch:
            self._write_stub(
                bin_dir / "hatch",
                "#!/bin/sh\n"
                'printf "hatch [%s]\\n" "$*" >> "$CALL_LOG"\n'
                'case "${1:-}" in\n'
                '  check) exit "${HATCH_CHECK_STATUS:-0}" ;;\n'
                '  test) exit "${HATCH_TEST_STATUS:-0}" ;;\n'
                '  run) exit "${HATCH_RUN_STATUS:-0}" ;;\n'
                "esac\n"
                "exit 0\n",
            )
        if docker:
            self._write_stub(
                bin_dir / "docker",
                "#!/bin/sh\n"
                'printf "docker [%s]\\n" "$*" >> "$CALL_LOG"\n'
                'if [ "${1:-}" = "info" ]; then\n'
                '  exit "${DOCKER_INFO_STATUS:-0}"\n'
                "fi\n"
                'if [ "${1:-}" = "compose" ] && [ "${2:-}" = "version" ]; then\n'
                '  exit "${DOCKER_COMPOSE_STATUS:-0}"\n'
                "fi\n"
                'if [ "${1:-}" = "compose" ] && [ "${2:-}" = "run" ]; then\n'
                '  exit "${DOCKER_RUN_STATUS:-0}"\n'
                "fi\n"
                "exit 0\n",
            )
        environment = dict(os.environ)
        environment["PATH"] = f"{bin_dir}{os.pathsep}{system_bin}"
        environment["CALL_LOG"] = str(call_log)
        environment.pop("PREGRAFITO_SKIP_SQLITE", None)
        if values:
            environment.update(values)
        return environment, call_log

    def _run(
        self,
        environment: dict[str, str],
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run the verification script with the stub environment.

        Parameters
        ----------
        environment : dict[str, str]
            Process environment.
        *args : str
            Script arguments.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Completed command.
        """
        return subprocess.run(
            [_PosixShell.require(), str(self.SCRIPT), *args],
            cwd=self.ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_default_runs_check_test_and_sqlite(self, tmp_path: pathlib.Path) -> None:
        environment, call_log = self._environment(tmp_path)
        completed = self._run(environment)
        assert completed.returncode == 0, completed.stderr
        assert call_log.read_text(encoding="utf-8").splitlines() == [
            "docker [compose version]",
            "docker [info]",
            "hatch [check]",
            "hatch [test -i py=3.13,3.14]",
            "docker [compose run --rm test-sqlite]",
        ]

    def test_skip_sqlite_flag(self, tmp_path: pathlib.Path) -> None:
        environment, call_log = self._environment(tmp_path)
        completed = self._run(environment, "--skip-sqlite")
        assert completed.returncode == 0, completed.stderr
        assert call_log.read_text(encoding="utf-8").splitlines() == [
            "hatch [check]",
            "hatch [test -i py=3.13,3.14]",
        ]

    def test_skip_sqlite_environment(self, tmp_path: pathlib.Path) -> None:
        environment, call_log = self._environment(
            tmp_path,
            values={"PREGRAFITO_SKIP_SQLITE": "1"},
        )
        completed = self._run(environment)
        assert completed.returncode == 0, completed.stderr
        assert call_log.read_text(encoding="utf-8").splitlines() == [
            "hatch [check]",
            "hatch [test -i py=3.13,3.14]",
        ]

    def test_docs_flag(self, tmp_path: pathlib.Path) -> None:
        environment, call_log = self._environment(tmp_path)
        completed = self._run(environment, "--skip-sqlite", "--docs")
        assert completed.returncode == 0, completed.stderr
        assert call_log.read_text(encoding="utf-8").splitlines() == [
            "hatch [check]",
            "hatch [test -i py=3.13,3.14]",
            "hatch [run docs:build]",
        ]

    def test_missing_docker_mentions_the_opt_out(self, tmp_path: pathlib.Path) -> None:
        environment, call_log = self._environment(tmp_path, docker=False)
        completed = self._run(environment)
        assert completed.returncode == 1
        assert "--skip-sqlite" in completed.stderr
        assert call_log.read_text(encoding="utf-8") == ""

    def test_missing_compose_mentions_compose(self, tmp_path: pathlib.Path) -> None:
        environment, call_log = self._environment(
            tmp_path,
            values={"DOCKER_COMPOSE_STATUS": "1"},
        )
        completed = self._run(environment)
        assert completed.returncode == 1
        assert "Docker Compose" in completed.stderr
        assert call_log.read_text(encoding="utf-8").splitlines() == [
            "docker [compose version]",
        ]

    def test_missing_daemon_mentions_daemon(self, tmp_path: pathlib.Path) -> None:
        environment, call_log = self._environment(
            tmp_path,
            values={"DOCKER_INFO_STATUS": "1"},
        )
        completed = self._run(environment)
        assert completed.returncode == 1
        assert "daemon" in completed.stderr
        assert call_log.read_text(encoding="utf-8").splitlines() == [
            "docker [compose version]",
            "docker [info]",
        ]

    def test_failing_stage_short_circuits(self, tmp_path: pathlib.Path) -> None:
        environment, call_log = self._environment(
            tmp_path,
            values={"HATCH_CHECK_STATUS": "1"},
        )
        completed = self._run(environment, "--skip-sqlite")
        assert completed.returncode == 1
        assert call_log.read_text(encoding="utf-8").splitlines() == ["hatch [check]"]

    def test_unknown_argument(self, tmp_path: pathlib.Path) -> None:
        environment, _ = self._environment(tmp_path)
        completed = self._run(environment, "--bogus")
        assert completed.returncode == 2
        assert "unknown argument" in completed.stderr

    def test_help(self, tmp_path: pathlib.Path) -> None:
        environment, _ = self._environment(tmp_path)
        completed = self._run(environment, "--help")
        assert completed.returncode == 0
        assert "Usage: scripts/verify" in completed.stdout


class TestPrePushHook:
    """Verify the Git-specific pre-push decisions."""

    def test_clean_code_push_runs_verify(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.commit("code.txt", "Flynn\n", "Add code")
        completed = repository.push("origin", "main")
        assert completed.returncode == 0, completed.stderr
        assert repository.calls() == ["verify []"]

    def test_docs_push_runs_docs_build(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.commit("docs/page.md", "# Grid\n", "Add docs")
        completed = repository.push("origin", "main")
        assert completed.returncode == 0, completed.stderr
        assert repository.calls() == ["verify [--docs]"]

    def test_readme_push_runs_docs_build(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.commit("README.md", "# Grid\n", "Update readme")
        completed = repository.push("origin", "main")
        assert completed.returncode == 0, completed.stderr
        assert repository.calls() == ["verify [--docs]"]

    def test_new_branch_runs_docs_build(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.git("checkout", "-b", "feature")
        repository.commit("code.txt", "Quorra\n", "Add feature")
        completed = repository.push("-u", "origin", "feature")
        assert completed.returncode == 0, completed.stderr
        assert repository.calls() == ["verify [--docs]"]

    def test_pure_deletion_skips_verification(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.git("checkout", "-b", "feature")
        repository.commit("code.txt", "Tron\n", "Add feature")
        repository.push("-u", "origin", "feature")
        repository.clear_log()
        completed = repository.push("origin", "--delete", "feature")
        assert completed.returncode == 0, completed.stderr
        assert repository.calls() == []

    def test_dirty_tracked_tree_aborts(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.commit("code.txt", "Rinzler\n", "Add code")
        repository.write("README.md", "# Dirty\n")
        completed = repository.push("origin", "main", check=False)
        assert completed.returncode != 0
        assert "tracked files differ from HEAD" in completed.stderr
        assert repository.calls() == []

    def test_pushed_ref_must_be_head(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.git("checkout", "-b", "feature")
        repository.commit("code.txt", "Clu\n", "Add feature")
        repository.git("checkout", "main")
        completed = repository.push("origin", "feature", check=False)
        assert completed.returncode != 0
        assert "HEAD" in completed.stderr
        assert repository.calls() == []

    def test_skip_sqlite_environment_is_forwarded(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.commit("code.txt", "ISO\n", "Add code")
        completed = repository.push(
            "origin",
            "main",
            env={"PREGRAFITO_SKIP_SQLITE": "1"},
        )
        assert completed.returncode == 0, completed.stderr
        assert repository.calls() == ["verify [--skip-sqlite]"]

    def test_verify_failure_aborts_push(self, tmp_path: pathlib.Path) -> None:
        repository = _ScratchRepository.create(tmp_path)
        repository.commit("code.txt", "Sark\n", "Add code")
        completed = repository.push(
            "origin",
            "main",
            check=False,
            env={"VERIFY_STATUS": "1"},
        )
        assert completed.returncode != 0
        assert repository.calls() == ["verify []"]
