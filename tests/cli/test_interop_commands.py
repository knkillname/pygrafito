# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the ``.export`` and ``.restore`` shell commands."""

from pathlib import Path

from pygrafito import Graph
from tests.cli.support import Fixtures, Harness


class Snapshots:
    """Create snapshots for command tests."""

    @staticmethod
    def build(tmp_path: Path) -> Path:
        """Export the standard shell fixture to a snapshot.

        Parameters
        ----------
        tmp_path : Path
            Temporary directory.

        Returns
        -------
        Path
            Written snapshot.
        """
        source = tmp_path / "source.db"
        destination = tmp_path / "snapshot.jsonl"
        Fixtures.seed(source)
        with Graph.open(source) as graph:
            graph.export_jsonl(destination)
        return destination


class TestExportCommand:
    """Verify `.export` options, summaries, and refusals."""

    def test_export(self, tmp_path: Path) -> None:
        """A snapshot is written and summarized."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "snapshot.jsonl"
        harness = Harness(path)
        try:
            code, output, error = harness.run(f".export {destination}\n")
        finally:
            harness.close()

        assert code == 0
        assert error == ""
        assert "exported 3 nodes and 3 relationships" in output
        assert str(destination) in output
        assert destination.exists()

    def test_explicit_format(self, tmp_path: Path) -> None:
        """`--format jsonl` is accepted for a non-JSONL suffix."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "snapshot.txt"
        harness = Harness(path)
        try:
            code, _, _ = harness.run(f".export {destination} --format jsonl\n")
        finally:
            harness.close()

        assert code == 0
        assert destination.read_text(encoding="utf-8").startswith(
            '{"kind":"header","format":"pygrafito-jsonl"'
        )

    def test_existing_destination(self, tmp_path: Path) -> None:
        """An existing path is refused without overwrite."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "snapshot.jsonl"
        destination.write_text("keep me", encoding="utf-8")
        harness = Harness(path)
        try:
            code, _, error = harness.run(f".export {destination}\n")
        finally:
            harness.close()

        assert code == 1
        assert "already exists" in error
        assert destination.read_text(encoding="utf-8") == "keep me"

    def test_overwrite(self, tmp_path: Path) -> None:
        """`--overwrite` replaces an existing destination."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "snapshot.jsonl"
        destination.write_text("old", encoding="utf-8")
        harness = Harness(path)
        try:
            code, _, _ = harness.run(f".export {destination} --overwrite\n")
        finally:
            harness.close()

        assert code == 0
        assert destination.read_text(encoding="utf-8").startswith(
            '{"kind":"header","format":"pygrafito-jsonl"'
        )

    def test_live_database_path(self, tmp_path: Path) -> None:
        """The open database is never an export target."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        harness = Harness(path)
        try:
            code, _, error = harness.run(f".export {path}\n")
        finally:
            harness.close()

        assert code == 1
        assert "open database" in error

    def test_read_only_session(self, tmp_path: Path) -> None:
        """A read-only session can export."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "snapshot.jsonl"
        harness = Harness(path, readonly=True)
        try:
            code, output, _ = harness.run(f".export {destination}\n")
        finally:
            harness.close()

        assert code == 0
        assert "exported 3 nodes and 3 relationships" in output
        assert destination.exists()

    def test_active_transaction(self, tmp_path: Path) -> None:
        """Export is refused while a transaction is active."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "snapshot.jsonl"
        harness = Harness(path)
        try:
            code, _, error = harness.run(f".begin\n.export {destination}\n")
            assert code == 1
            assert "not available while a transaction is active" in error
            assert harness.session.in_transaction
        finally:
            harness.close()

        assert not destination.exists()

    def test_quoted_path(self, tmp_path: Path) -> None:
        """A quoted path with spaces is one argument."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "grid snapshot.jsonl"
        harness = Harness(path)
        try:
            code, _, _ = harness.run(f'.export "{destination}"\n')
        finally:
            harness.close()

        assert code == 0
        assert destination.exists()

    def test_help(self) -> None:
        """Help lists the command and its options."""
        harness = Harness()
        try:
            _, listing, _ = harness.run(".help\n")
            _, output, _ = harness.run(".help export\n")
        finally:
            harness.close()

        assert ".export" in listing
        assert ".restore" in listing
        assert ".export PATH [--format jsonl] [--overwrite]" in output

    def test_unsupported_format(self, tmp_path: Path) -> None:
        """Only JSONL is accepted."""
        harness = Harness()
        try:
            code, _, error = harness.run(f".export {tmp_path / 'x.jsonl'} --format csv\n")
        finally:
            harness.close()

        assert code == 1
        assert "--format must be 'jsonl'" in error

    def test_unknown_option(self, tmp_path: Path) -> None:
        """Unknown options are usage errors."""
        harness = Harness()
        try:
            code, _, error = harness.run(f".export {tmp_path / 'x.jsonl'} --bogus\n")
        finally:
            harness.close()

        assert code == 1
        assert "unknown .export option" in error

    def test_missing_path(self) -> None:
        """A missing path reports usage."""
        harness = Harness()
        try:
            code, _, error = harness.run(".export\n")
        finally:
            harness.close()

        assert code == 1
        assert "usage: .export" in error

    def test_error_isolation(self, tmp_path: Path) -> None:
        """A failed export leaves the session usable."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        harness = Harness(path)
        try:
            failed, _, _ = harness.run(f".export {path}\n")
            code, output, _ = harness.run("MATCH (n) RETURN count(*) AS total;\n")
        finally:
            harness.close()

        assert failed == 1
        assert code == 0
        assert "3" in output


class TestRestoreCommand:
    """Verify `.restore` options, summaries, and refusals."""

    def test_restore_into_empty(self, tmp_path: Path) -> None:
        """A snapshot restores into a transient graph."""
        snapshot = Snapshots.build(tmp_path)
        harness = Harness()
        try:
            code, output, error = harness.run(f".restore {snapshot}\n")
            query_code, query_output, _ = harness.run("MATCH (n) RETURN count(*) AS total;\n")
        finally:
            harness.close()

        assert code == 0
        assert error == ""
        assert "restored 3 nodes and 3 relationships" in output
        assert str(snapshot) in output
        assert query_code == 0
        assert "3" in query_output

    def test_non_empty_without_replace(self, tmp_path: Path) -> None:
        """A populated target is refused without `--replace`."""
        snapshot = Snapshots.build(tmp_path)
        harness = Harness()
        try:
            harness.run("CREATE (n:Program {designation: 'Rinzler'});\n")
            code, _, error = harness.run(f".restore {snapshot}\n")
            _, output, _ = harness.run("MATCH (n:Program) RETURN n.designation AS name;\n")
        finally:
            harness.close()

        assert code == 1
        assert "not empty" in error
        assert "Rinzler" in output

    def test_replace(self, tmp_path: Path) -> None:
        """`--replace` swaps the graph."""
        snapshot = Snapshots.build(tmp_path)
        harness = Harness()
        try:
            harness.run("CREATE (n:Program {designation: 'Rinzler'});\n")
            code, output, _ = harness.run(f".restore {snapshot} --replace\n")
            _, query_output, _ = harness.run("MATCH (n:Program) RETURN n.designation AS name;\n")
        finally:
            harness.close()

        assert code == 0
        assert "restored 3 nodes and 3 relationships" in output
        assert "Rinzler" not in query_output
        assert "Tron" in query_output

    def test_replace_failure_keeps_graph(self, tmp_path: Path) -> None:
        """A failed replace restores the original graph."""
        snapshot = Snapshots.build(tmp_path)
        lines = snapshot.read_text(encoding="utf-8").splitlines()
        lines[-1] = lines[-1].replace('"start_id":3', '"start_id":99', 1)
        invalid = tmp_path / "invalid.jsonl"
        invalid.write_text("\n".join(lines) + "\n", encoding="utf-8")

        harness = Harness()
        try:
            harness.run("CREATE (n:Program {designation: 'Rinzler'});\n")
            code, _, error = harness.run(f".restore {invalid} --replace\n")
            _, output, _ = harness.run("MATCH (n:Program) RETURN n.designation AS name;\n")
        finally:
            harness.close()

        assert code == 1
        assert "unknown node id" in error
        assert "Rinzler" in output

    def test_read_only_session(self, tmp_path: Path) -> None:
        """A read-only session cannot restore."""
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        snapshot = Snapshots.build(tmp_path)
        harness = Harness(path, readonly=True)
        try:
            code, _, error = harness.run(f".restore {snapshot}\n")
        finally:
            harness.close()

        assert code == 1
        assert "read-only" in error
        with Graph.open(path) as graph:
            assert graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"] == 3

    def test_active_transaction(self, tmp_path: Path) -> None:
        """Restore is refused while a transaction is active."""
        snapshot = Snapshots.build(tmp_path)
        harness = Harness()
        try:
            code, _, error = harness.run(f".begin\n.restore {snapshot}\n")
            assert code == 1
            assert "not available while a transaction is active" in error
            assert harness.session.in_transaction
        finally:
            harness.close()

    def test_malformed_snapshot(self, tmp_path: Path) -> None:
        """A malformed header is reported and the session stays usable."""
        malformed = tmp_path / "malformed.jsonl"
        malformed.write_text(
            '{"kind":"node","id":1,"labels":[],"properties":{}}\n',
            encoding="utf-8",
        )
        harness = Harness()
        try:
            code, _, error = harness.run(f".restore {malformed}\n")
            query_code, _, _ = harness.run("MATCH (n) RETURN count(*) AS total;\n")
        finally:
            harness.close()

        assert code == 1
        assert "line 1" in error
        assert query_code == 0

    def test_quoted_path(self, tmp_path: Path) -> None:
        """A quoted snapshot path with spaces is accepted."""
        snapshot = Snapshots.build(tmp_path)
        quoted = tmp_path / "grid snapshot.jsonl"
        snapshot.rename(quoted)
        harness = Harness()
        try:
            code, _, _ = harness.run(f'.restore "{quoted}"\n')
        finally:
            harness.close()

        assert code == 0

    def test_help(self) -> None:
        """Help describes the restore options."""
        harness = Harness()
        try:
            _, output, _ = harness.run(".help restore\n")
        finally:
            harness.close()

        assert ".restore PATH [--replace]" in output

    def test_unknown_option(self, tmp_path: Path) -> None:
        """Unknown restore options are usage errors."""
        snapshot = Snapshots.build(tmp_path)
        harness = Harness()
        try:
            code, _, error = harness.run(f".restore {snapshot} --bogus\n")
        finally:
            harness.close()

        assert code == 1
        assert "unknown .restore option" in error

    def test_missing_path(self) -> None:
        """A missing path reports usage."""
        harness = Harness()
        try:
            code, _, error = harness.run(".restore\n")
        finally:
            harness.close()

        assert code == 1
        assert "usage: .restore" in error

    def test_error_isolation(self, tmp_path: Path) -> None:
        """A failed restore leaves the session usable."""
        malformed = tmp_path / "malformed.jsonl"
        malformed.write_text("not json\n", encoding="utf-8")
        harness = Harness()
        try:
            failed, _, _ = harness.run(f".restore {malformed}\n")
            code, _, _ = harness.run("MATCH (n) RETURN count(*) AS total;\n")
        finally:
            harness.close()

        assert failed == 1
        assert code == 0
