# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Mutation stages for write clauses.

The executor applies write clauses to the bindings produced by ``MATCH``. Each
clause first converts its input rows into deduplicated operations keyed by
entity identity, then applies every operation once. This keeps a statement that
binds the same entity through several rows from writing it several times.
"""

import dataclasses
import typing
from collections.abc import Mapping, Sequence

from pygrafito.engine.query.ast import (
    Create,
    Delete,
    PropertyEntry,
    Remove,
    Set,
)
from pygrafito.engine.query.results import MutationSummary
from pygrafito.engine.query.values import ExpressionEvaluator, QueryValue
from pygrafito.model import (
    Node,
    Path,
    QueryExecutionError,
    Relationship,
    Value,
)
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository

type Binding = dict[str, QueryValue]
type EntityKey = tuple[str, int]

NODE = "node"
RELATIONSHIP = "relationship"


@dataclasses.dataclass(slots=True)
class MutationTally:
    """Mutable counters for the operations applied by one statement."""

    created_nodes: int = 0
    created_relationships: int = 0
    deleted_nodes: int = 0
    deleted_relationships: int = 0
    properties_set: int = 0
    properties_removed: int = 0
    labels_added: int = 0
    labels_removed: int = 0

    def summary(self) -> MutationSummary:
        """Return an immutable snapshot of the counters.

        Returns
        -------
        MutationSummary
            Counts of the operations applied so far.
        """
        return MutationSummary(
            created_nodes=self.created_nodes,
            created_relationships=self.created_relationships,
            deleted_nodes=self.deleted_nodes,
            deleted_relationships=self.deleted_relationships,
            properties_set=self.properties_set,
            properties_removed=self.properties_removed,
            labels_added=self.labels_added,
            labels_removed=self.labels_removed,
        )


class MutationExecutor:
    """Apply write clauses to a binding sequence.

    Parameters
    ----------
    nodes : NodeRepository
        Repository used for node writes.
    relationships : RelationshipRepository
        Repository used for relationship writes.
    """

    def __init__(
        self,
        nodes: NodeRepository,
        relationships: RelationshipRepository,
    ) -> None:
        self._nodes = nodes
        self._relationships = relationships
        self._tally = MutationTally()

    @property
    def summary(self) -> MutationSummary:
        """Return the counts of the operations applied so far.

        Returns
        -------
        MutationSummary
            Immutable snapshot of the counters.
        """
        return self._tally.summary()

    def apply(
        self,
        clauses: Sequence[object],
        bindings: Sequence[Binding],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> list[Binding]:
        """Apply every write clause in source order.

        Parameters
        ----------
        clauses : Sequence[object]
            Candidate clauses; non-write clauses are ignored.
        bindings : Sequence[Binding]
            Input bindings.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        list[Binding]
            Bindings after every write clause.
        """
        current = list(bindings)
        for clause in clauses:
            if isinstance(clause, Create):
                current = self._create(clause, current, evaluator, parameters)
            elif isinstance(clause, Set):
                current = self._set(clause, current, evaluator, parameters)
            elif isinstance(clause, Remove):
                current = self._remove(clause, current)
            elif isinstance(clause, Delete):
                current = self._delete(clause, current)
        return current

    def _create(
        self,
        clause: Create,
        bindings: Sequence[Binding],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> list[Binding]:
        """Create the elements of one ``CREATE`` clause per input row.

        Parameters
        ----------
        clause : Create
            Clause to apply.
        bindings : Sequence[Binding]
            Input bindings.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        list[Binding]
            Bindings extended with the created elements.
        """
        result: list[Binding] = []
        for binding in bindings:
            nodes: list[Node] = []
            created: Binding = {}
            for node in clause.pattern.nodes:
                existing = self._reference_node(node.variable, binding)
                if existing is not None:
                    nodes.append(existing)
                    continue
                properties = self._constant_properties(node.properties, evaluator, parameters)
                new_node = self._nodes.create(node.labels, properties)
                self._tally.created_nodes += 1
                nodes.append(new_node)
                if node.variable is not None:
                    created[node.variable] = new_node
            for index, relationship in enumerate(clause.pattern.relationships):
                properties = self._constant_properties(
                    relationship.properties,
                    evaluator,
                    parameters,
                )
                new_relationship = self._relationships.create(
                    nodes[index].id,
                    relationship.types[0],
                    nodes[index + 1].id,
                    properties,
                )
                self._tally.created_relationships += 1
                if relationship.variable is not None:
                    created[relationship.variable] = new_relationship
            extended = dict(binding)
            extended.update(created)
            result.append(extended)
        return result

    @staticmethod
    def _reference_node(variable: str | None, binding: Mapping[str, QueryValue]) -> Node | None:
        """Return an already bound node referenced by a create pattern.

        Parameters
        ----------
        variable : str | None
            Pattern variable, or ``None`` for an anonymous creation site.
        binding : Mapping[str, QueryValue]
            Current binding.

        Returns
        -------
        Node | None
            Bound node, or ``None`` when the pattern creates a node.
        """
        if variable is None:
            return None
        value = binding.get(variable)
        if value is None:
            return None
        if not isinstance(value, Node):
            message = f"variable {variable!r} is not a node"
            raise QueryExecutionError(message)
        return value

    def _constant_properties(
        self,
        entries: Sequence[PropertyEntry],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> dict[str, Value]:
        """Evaluate a create pattern's property map.

        Parameters
        ----------
        entries : Sequence[PropertyEntry]
            Pattern property entries.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        dict[str, Value]
            Stored properties; null entries are ignored.
        """
        properties: dict[str, Value] = {}
        for entry in entries:
            value = evaluator.evaluate(entry.value, {}, parameters)
            if value is None:
                continue
            properties[entry.key] = typing.cast(Value, value)
        return properties

    def _set(
        self,
        clause: Set,
        bindings: Sequence[Binding],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> list[Binding]:
        """Apply one ``SET`` clause and refresh the affected snapshots.

        Parameters
        ----------
        clause : Set
            Clause to apply.
        bindings : Sequence[Binding]
            Input bindings.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        list[Binding]
            Bindings with refreshed element snapshots.
        """
        properties: dict[EntityKey, dict[str, Value | None]] = {}
        labels: dict[int, set[str]] = {}
        for binding in bindings:
            for assignment in clause.assignments:
                key, _target = self._target(binding, assignment.variable)
                value = evaluator.evaluate(assignment.value, binding, parameters)
                slot = properties.setdefault(key, {})
                slot[assignment.key] = typing.cast(Value | None, value)
            for addition in clause.labels:
                key, target = self._target(binding, addition.variable)
                if key[0] != NODE or not isinstance(target, Node):
                    message = "labels can only be added to nodes"
                    raise QueryExecutionError(message)
                labels.setdefault(key[1], set()).update(addition.labels)
        updates = self._apply_properties(properties)
        updates.update(self._apply_labels(labels))
        return self._refresh(bindings, updates)

    def _remove(
        self,
        clause: Remove,
        bindings: Sequence[Binding],
    ) -> list[Binding]:
        """Apply one ``REMOVE`` clause and refresh the affected snapshots.

        Parameters
        ----------
        clause : Remove
            Clause to apply.
        bindings : Sequence[Binding]
            Input bindings.

        Returns
        -------
        list[Binding]
            Bindings with refreshed element snapshots.
        """
        removals: dict[EntityKey, list[str]] = {}
        labels: dict[int, set[str]] = {}
        for binding in bindings:
            for removal in clause.properties:
                key, _target = self._target(binding, removal.variable)
                keys = removals.setdefault(key, [])
                if removal.key not in keys:
                    keys.append(removal.key)
            for removal in clause.labels:
                key, target = self._target(binding, removal.variable)
                if key[0] != NODE or not isinstance(target, Node):
                    message = "labels can only be removed from nodes"
                    raise QueryExecutionError(message)
                labels.setdefault(key[1], set()).update(removal.labels)
        updates: dict[EntityKey, Node | Relationship] = {}
        for (kind, entity_id), keys in removals.items():
            updated = self._remove_properties(kind, entity_id, keys)
            updates[(kind, entity_id)] = updated
            self._tally.properties_removed += len(keys)
        for entity_id, names in labels.items():
            updates[(NODE, entity_id)] = self._nodes.remove_labels(entity_id, sorted(names))
            self._tally.labels_removed += len(names)
        return self._refresh(bindings, updates)

    def _delete(self, clause: Delete, bindings: Sequence[Binding]) -> list[Binding]:
        """Apply one ``DELETE`` clause, keeping the pre-deletion snapshots.

        Parameters
        ----------
        clause : Delete
            Clause to apply.
        bindings : Sequence[Binding]
            Input bindings.

        Returns
        -------
        list[Binding]
            The input bindings, unchanged.
        """
        relationship_ids: list[int] = []
        node_ids: list[int] = []
        for binding in bindings:
            for name in clause.variables:
                value = binding.get(name)
                if isinstance(value, Relationship):
                    if value.id not in relationship_ids:
                        relationship_ids.append(value.id)
                elif isinstance(value, Node):
                    if value.id not in node_ids:
                        node_ids.append(value.id)
                else:
                    message = f"DELETE cannot remove variable {name!r}"
                    raise QueryExecutionError(message)
        for relationship_id in relationship_ids:
            self._relationships.delete(relationship_id)
            self._tally.deleted_relationships += 1
        for node_id in node_ids:
            if clause.detach:
                self._tally.deleted_relationships += self._relationships.delete_incident(node_id)
            self._nodes.delete(node_id)
            self._tally.deleted_nodes += 1
        return list(bindings)

    def _apply_properties(
        self,
        properties: Mapping[EntityKey, Mapping[str, Value | None]],
    ) -> dict[EntityKey, Node | Relationship]:
        """Apply deduplicated property assignments once per entity.

        Parameters
        ----------
        properties : Mapping[EntityKey, Mapping[str, Value | None]]
            Assignments keyed by entity, with the last row's value per key.

        Returns
        -------
        dict[EntityKey, Node | Relationship]
            Updated snapshots keyed by entity.
        """
        updates: dict[EntityKey, Node | Relationship] = {}
        for key, values in properties.items():
            kind, entity_id = key
            if kind == NODE:
                updates[key] = self._nodes.set_properties(entity_id, values)
            else:
                updates[key] = self._relationships.set_properties(entity_id, values)
            for value in values.values():
                if value is None:
                    self._tally.properties_removed += 1
                else:
                    self._tally.properties_set += 1
        return updates

    def _apply_labels(self, labels: Mapping[int, set[str]]) -> dict[EntityKey, Node]:
        """Apply deduplicated label additions once per node.

        Parameters
        ----------
        labels : Mapping[int, set[str]]
            Labels to add, keyed by node id.

        Returns
        -------
        dict[EntityKey, Node]
            Updated node snapshots keyed by entity.
        """
        updates: dict[EntityKey, Node] = {}
        for node_id, names in labels.items():
            updates[(NODE, node_id)] = self._nodes.add_labels(node_id, sorted(names))
            self._tally.labels_added += len(names)
        return updates

    def _remove_properties(
        self,
        kind: str,
        entity_id: int,
        keys: Sequence[str],
    ) -> Node | Relationship:
        """Remove keys from one entity.

        Parameters
        ----------
        kind : str
            Entity kind, either ``node`` or ``relationship``.
        entity_id : int
            Entity identifier.
        keys : Sequence[str]
            Keys to remove.

        Returns
        -------
        Node | Relationship
            Updated snapshot.
        """
        if kind == NODE:
            return self._nodes.remove_properties(entity_id, keys)
        return self._relationships.remove_properties(entity_id, keys)

    @staticmethod
    def _target(binding: Mapping[str, QueryValue], name: str) -> tuple[EntityKey, object]:
        """Resolve a write target to its kind and snapshot.

        Parameters
        ----------
        binding : Mapping[str, QueryValue]
            Current binding.
        name : str
            Bound variable name.

        Returns
        -------
        tuple[EntityKey, object]
            Entity key and the current snapshot.

        Raises
        ------
        QueryExecutionError
            If the variable is not bound to a node or relationship.
        """
        value = binding.get(name)
        if isinstance(value, Node):
            return (NODE, value.id), value
        if isinstance(value, Relationship):
            return (RELATIONSHIP, value.id), value
        message = f"{name!r} is not a node or relationship"
        raise QueryExecutionError(message)

    def _refresh(
        self,
        bindings: Sequence[Binding],
        updates: Mapping[EntityKey, Node | Relationship],
    ) -> list[Binding]:
        """Replace stale element snapshots in every binding.

        Parameters
        ----------
        bindings : Sequence[Binding]
            Bindings to refresh.
        updates : Mapping[EntityKey, Node | Relationship]
            Updated snapshots keyed by entity.

        Returns
        -------
        list[Binding]
            Refreshed bindings.
        """
        if not updates:
            return list(bindings)
        return [
            {name: self._refresh_value(value, updates) for name, value in binding.items()}
            for binding in bindings
        ]

    def _refresh_value(
        self,
        value: QueryValue,
        updates: Mapping[EntityKey, Node | Relationship],
    ) -> QueryValue:
        """Replace one stale value.

        Parameters
        ----------
        value : QueryValue
            Binding value.
        updates : Mapping[EntityKey, Node | Relationship]
            Updated snapshots keyed by entity.

        Returns
        -------
        QueryValue
            Refreshed value.
        """
        if isinstance(value, Node):
            return updates.get((NODE, value.id), value)
        if isinstance(value, Relationship):
            return updates.get((RELATIONSHIP, value.id), value)
        if isinstance(value, Path):
            nodes = tuple(
                typing.cast(Node, self._refresh_value(node, updates)) for node in value.nodes
            )
            relationships = tuple(
                typing.cast(Relationship, self._refresh_value(item, updates))
                for item in value.relationships
            )
            if nodes == value.nodes and relationships == value.relationships:
                return value
            return Path(nodes=nodes, relationships=relationships)
        return value


__all__ = [
    "MutationExecutor",
    "MutationTally",
]
