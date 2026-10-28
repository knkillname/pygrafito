# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for dot-commands: session, introspection, transactions, maintenance."""

import sqlite3
from pathlib import Path

import pytest

from pygrafito import Graph, NotFoundError
from pygrafito.cli.formatting import OutputMode
from tests.cli.support import Fixtures, Harness


class TestSessionCommands:
    """Verify help, database selection, and output control."""

    def test_help_lists_commands(self) -> None:
        harness = Harness()
        try:
            code, output, _ = harness.run(".help\n")
        finally:
            harness.close()
        assert code == 0
        assert "Commands:" in output
        assert ".schema" in output
        assert ".backup" in output

    def test_help_for_one_command(self) -> None:
        harness = Harness()
        try:
            _, output, _ = harness.run(".help mode\n")
        finally:
            harness.close()
        assert ".mode table|json|jsonl|csv|line" in output

    def test_unknown_command(self) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run(".bogus\n")
        finally:
            harness.close()
        assert code == 1
        assert 'unknown command ".bogus"' in error

    def test_open_and_close(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        harness = Harness()
        try:
            code, _, _ = harness.run(
                f".open {path}\nCREATE (n:Program {{designation: 'Tron'}});\n.close\n"
            )
            assert code == 0
            assert path.exists()
            failed, _, error = harness.run("MATCH (n) RETURN n;\n")
        finally:
            harness.close()

        assert failed == 1
        assert "no database is open" in error

    def test_mode_switches_rendering(self) -> None:
        harness = Harness()
        try:
            _, output, _ = harness.run(
                ".mode json\nCREATE (n:Program {designation: 'Tron'}) "
                "RETURN n.designation AS name;\n"
            )
        finally:
            harness.close()
        assert '"name": "Tron"' in output

    def test_mode_rejects_unknown_name(self) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run(".mode yaml\n")
        finally:
            harness.close()
        assert code == 1
        assert "unknown output mode" in error

    def test_headers_off(self) -> None:
        harness = Harness()
        try:
            _, output, _ = harness.run(
                ".headers off\nCREATE (n:Program {designation: 'Tron'}) "
                "RETURN n.designation AS name;\n"
            )
        finally:
            harness.close()
        assert "name" not in output
        assert "Tron" in output

    def test_output_command_reports_and_redirects(self, tmp_path: Path) -> None:
        destination = tmp_path / "result.txt"
        harness = Harness()
        try:
            _, output, _ = harness.run(".output\n")
            assert output.strip() == "stdout"
            harness.reset()
            code, _, _ = harness.run(
                f".output {destination}\nCREATE (n:Program {{designation: 'Tron'}}) RETURN n;\n"
            )
        finally:
            harness.close()

        assert code == 0
        assert "(:Program" in destination.read_text(encoding="utf-8")

    def test_once_command(self, tmp_path: Path) -> None:
        destination = tmp_path / "once.txt"
        harness = Harness()
        try:
            _, output, _ = harness.run(
                "CREATE (n:Program {designation: 'Tron'});\n"
                f".once {destination}\n"
                "MATCH (n:Program) RETURN n.designation AS name;\n"
                "MATCH (n:Program) RETURN n.designation AS name;\n"
            )
        finally:
            harness.close()
        assert "Tron" in destination.read_text(encoding="utf-8")
        assert "Tron" in output

    def test_parameter_command(self) -> None:
        harness = Harness()
        try:
            _, output, _ = harness.run(
                '.param name="Quorra"\n'
                "CREATE (n:Program {designation: $name}) RETURN n.designation AS name;\n"
            )
            harness.reset()
            _, listing, _ = harness.run(".param\n")
        finally:
            harness.close()

        assert "Quorra" in output
        assert 'name = "Quorra"' in listing

    def test_parameter_command_rejects_bad_json(self) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run(".param name=not-json\n")
        finally:
            harness.close()
        assert code == 1
        assert "invalid JSON" in error


class TestTransactionCommands:
    """Verify explicit transactions and their refusals."""

    def test_commit(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        harness = Harness(path)
        try:
            code, _, _ = harness.run(".begin\nCREATE (n:Program {designation: 'Tron'});\n.commit\n")
        finally:
            harness.close()
        assert code == 0
        with Graph.open(path) as graph:
            assert graph.query("MATCH (n:Program) RETURN count(*) AS t").rows[0]["t"] == 1

    def test_rollback(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        harness = Harness(path)
        try:
            code, _, _ = harness.run(
                ".begin\nCREATE (n:Program {designation: 'Tron'});\n.rollback\n"
            )
        finally:
            harness.close()
        assert code == 0
        with Graph.open(path) as graph:
            assert graph.query("MATCH (n:Program) RETURN count(*) AS t").rows[0]["t"] == 0

    def test_begin_twice(self) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run(".begin\n.begin\n")
        finally:
            harness.close()
        assert code == 1
        assert "already active" in error

    def test_commit_without_transaction(self) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run(".commit\n")
        finally:
            harness.close()
        assert code == 1
        assert "no transaction is active" in error

    def test_rollback_without_transaction(self) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run(".rollback\n")
        finally:
            harness.close()
        assert code == 1
        assert "no transaction is active" in error

    def test_open_and_close_refused_during_transaction(self, tmp_path: Path) -> None:
        harness = Harness()
        try:
            _, _, open_error = harness.run(f".begin\n.open {tmp_path / 'other.db'}\n")
            harness.reset()
            _, _, close_error = harness.run(".close\n")
            still_active = harness.session.in_transaction
            harness.session.rollback()
        finally:
            harness.close()

        assert "not available while a transaction is active" in open_error
        assert "not available while a transaction is active" in close_error
        assert still_active

    def test_quit_rolls_back(self) -> None:
        harness = Harness()
        try:
            code, _, _ = harness.run(".begin\nCREATE (n:Program {designation: 'Tron'});\n.quit\n")
        finally:
            harness.close()
        assert code == 0
        assert "rolled back an open transaction" in harness.error.getvalue()


class TestSchemaCommands:
    """Verify the metadata inventory commands."""

    @pytest.fixture
    def seeded(self, tmp_path: Path) -> Path:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with Graph.open(path) as graph:
            graph.create_node_index("cycles")
            graph.create_node_uniqueness_constraint("Program", "designation")
        return path

    def test_schema(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            code, output, _ = harness.run(".schema\n")
        finally:
            harness.close()

        assert code == 0
        assert output.splitlines() == [
            "Labels",
            "  ISO               1 node   cycles, designation",
            "  Program           3 nodes   cycles, designation",
            "Relationship labels",
            "  ALLIES_WITH       2 relationships",
            "  GUARDS            1 relationship",
            "Directions",
            "  directed          3 relationships",
            "  undirected        0 relationships",
            "Indexes",
            "  node cycles",
            "Constraints",
            "  node Program designation",
            "Journal mode",
            "  wal",
        ]

    def test_labels(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".labels\n")
        finally:
            harness.close()
        assert output.splitlines() == [
            "  ISO               1 node",
            "  Program           3 nodes",
        ]

    def test_reltypes(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".reltypes\n")
        finally:
            harness.close()
        assert output.splitlines() == [
            "  ALLIES_WITH       2 relationships",
            "  GUARDS            1 relationship",
        ]

    def test_indexes(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".indexes\n")
        finally:
            harness.close()
        assert output.splitlines() == ["  node cycles"]

    def test_constraints(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".constraints\n")
        finally:
            harness.close()
        assert output.splitlines() == ["  node Program designation"]

    def test_empty_schema(self) -> None:
        harness = Harness()
        try:
            _, output, _ = harness.run(".schema\n")
        finally:
            harness.close()
        assert output.count("(none)") == 4
        assert "Journal mode" in output
        assert "  memory" in output

    def test_empty_constraints(self) -> None:
        harness = Harness()
        try:
            _, output, _ = harness.run(".constraints\n")
        finally:
            harness.close()
        assert output.strip() == "(none)"


class TestElementCommands:
    """Verify node, relationship, expansion, and path rendering."""

    @pytest.fixture
    def seeded(self, tmp_path: Path) -> Path:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        with Graph.open(path) as graph:
            graph.add_node("SystemMonitor", designation="Rinzler")
        return path

    def test_node_details(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".node 1\n")
        finally:
            harness.close()

        lines = output.splitlines()
        assert lines[0] == "Node 1"
        assert lines[1] == "  labels: Program"
        assert lines[2] == '  properties: {cycles=36, designation="Kevin Flynn"}'
        assert any(line.startswith("    -> :ALLIES_WITH") for line in lines)

    def test_node_shows_incoming_and_self_loop(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".node 3\n")
        finally:
            harness.close()

        assert "<- :ALLIES_WITH" in output
        assert "-> :GUARDS" in output

    def test_missing_node(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            code, _, error = harness.run(".node 999\n")
        finally:
            harness.close()
        assert code == 1
        assert "does not exist" in error

    def test_relationship_details(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".rel 1\n")
        finally:
            harness.close()
        assert output.splitlines() == [
            "Relationship 1",
            "  labels: :ALLIES_WITH",
            "  directed: True",
            "  start: 1",
            "  end: 2",
            "  properties: {since_cycle=2020}",
        ]

    def test_undirected_relationship_introspection(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        with Graph.open(path) as graph:
            first = graph.add_node("Program", designation="Tron")
            second = graph.add_node("Program", designation="Quorra")
            graph.add_relationship(first, ["TRUSTS"], second, directed=False)
        harness = Harness(path)
        try:
            _, node_output, _ = harness.run(".node 1\n")
            _, rel_output, _ = harness.run(".rel 1\n")
        finally:
            harness.close()
        assert "~ :TRUSTS" in node_output
        assert "labels: :TRUSTS" in rel_output
        assert "directed: False" in rel_output

    def test_expand_depth_one(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".expand 1\n")
        finally:
            harness.close()

        lines = output.splitlines()
        assert lines[0].startswith("(:Program {id: 1")
        assert len(lines) == 2
        assert "+-[:ALLIES_WITH]->" in lines[1]

    def test_expand_depth_two(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".expand 1 2\n")
        finally:
            harness.close()

        lines = output.splitlines()
        assert len(lines) == 3
        assert "+-[:ALLIES_WITH]->" in lines[2]
        assert "id: 3" in lines[2]

    def test_expand_cycle_stops(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".expand 3 3\n")
        finally:
            harness.close()

        assert output.count("(:Program {id: 3") == 1
        assert "GUARDS" not in output

    def test_expand_rejects_bad_depth(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            code, _, error = harness.run(".expand 1 -1\n")
        finally:
            harness.close()
        assert code == 1
        assert "non-negative depth" in error

    def test_expand_rejects_non_integer(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            code, _, error = harness.run(".expand 1 many\n")
        finally:
            harness.close()
        assert code == 1
        assert "non-negative depth" in error

    def test_path_between_directions(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, both, _ = harness.run(".path 1 3\n")
            harness.reset()
            _, incoming, _ = harness.run(".path 3 1 INCOMING\n")
            harness.reset()
            _, missing, _ = harness.run(".path 3 1 OUTGOING\n")
        finally:
            harness.close()

        assert both.strip() == "(1)-[:ALLIES_WITH]->(2)-[:ALLIES_WITH]->(3)"
        assert incoming.strip() == ("(3)<-[:ALLIES_WITH]-(2)<-[:ALLIES_WITH]-(1)")
        assert missing.strip() == "no path from 3 to 1"

    def test_path_to_disconnected_node(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".path 1 4\n")
        finally:
            harness.close()
        assert output.strip() == "no path from 1 to 4"

    def test_explain_does_not_execute(self, seeded: Path) -> None:
        harness = Harness(seeded)
        try:
            _, output, _ = harness.run(".explain MATCH (n:Program) WHERE n.cycles = 36 RETURN n\n")
            total = harness.session.execute("MATCH (n:Program) RETURN count(*) AS total").rows[0][
                "total"
            ]
        finally:
            harness.close()

        assert output.strip()
        assert total == 3

    def test_explain_requires_a_statement(self) -> None:
        harness = Harness()
        try:
            code, _, error = harness.run(".explain\n")
        finally:
            harness.close()
        assert code == 1
        assert "usage:" in error


class TestMaintenanceCommands:
    """Verify integrity reports and backup commands."""

    def test_check_ok(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        harness = Harness(path)
        try:
            _, output, _ = harness.run(".check\n")
        finally:
            harness.close()
        assert output.strip() == "ok"

    def test_check_reports_a_problem(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "INSERT INTO relationships (src, dst, directed, props) VALUES (1, 999, 1, '{}')"
            )
            connection.commit()
        finally:
            connection.close()

        harness = Harness(path)
        try:
            _, output, _ = harness.run(".check\n")
        finally:
            harness.close()
        assert "foreign key" in output

    def test_backup_copies(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "backup.db"
        harness = Harness(path)
        try:
            code, output, _ = harness.run(f".backup {destination}\n")
        finally:
            harness.close()

        assert code == 0
        assert "backup written to" in output
        with Graph.open(destination) as copy:
            assert copy.query("MATCH (n) RETURN count(*) AS t").rows[0]["t"] == 3

    def test_backup_refuses_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "backup.db"
        destination.write_text("keep", encoding="utf-8")
        harness = Harness(path)
        try:
            code, _, error = harness.run(f".backup {destination}\n")
        finally:
            harness.close()

        assert code == 1
        assert "already exists" in error
        assert destination.read_text(encoding="utf-8") == "keep"

    def test_backup_refused_during_transaction(self, tmp_path: Path) -> None:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        destination = tmp_path / "backup.db"
        harness = Harness(path)
        try:
            code, _, error = harness.run(f".begin\n.backup {destination}\n")
            still_active = harness.session.in_transaction
            harness.session.rollback()
        finally:
            harness.close()

        assert code == 1
        assert "transaction is active" in error
        assert still_active


class TestReadOnlySession:
    """Verify the read-only session contract."""

    @pytest.fixture
    def seeded(self, tmp_path: Path) -> Path:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        return path

    def test_reads_work(self, seeded: Path) -> None:
        harness = Harness(seeded, readonly=True)
        try:
            code, output, _ = harness.run("MATCH (n:Program) RETURN count(*) AS total;\n")
        finally:
            harness.close()
        assert code == 0
        assert "3" in output

    def test_writes_are_rejected(self, seeded: Path) -> None:
        harness = Harness(seeded, readonly=True)
        try:
            code, _, error = harness.run("CREATE (n:Program {designation: 'Clu'});\n")
            total = harness.session.execute("MATCH (n:Program) RETURN count(*) AS total").rows[0][
                "total"
            ]
        finally:
            harness.close()

        assert code == 1
        assert "read-only" in error
        assert total == 3

    def test_begin_is_rejected(self, seeded: Path) -> None:
        harness = Harness(seeded, readonly=True)
        try:
            code, _, error = harness.run(".begin\n")
        finally:
            harness.close()
        assert code == 1
        assert "read-only" in error

    def test_check_and_backup_work(self, seeded: Path, tmp_path: Path) -> None:
        destination = tmp_path / "backup.db"
        harness = Harness(seeded, readonly=True)
        try:
            _, check, _ = harness.run(".check\n")
            harness.reset()
            code, _, error = harness.run(f".backup {destination}\n")
        finally:
            harness.close()

        assert check.strip() == "ok"
        assert code == 0, error
        assert destination.exists()

    def test_open_keeps_read_only(self, seeded: Path, tmp_path: Path) -> None:
        other = tmp_path / "other.db"
        with Graph.open(other) as graph:
            graph.add_node("Program", designation="Rinzler")
        harness = Harness(seeded, readonly=True)
        try:
            code, _, error = harness.run(
                f".open {other}\nCREATE (n:Program {{designation: 'Clu'}});\n"
            )
        finally:
            harness.close()
        assert code == 1
        assert "read-only" in error

    def test_missing_database(self, tmp_path: Path) -> None:
        with pytest.raises(NotFoundError):
            Harness(tmp_path / "missing.db", readonly=True)


class TestModeDefaults:
    """Verify session defaults from the harness."""

    def test_default_mode_is_table(self) -> None:
        harness = Harness()
        try:
            assert harness.session.mode is OutputMode.TABLE
            assert harness.session.headers is True
            assert harness.session.timer is False
        finally:
            harness.close()


class TestImportCommand:
    """Verify the .import dot-command and its guards."""

    @pytest.fixture
    def seeded(self, tmp_path: Path) -> Path:
        path = tmp_path / "grid.db"
        Fixtures.seed(path)
        return path

    def test_help_for_import(self) -> None:
        harness = Harness()
        try:
            code, output, _ = harness.run(".help import\n")
        finally:
            harness.close()
        assert code == 0
        assert "--statement" in output

    def test_import_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "programs.jsonl"
        path.write_text(
            '{"designation": "Kevin Flynn", "cycles": 36}\n'
            '{"designation": "Quorra", "cycles": 37}\n',
            encoding="utf-8",
        )
        harness = Harness()
        try:
            code, output, error = harness.run(
                f'.import {path} --statement "UNWIND $rows AS row '
                f"MERGE (n:Program {{designation: row.designation}}) "
                f'ON CREATE SET n.cycles = row.cycles"\n'
                "MATCH (n:Program) RETURN n.designation AS name ORDER BY name;\n"
            )
        finally:
            harness.close()
        assert code == 0, error
        assert "imported 2 rows in 1 batches" in output
        assert "Kevin Flynn" in output

    def test_import_csv_with_explicit_format(self, tmp_path: Path) -> None:
        path = tmp_path / "programs.txt"
        path.write_text("designation,cycles\nTron,40\n", encoding="utf-8")
        harness = Harness()
        try:
            code, output, error = harness.run(
                f'.import {path} --format csv --statement "UNWIND $rows AS row '
                f"CREATE (n:Program {{designation: row.designation, "
                f'cycles: toInteger(row.cycles)}})"\n'
            )
        finally:
            harness.close()
        assert code == 0, error
        assert "imported 1 rows in 1 batches" in output

    def test_import_batch_and_atomic_options(self, tmp_path: Path) -> None:
        path = tmp_path / "programs.jsonl"
        path.write_text(
            '{"designation": "Tron"}\n{"designation": "Clu"}\n',
            encoding="utf-8",
        )
        harness = Harness()
        try:
            code, output, error = harness.run(
                f".import {path} --batch 1 --atomic --statement "
                f'"UNWIND $rows AS row MERGE (n:Program {{designation: row.designation}})"\n'
            )
        finally:
            harness.close()
        assert code == 0, error
        assert "2 batches" in output

    def test_missing_statement_is_a_usage_error(self, tmp_path: Path) -> None:
        path = tmp_path / "programs.jsonl"
        path.write_text('{"designation": "Tron"}\n', encoding="utf-8")
        harness = Harness()
        try:
            code, _, error = harness.run(f".import {path}\n")
        finally:
            harness.close()
        assert code == 1
        assert "usage:" in error

    def test_invalid_batch_size(self, tmp_path: Path) -> None:
        path = tmp_path / "programs.jsonl"
        path.write_text('{"designation": "Tron"}\n', encoding="utf-8")
        harness = Harness()
        try:
            code, _, error = harness.run(
                f'.import {path} --batch 0 --statement "UNWIND $rows AS row CREATE (n:Program)"\n'
            )
        finally:
            harness.close()
        assert code == 1
        assert "--batch" in error

    def test_unknown_option(self, tmp_path: Path) -> None:
        path = tmp_path / "programs.jsonl"
        path.write_text('{"designation": "Tron"}\n', encoding="utf-8")
        harness = Harness()
        try:
            code, _, error = harness.run(f".import {path} --bogus\n")
        finally:
            harness.close()
        assert code == 1
        assert "unknown .import option" in error

    def test_import_during_a_transaction_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "programs.jsonl"
        path.write_text('{"designation": "Tron"}\n', encoding="utf-8")
        harness = Harness()
        try:
            code, _, error = harness.run(
                ".begin\n"
                f'.import {path} --statement "UNWIND $rows AS row '
                f'MERGE (n:Program {{designation: row.designation}})"\n'
                ".rollback\n"
            )
        finally:
            harness.close()
        assert code == 1
        assert "transaction" in error

    def test_import_in_read_only_session(self, seeded: Path, tmp_path: Path) -> None:
        path = tmp_path / "programs.jsonl"
        path.write_text('{"designation": "Tron"}\n', encoding="utf-8")
        harness = Harness(seeded, readonly=True)
        try:
            code, _, error = harness.run(
                f'.import {path} --statement "UNWIND $rows AS row '
                f'MERGE (n:Program {{designation: row.designation}})"\n'
            )
        finally:
            harness.close()
        assert code == 1
        assert "read-only" in error

    def test_failure_reports_context_and_keeps_the_session_usable(self, tmp_path: Path) -> None:
        path = tmp_path / "programs.jsonl"
        path.write_text(
            '{"designation": "Tron", "cycles": 40}\n{"designation": "Clu", "cycles": {"bad": 1}}\n',
            encoding="utf-8",
        )
        harness = Harness()
        try:
            code, _, error = harness.run(
                f'.import {path} --statement "UNWIND $rows AS row '
                f"CREATE (n:Program {{designation: row.designation, "
                f'cycles: row.cycles}})"\n'
            )
            assert code == 1
            usable, output, _ = harness.run("MATCH (n:Program) RETURN count(*) AS total;\n")
        finally:
            harness.close()
        assert usable == 0
        assert "while importing" in error
        assert "row 2" in error
        assert "0" in output
