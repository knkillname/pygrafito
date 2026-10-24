# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Dot-commands for the graph shell."""

import json
import typing
from pathlib import Path

from pygrafito import Direction, Node, Relationship, TransactionError, ValidationError
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
        "mode": ("table|json|jsonl|csv|line", "select the output mode"),
        "headers": ("on|off", "show or hide column names"),
        "timer": ("on|off", "report statement timing"),
        "output": ("PATH|off", "redirect results to a file"),
        "once": ("PATH", "redirect the next result to a file"),
        "param": ("NAME=JSON", "bind a query parameter"),
        "begin": ("", "start a transaction"),
        "commit": ("", "commit the active transaction"),
        "rollback": ("", "roll back the active transaction"),
        "schema": ("", "summarize labels, relationship types, and indexes"),
        "labels": ("", "list labels and node counts"),
        "reltypes": ("", "list relationship types and counts"),
        "indexes": ("", "list declared indexes"),
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

    def __init__(self, session: Session, shell: Shell) -> None:
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
        self._session.set_output(argument)
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
        types = self._type_inventory()
        indexes = self._session.graph.indexes()
        lines = ["Labels"]
        lines.extend(
            self._schema_label_line(label, labels[label], keys[label]) for label in sorted(labels)
        )
        if not labels:
            lines.append("  (none)")
        lines.append("Relationship types")
        lines.extend(
            f"  {rel_type:<{self.WIDTH}}{self._count(count, 'relationship')}"
            for rel_type, count in sorted(types.items())
        )
        if not types:
            lines.append("  (none)")
        lines.append("Indexes")
        lines.extend(f"  {index.kind.value} {index.key}" for index in indexes)
        if not indexes:
            lines.append("  (none)")
        self._session.emit_lines(lines)
        return True

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
        types = self._type_inventory()
        lines = [
            f"  {rel_type:<{self.WIDTH}}{self._count(count, 'relationship')}"
            for rel_type, count in sorted(types.items())
        ]
        self._session.emit_lines(lines or ["  (none)"])
        return True

    def _command_indexes(self, _argument: str) -> bool:
        indexes = self._session.graph.indexes()
        lines = [f"  {index.kind.value} {index.key}" for index in indexes]
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
            incoming = relationship.end_id == node.id
            arrow = "<-" if incoming and relationship.start_id != node.id else "->"
            lines.append(
                f"    {arrow} {relationship.rel_type} {self._formatter.cell(neighbor)}"
                f" id={relationship.id}"
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
            f"  type: {relationship.rel_type}",
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

    def _type_inventory(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        result = self._session.execute("MATCH ()-[r]->() RETURN type(r) AS type")
        for row in result.rows:
            rel_type = typing.cast(str, row["type"])
            counts[rel_type] = counts.get(rel_type, 0) + 1
        return counts

    def _incident(self, node_id: int) -> list[tuple[Relationship, Node]]:
        result = self._session.execute(f"MATCH (n)-[r]-(m) WHERE id(n) = {node_id} RETURN r, m")
        found: dict[int, tuple[Relationship, Node]] = {}
        for row in result.rows:
            relationship = typing.cast(Relationship, row["r"])
            found[relationship.id] = (relationship, typing.cast(Node, row["m"]))
        ordered = sorted(found, key=lambda value: (found[value][0].rel_type, value))
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
                    for key in sorted(bucket, key=lambda value: (bucket[value][0].rel_type, value))
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
            arrow = "->" if relationship.start_id == node.id else "<-"
            lines.append(
                f"{prefix}+-[:{relationship.rel_type}]{arrow} {self._formatter.cell(neighbor)}"
            )
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

    @staticmethod
    def _required(argument: str, usage: str) -> str:
        if not argument:
            message = f"usage: {usage}"
            raise ValidationError(message)
        return argument

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
