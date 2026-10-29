# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Dot-commands for the graph shell."""

import json
import typing
from pathlib import Path

from pygrafito import (
    Constraint,
    Direction,
    ImportSummary,
    InteropSummary,
    Node,
    Relationship,
    TransactionError,
    ValidationError,
)
from pygrafito.cli.arguments import CommandArguments
from pygrafito.cli.formatting import OutputMode, ValueFormatter
from pygrafito.cli.session import ParameterDecoder, Session

if typing.TYPE_CHECKING:
    from pygrafito.cli.shell import Shell


class Commands:
    """Dispatch and implement dot-commands for one session.

    Parameters
    ----------
    session : Session
        Session the commands operate on.
    shell : Shell
        Shell that runs scripts for ``.read``.
    """

    DESCRIPTIONS: typing.ClassVar[dict[str, tuple[str, str]]] = {
        "help": ("[COMMAND]", "list commands, or describe one command"),
        "quit": ("", "leave the session"),
        "exit": ("", "leave the session"),
        "open": ("PATH", "open another database"),
        "close": ("", "close the current database"),
        "read": ("PATH", "run a script file in this session"),
        "import": (
            "PATH --statement TEXT [--format csv|jsonl] [--batch N] [--atomic]",
            "import rows from a CSV or JSONL file",
        ),
        "export": (
            "PATH [--format jsonl] [--overwrite]",
            "export a JSONL snapshot",
        ),
        "restore": ("PATH [--replace]", "restore a JSONL snapshot"),
        "mode": ("table|json|jsonl|csv|line", "select the output mode"),
        "headers": ("on|off", "show or hide column names"),
        "timer": ("on|off", "report statement timing"),
        "output": ("PATH|off", "redirect results to a file"),
        "once": ("PATH", "redirect the next result to a file"),
        "param": ("NAME=JSON", "bind a query parameter"),
        "begin": ("", "start a transaction"),
        "commit": ("", "commit the active transaction"),
        "rollback": ("", "roll back the active transaction"),
        "schema": ("", "summarize labels, types, indexes, constraints, and journal mode"),
        "labels": ("", "list labels and node counts"),
        "reltypes": ("", "list relationship types and counts"),
        "indexes": ("", "list declared indexes"),
        "constraints": ("", "list declared uniqueness constraints"),
        "node": ("ID", "show one node and its relationships"),
        "rel": ("ID", "show one relationship"),
        "expand": ("ID [DEPTH]", "render a bounded neighborhood tree"),
        "path": ("START END [DIRECTION]", "render the shortest path"),
        "explain": ("STATEMENT", "show a plan without executing"),
        "check": ("", "report structural integrity"),
        "backup": ("PATH", "write a consistent copy of the database"),
    }

    WIDTH: typing.ClassVar[int] = 18
    EXPAND_ARGUMENTS: typing.ClassVar[int] = 2
    PATH_ARGUMENTS: typing.ClassVar[int] = 3
    IMPORT_USAGE: typing.ClassVar[str] = (
        ".import PATH --statement TEXT [--format csv|jsonl] [--batch N] [--atomic]"
    )
    EXPORT_USAGE: typing.ClassVar[str] = ".export PATH [--format jsonl] [--overwrite]"
    RESTORE_USAGE: typing.ClassVar[str] = ".restore PATH [--replace]"

    def __init__(self, session: Session, shell: "Shell") -> None:
        self._session = session
        self._shell = shell
        self._formatter = ValueFormatter(OutputMode.LINE)

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Return the supported command names.

        Returns
        -------
        tuple[str, ...]
            Command names in help order.
        """
        return tuple(cls.DESCRIPTIONS)

    def execute(self, name: str, argument: str) -> bool:
        """Run one dot-command.

        Parameters
        ----------
        name : str
            Command name without the leading dot.
        argument : str
            Command argument text.

        Returns
        -------
        bool
            ``False`` when the session should end.

        Raises
        ------
        ValidationError
            If the command is unknown.
        """
        if name not in self.DESCRIPTIONS:
            message = f'unknown command ".{name}"'
            raise ValidationError(message)
        handler: typing.Callable[[str], bool] = getattr(self, f"_command_{name}")
        return handler(argument)

    def _command_help(self, argument: str) -> bool:
        if argument:
            return self._help_for(argument.lstrip("."))
        width = self.WIDTH - 1
        lines = [
            f"  .{name:<{width}}{description}"
            for name, (_, description) in self.DESCRIPTIONS.items()
        ]
        self._session.emit_lines(["Commands:", *lines])
        return True

    def _help_for(self, name: str) -> bool:
        if name not in self.DESCRIPTIONS:
            message = f'unknown command ".{name}"'
            raise ValidationError(message)
        usage, description = self.DESCRIPTIONS[name]
        line = f".{name} {usage}".rstrip()
        self._session.emit_lines([line, f"  {description}"])
        return True

    def _command_quit(self, _argument: str) -> bool:
        return False

    def _command_exit(self, _argument: str) -> bool:
        return False

    def _command_open(self, argument: str) -> bool:
        path = self._required(argument, ".open PATH")
        self._require_no_transaction(".open")
        self._session.open_database(path)
        return True

    def _command_close(self, _argument: str) -> bool:
        self._require_no_transaction(".close")
        self._session.close_database()
        return True

    def _command_read(self, argument: str) -> bool:
        path = self._required(argument, ".read PATH")
        text = Path(path).read_text(encoding="utf-8")
        self._shell.run_script(text)
        return True

    def _command_import(self, argument: str) -> bool:
        path, statement, format, batch, atomic = self._import_arguments(argument)
        self._require_no_transaction(".import")
        summary = self._session.graph.import_file(
            path,
            statement,
            format=format,
            batch_size=batch,
            atomic=atomic,
        )
        self._session.emit(self._import_summary(summary))
        return True

    @classmethod
    def _import_arguments(cls, argument: str) -> tuple[str, str, str | None, int, bool]:
        """Parse the ``.import`` argument list.

        Parameters
        ----------
        argument : str
            Raw text after the command name.

        Returns
        -------
        tuple[str, str, str | None, int, bool]
            Path, statement, optional format, batch size, and atomic flag.

        Raises
        ------
        ValidationError
            If the arguments are missing, malformed, or unknown.
        """
        parts = cls._import_parts(argument)
        path = ""
        statement: str | None = None
        format: str | None = None
        batch = 1000
        atomic = False
        index = 0
        while index < len(parts):
            part = parts[index]
            if part == "--atomic":
                atomic = True
            elif part in {"--statement", "--format", "--batch"}:
                value, index = cls._import_value(parts, index)
                if part == "--statement":
                    statement = value
                elif part == "--format":
                    format = cls._import_format(value)
                else:
                    batch = cls._import_batch(value)
            elif part.startswith("--"):
                message = f"unknown .import option {part!r}"
                raise ValidationError(message)
            elif path:
                message = f"usage: {cls.IMPORT_USAGE}"
                raise ValidationError(message)
            else:
                path = part
            index += 1
        if not path or statement is None:
            message = f"usage: {cls.IMPORT_USAGE}"
            raise ValidationError(message)
        return path, statement, format, batch, atomic

    @classmethod
    def _import_parts(cls, argument: str) -> list[str]:
        """Split the ``.import`` argument text into quoted parts.

        Parameters
        ----------
        argument : str
            Raw text after the command name.

        Returns
        -------
        list[str]
            Parsed argument parts.

        Raises
        ------
        ValidationError
            If the argument is empty or cannot be split.
        """
        if not argument:
            message = f"usage: {cls.IMPORT_USAGE}"
            raise ValidationError(message)
        try:
            return CommandArguments.split(argument)
        except ValueError as error:
            message = f"could not parse .import arguments: {error}"
            raise ValidationError(message) from error

    @classmethod
    def _import_value(cls, parts: list[str], index: int) -> tuple[str, int]:
        """Return the value following one ``.import`` option.

        Parameters
        ----------
        parts : list[str]
            Parsed argument parts.
        index : int
            Index of the option name.

        Returns
        -------
        tuple[str, int]
            Option value and the index of that value.

        Raises
        ------
        ValidationError
            If the option has no value.
        """
        if index + 1 >= len(parts):
            message = f"usage: {cls.IMPORT_USAGE}"
            raise ValidationError(message)
        return parts[index + 1], index + 1

    @staticmethod
    def _import_format(value: str) -> str:
        """Validate one ``--format`` value.

        Parameters
        ----------
        value : str
            Candidate format.

        Returns
        -------
        str
            ``csv`` or ``jsonl``.

        Raises
        ------
        ValidationError
            If the format is not supported.
        """
        selected = value.lower()
        if selected not in {"csv", "jsonl"}:
            message = "--format must be 'csv' or 'jsonl'"
            raise ValidationError(message)
        return selected

    @staticmethod
    def _import_batch(value: str) -> int:
        """Parse one ``--batch`` value.

        Parameters
        ----------
        value : str
            Candidate batch size.

        Returns
        -------
        int
            Positive batch size.

        Raises
        ------
        ValidationError
            If the value is not a positive integer.
        """
        try:
            batch = int(value)
        except ValueError:
            message = "--batch must be a positive integer"
            raise ValidationError(message) from None
        if batch < 1:
            message = "--batch must be a positive integer"
            raise ValidationError(message)
        return batch

    @staticmethod
    def _import_summary(summary: ImportSummary) -> str:
        """Format one import summary line.

        Parameters
        ----------
        summary : ImportSummary
            Summary returned by the import.

        Returns
        -------
        str
            Human-readable summary line.
        """
        mutations = summary.mutations
        return (
            f"imported {summary.rows} rows in {summary.batches} batches; "
            f"created {mutations.created_nodes} nodes/"
            f"{mutations.created_relationships} relationships; "
            f"deleted {mutations.deleted_nodes} nodes/"
            f"{mutations.deleted_relationships} relationships; "
            f"{mutations.properties_set} properties set, "
            f"{mutations.properties_removed} removed, "
            f"{mutations.labels_added} labels added, "
            f"{mutations.labels_removed} removed"
        )

    def _command_export(self, argument: str) -> bool:
        path, overwrite = self._export_arguments(argument)
        self._require_no_transaction(".export")
        summary = self._session.graph.export_jsonl(path, overwrite=overwrite)
        self._session.emit(self._export_summary(summary, path))
        return True

    @classmethod
    def _export_arguments(cls, argument: str) -> tuple[str, bool]:
        """Parse the ``.export`` argument list.

        Parameters
        ----------
        argument : str
            Raw text after the command name.

        Returns
        -------
        tuple[str, bool]
            Path and overwrite flag.

        Raises
        ------
        ValidationError
            If the path is missing or an option is unknown or malformed.
        """
        parts = cls._snapshot_parts(argument, cls.EXPORT_USAGE)
        path = ""
        overwrite = False
        index = 0
        while index < len(parts):
            part = parts[index]
            if part == "--overwrite":
                overwrite = True
            elif part == "--format":
                if index + 1 >= len(parts):
                    message = f"usage: {cls.EXPORT_USAGE}"
                    raise ValidationError(message)
                cls._export_format(parts[index + 1])
                index += 1
            elif part.startswith("--"):
                message = f"unknown .export option {part!r}"
                raise ValidationError(message)
            elif path:
                message = f"usage: {cls.EXPORT_USAGE}"
                raise ValidationError(message)
            else:
                path = part
            index += 1
        if not path:
            message = f"usage: {cls.EXPORT_USAGE}"
            raise ValidationError(message)
        return path, overwrite

    @staticmethod
    def _export_format(value: str) -> None:
        """Validate one ``.export --format`` value.

        Parameters
        ----------
        value : str
            Candidate format.

        Raises
        ------
        ValidationError
            If the format is not ``jsonl``.
        """
        if value.lower() != "jsonl":
            message = "--format must be 'jsonl'"
            raise ValidationError(message)

    @staticmethod
    def _snapshot_parts(argument: str, usage: str) -> list[str]:
        """Split a snapshot command argument list into quoted parts.

        Parameters
        ----------
        argument : str
            Raw text after the command name.
        usage : str
            Usage line used in error messages.

        Returns
        -------
        list[str]
            Parsed argument parts.

        Raises
        ------
        ValidationError
            If the argument is empty or cannot be split.
        """
        if not argument:
            message = f"usage: {usage}"
            raise ValidationError(message)
        try:
            return CommandArguments.split(argument)
        except ValueError as error:
            message = f"could not parse arguments: {error}"
            raise ValidationError(message) from error

    @staticmethod
    def _export_summary(summary: InteropSummary, path: str) -> str:
        """Format one export summary line.

        Parameters
        ----------
        summary : InteropSummary
            Summary returned by the export.
        path : str
            Destination path.

        Returns
        -------
        str
            Human-readable summary line.
        """
        return (
            f"exported {Commands._count(summary.nodes, 'node')} and "
            f"{Commands._count(summary.relationships, 'relationship')} to {path}"
        )

    def _command_restore(self, argument: str) -> bool:
        path, replace = self._restore_arguments(argument)
        self._require_no_transaction(".restore")
        summary = self._session.graph.restore_jsonl(path, replace=replace)
        self._session.emit(self._restore_summary(summary, path))
        return True

    @classmethod
    def _restore_arguments(cls, argument: str) -> tuple[str, bool]:
        """Parse the ``.restore`` argument list.

        Parameters
        ----------
        argument : str
            Raw text after the command name.

        Returns
        -------
        tuple[str, bool]
            Path and replace flag.

        Raises
        ------
        ValidationError
            If the path is missing or an option is unknown.
        """
        parts = cls._snapshot_parts(argument, cls.RESTORE_USAGE)
        path = ""
        replace = False
        for part in parts:
            if part == "--replace":
                replace = True
            elif part.startswith("--"):
                message = f"unknown .restore option {part!r}"
                raise ValidationError(message)
            elif path:
                message = f"usage: {cls.RESTORE_USAGE}"
                raise ValidationError(message)
            else:
                path = part
        if not path:
            message = f"usage: {cls.RESTORE_USAGE}"
            raise ValidationError(message)
        return path, replace

    @staticmethod
    def _restore_summary(summary: InteropSummary, path: str) -> str:
        """Format one restore summary line.

        Parameters
        ----------
        summary : InteropSummary
            Summary returned by the restore.
        path : str
            Source path.

        Returns
        -------
        str
            Human-readable summary line.
        """
        return (
            f"restored {Commands._count(summary.nodes, 'node')} and "
            f"{Commands._count(summary.relationships, 'relationship')} from {path}"
        )

    def _command_mode(self, argument: str) -> bool:
        mode = OutputMode.from_name(argument or "")
        self._session.set_mode(mode)
        return True

    def _command_headers(self, argument: str) -> bool:
        self._session.set_headers(self._toggle(argument, ".headers on|off"))
        return True

    def _command_timer(self, argument: str) -> bool:
        self._session.set_timer(self._toggle(argument, ".timer on|off"))
        return True

    def _command_output(self, argument: str) -> bool:
        if not argument:
            self._session.emit(self._session.output_description())
            return True
        if argument.lower() in {"off", "stdout"}:
            self._session.set_output(None)
            return True
        try:
            path = CommandArguments.path(argument)
        except ValueError as error:
            message = "usage: .output PATH|off"
            raise ValidationError(message) from error
        if not path:
            message = "usage: .output PATH|off"
            raise ValidationError(message)
        self._session.set_output(path)
        return True

    def _command_once(self, argument: str) -> bool:
        path = self._required(argument, ".once PATH")
        self._session.set_once(path)
        return True

    def _command_param(self, argument: str) -> bool:
        if not argument:
            parameters = self._session.parameters()
            if not parameters:
                self._session.emit("(no parameters)")
                return True
            lines = [
                f"  {name} = {json.dumps(value, ensure_ascii=False)}"
                for name, value in sorted(parameters.items())
            ]
            self._session.emit_lines(lines)
            return True
        name, value = ParameterDecoder.decode(argument)
        self._session.set_parameter(name, value)
        return True

    def _command_begin(self, _argument: str) -> bool:
        if self._session.in_transaction:
            message = "a transaction is already active"
            raise TransactionError(message)
        self._session.begin()
        return True

    def _command_commit(self, _argument: str) -> bool:
        self._session.commit()
        return True

    def _command_rollback(self, _argument: str) -> bool:
        self._session.rollback()
        return True

    def _command_schema(self, _argument: str) -> bool:
        labels, keys = self._node_inventory()
        relationship_labels, directions = self._relationship_inventory()
        indexes = self._session.graph.indexes()
        constraints = self._session.graph.constraints()
        lines = ["Labels"]
        lines.extend(
            self._schema_label_line(label, labels[label], keys[label]) for label in sorted(labels)
        )
        if not labels:
            lines.append("  (none)")
        lines.append("Relationship labels")
        lines.extend(
            f"  {label:<{self.WIDTH}}{self._count(count, 'relationship')}"
            for label, count in sorted(relationship_labels.items())
        )
        if not relationship_labels:
            lines.append("  (none)")
        lines.append("Directions")
        lines.append(
            f"  {'directed':<{self.WIDTH}}{self._count(directions['directed'], 'relationship')}"
        )
        lines.append(
            f"  {'undirected':<{self.WIDTH}}{self._count(directions['undirected'], 'relationship')}"
        )
        lines.append("Indexes")
        lines.extend(f"  {index.kind.value} {index.key}" for index in indexes)
        if not indexes:
            lines.append("  (none)")
        lines.append("Constraints")
        lines.extend(self._constraint_line(constraint) for constraint in constraints)
        if not constraints:
            lines.append("  (none)")
        lines.append("Journal mode")
        lines.append(f"  {self._session.graph.journal_mode}")
        self._session.emit_lines(lines)
        return True

    @staticmethod
    def _constraint_line(constraint: Constraint) -> str:
        return f"  {constraint.kind.value} {constraint.scope} {constraint.key}"

    @staticmethod
    def _relationship_labels(relationship: Relationship) -> str:
        """Render a relationship's labels for introspection.

        Parameters
        ----------
        relationship : Relationship
            Relationship to describe.

        Returns
        -------
        str
            Colon-separated labels, or ``(none)``.
        """
        if not relationship.labels:
            return "(none)"
        return "".join(f":{label}" for label in relationship.labels)

    def _schema_label_line(self, label: str, count: int, keys: set[str]) -> str:
        properties = ", ".join(sorted(keys)) if keys else "(none)"
        return f"  {label:<{self.WIDTH}}{self._count(count, 'node')}   {properties}"

    def _command_labels(self, _argument: str) -> bool:
        labels, _ = self._node_inventory()
        lines = [
            f"  {label:<{self.WIDTH}}{self._count(count, 'node')}"
            for label, count in sorted(labels.items())
        ]
        self._session.emit_lines(lines or ["  (none)"])
        return True

    def _command_reltypes(self, _argument: str) -> bool:
        labels, _directions = self._relationship_inventory()
        lines = [
            f"  {label:<{self.WIDTH}}{self._count(count, 'relationship')}"
            for label, count in sorted(labels.items())
        ]
        self._session.emit_lines(lines or ["  (none)"])
        return True

    def _command_indexes(self, _argument: str) -> bool:
        indexes = self._session.graph.indexes()
        lines = [f"  {index.kind.value} {index.key}" for index in indexes]
        self._session.emit_lines(lines or ["  (none)"])
        return True

    def _command_constraints(self, _argument: str) -> bool:
        constraints = self._session.graph.constraints()
        lines = [self._constraint_line(constraint) for constraint in constraints]
        self._session.emit_lines(lines or ["  (none)"])
        return True

    def _command_node(self, argument: str) -> bool:
        node_id = self._required_id(argument, ".node ID")
        node = self._session.graph.node(node_id)
        relationships = self._incident(node_id)
        lines = [
            f"Node {node.id}",
            f"  labels: {', '.join(sorted(node.labels)) or '(none)'}",
            f"  properties: {self._properties(dict(node))}",
            "  relationships",
        ]
        for relationship, neighbor in relationships:
            labels = self._relationship_labels(relationship)
            if not relationship.directed:
                arrow = "~"
            elif relationship.end_id == node.id and relationship.start_id != node.id:
                arrow = "<-"
            else:
                arrow = "->"
            lines.append(
                f"    {arrow} {labels} {self._formatter.cell(neighbor)} id={relationship.id}"
            )
        if not relationships:
            lines.append("    (none)")
        self._session.emit_lines(lines)
        return True

    def _command_rel(self, argument: str) -> bool:
        relationship_id = self._required_id(argument, ".rel ID")
        relationship = self._session.graph.relationship(relationship_id)
        lines = [
            f"Relationship {relationship.id}",
            f"  labels: {self._relationship_labels(relationship)}",
            f"  directed: {relationship.directed}",
            f"  start: {relationship.start_id}",
            f"  end: {relationship.end_id}",
            f"  properties: {self._properties(dict(relationship))}",
        ]
        self._session.emit_lines(lines)
        return True

    def _command_expand(self, argument: str) -> bool:
        parts = argument.split()
        if not parts or len(parts) > self.EXPAND_ARGUMENTS:
            message = "usage: .expand ID [DEPTH]"
            raise ValidationError(message)
        node_id = self._required_id(parts[0], ".expand ID [DEPTH]")
        depth = self._depth(parts[1]) if len(parts) == self.EXPAND_ARGUMENTS else 1
        root = self._session.graph.node(node_id)
        children = self._expand_tree(root, depth)
        lines = [self._formatter.cell(root)]
        self._render_tree(lines, children, root, "")
        self._session.emit_lines(lines)
        return True

    def _command_path(self, argument: str) -> bool:
        parts = argument.split()
        if len(parts) not in {2, self.PATH_ARGUMENTS}:
            message = "usage: .path START END [OUTGOING|INCOMING|BOTH]"
            raise ValidationError(message)
        start = self._required_id(parts[0], "usage: .path START END [DIRECTION]")
        end = self._required_id(parts[1], "usage: .path START END [DIRECTION]")
        direction = (
            self._direction(parts[2]) if len(parts) == self.PATH_ARGUMENTS else Direction.BOTH
        )
        path = self._session.graph.shortest_path(start, end, direction=direction)
        if path is None:
            self._session.emit(f"no path from {start} to {end}")
            return True
        self._session.emit(self._formatter.cell(path))
        return True

    def _command_explain(self, argument: str) -> bool:
        statement = argument.rstrip().rstrip(";").strip()
        if not statement:
            message = "usage: .explain STATEMENT"
            raise ValidationError(message)
        plan = self._session.explain(statement)
        self._session.emit_lines(plan or ["(no plan)"])
        return True

    def _command_check(self, _argument: str) -> bool:
        problems = self._session.graph.check_integrity()
        self._session.emit_lines(problems or ["ok"])
        return True

    def _command_backup(self, argument: str) -> bool:
        path = self._required(argument, ".backup PATH")
        written = self._session.graph.backup_to(path)
        self._session.emit(f"backup written to {written}")
        return True

    def _node_inventory(self) -> tuple[dict[str, int], dict[str, set[str]]]:
        counts: dict[str, int] = {}
        keys: dict[str, set[str]] = {}
        result = self._session.execute("MATCH (n) RETURN labels(n) AS labels, keys(n) AS keys")
        for row in result.rows:
            labels = typing.cast(list[str], row["labels"])
            properties = typing.cast(list[str], row["keys"])
            for label in labels or ["(none)"]:
                counts[label] = counts.get(label, 0) + 1
                keys.setdefault(label, set()).update(properties)
        return (counts, keys)

    def _relationship_inventory(self) -> tuple[dict[str, int], dict[str, int]]:
        counts: dict[str, int] = {}
        directions = {"directed": 0, "undirected": 0}
        result = self._session.execute("MATCH ()-[r]-() RETURN r")
        found: dict[int, Relationship] = {}
        for row in result.rows:
            relationship = typing.cast(Relationship, row["r"])
            found[relationship.id] = relationship
        for relationship in found.values():
            key = "directed" if relationship.directed else "undirected"
            directions[key] += 1
            for label in relationship.labels or ("(none)",):
                counts[label] = counts.get(label, 0) + 1
        return (counts, directions)

    def _incident(self, node_id: int) -> list[tuple[Relationship, Node]]:
        result = self._session.execute(f"MATCH (n)-[r]-(m) WHERE id(n) = {node_id} RETURN r, m")
        found: dict[int, tuple[Relationship, Node]] = {}
        for row in result.rows:
            relationship = typing.cast(Relationship, row["r"])
            found[relationship.id] = (relationship, typing.cast(Node, row["m"]))
        ordered = sorted(found, key=lambda value: (found[value][0].labels, value))
        return [found[key] for key in ordered]

    def _expand_tree(
        self,
        root: Node,
        depth: int,
    ) -> dict[int, list[tuple[Relationship, Node]]]:
        children: dict[int, list[tuple[Relationship, Node]]] = {}
        visited = {root.id}
        frontier = [root]
        for _ in range(depth):
            if not frontier:
                break
            ids = ", ".join(str(node.id) for node in frontier)
            result = self._session.execute(
                f"MATCH (n)-[r]-(m) WHERE id(n) IN [{ids}] RETURN id(n) AS origin, r, m"
            )
            found: dict[int, dict[int, tuple[Relationship, Node]]] = {}
            for row in result.rows:
                origin = typing.cast(int, row["origin"])
                relationship = typing.cast(Relationship, row["r"])
                neighbor = typing.cast(Node, row["m"])
                bucket = found.setdefault(origin, {})
                bucket[relationship.id] = (relationship, neighbor)
            next_frontier: list[Node] = []
            for node in frontier:
                bucket = found.get(node.id, {})
                ordered = [
                    bucket[key]
                    for key in sorted(bucket, key=lambda value: (bucket[value][0].labels, value))
                ]
                for relationship, neighbor in ordered:
                    if neighbor.id in visited:
                        continue
                    visited.add(neighbor.id)
                    children.setdefault(node.id, []).append((relationship, neighbor))
                    next_frontier.append(neighbor)
            frontier = next_frontier
        return children

    def _render_tree(
        self,
        lines: list[str],
        children: dict[int, list[tuple[Relationship, Node]]],
        node: Node,
        prefix: str,
    ) -> None:
        entries = children.get(node.id, [])
        for position, (relationship, neighbor) in enumerate(entries):
            last = position == len(entries) - 1
            if not relationship.directed:
                arrow = "~"
            else:
                arrow = "->" if relationship.start_id == node.id else "<-"
            labels = self._relationship_labels(relationship)
            lines.append(f"{prefix}+-[{labels}]{arrow} {self._formatter.cell(neighbor)}")
            self._render_tree(
                lines,
                children,
                neighbor,
                prefix + ("  " if last else "| "),
            )

    @staticmethod
    def _properties(properties: dict[str, object]) -> str:
        if not properties:
            return "{}"
        items = ", ".join(
            f"{key}={json.dumps(value, ensure_ascii=False)}"
            for key, value in sorted(properties.items())
        )
        return "{" + items + "}"

    @classmethod
    def _required(cls, argument: str, usage: str) -> str:
        try:
            value = CommandArguments.path(argument)
        except ValueError as error:
            message = f"usage: {usage}"
            raise ValidationError(message) from error
        if not value:
            message = f"usage: {usage}"
            raise ValidationError(message)
        return value

    @classmethod
    def _required_id(cls, argument: str, usage: str) -> int:
        value = cls._required(argument, usage)
        try:
            return int(value)
        except ValueError:
            message = f"expected an integer id, got {value!r}"
            raise ValidationError(message) from None

    @staticmethod
    def _depth(argument: str) -> int:
        try:
            depth = int(argument)
        except ValueError:
            message = f"expected a non-negative depth, got {argument!r}"
            raise ValidationError(message) from None
        if depth < 0:
            message = f"expected a non-negative depth, got {argument!r}"
            raise ValidationError(message)
        return depth

    @staticmethod
    def _direction(argument: str) -> Direction:
        try:
            return Direction(argument.lower())
        except ValueError:
            message = "direction must be OUTGOING, INCOMING, or BOTH"
            raise ValidationError(message) from None

    @staticmethod
    def _toggle(argument: str, usage: str) -> bool:
        lowered = argument.lower()
        if lowered == "on":
            return True
        if lowered == "off":
            return False
        message = f"usage: {usage}"
        raise ValidationError(message)

    @staticmethod
    def _count(count: int, noun: str) -> str:
        suffix = "" if count == 1 else "s"
        return f"{count} {noun}{suffix}"

    def _require_no_transaction(self, command: str) -> None:
        if self._session.in_transaction:
            message = f"{command} is not available while a transaction is active"
            raise TransactionError(message)
