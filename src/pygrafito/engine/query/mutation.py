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
    Merge,
    PathPattern,
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


class PatternCreator:
    """Create the elements of one path pattern against one input row.

    Parameters
    ----------
    nodes : NodeRepository
        Repository used for node writes.
    relationships : RelationshipRepository
        Repository used for relationship writes.
    tally : MutationTally
        Counters updated by each created element.
    """

    def __init__(
        self,
        nodes: NodeRepository,
        relationships: RelationshipRepository,
        tally: MutationTally,
    ) -> None:
        self._nodes = nodes
        self._relationships = relationships
        self._tally = tally

    def create(
        self,
        pattern: PathPattern,
        binding: Mapping[str, QueryValue],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        *,
        reject_null_properties: bool = False,
    ) -> Binding:
        """Create a pattern and return the extended binding.

        Parameters
        ----------
        pattern : PathPattern
            Pattern whose elements are created.
        binding : Mapping[str, QueryValue]
            Variables bound before the pattern.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        reject_null_properties : bool, optional
            Whether a null property value raises instead of being omitted, by
            default ``False``.

        Returns
        -------
        Binding
            Input variables plus the created and reused elements.

        Raises
        ------
        QueryExecutionError
            If a bound variable is not a node or a merge property is null.
        """
        working: Binding = dict(binding)
        nodes: list[Node] = []
        for node in pattern.nodes:
            existing = self._existing_node(node.variable, working)
            if existing is not None:
                nodes.append(existing)
                continue
            properties = self._properties(
                node.properties,
                working,
                evaluator,
                parameters,
                reject_null_properties=reject_null_properties,
            )
            created = self._nodes.create(node.labels, properties)
            self._tally.created_nodes += 1
            nodes.append(created)
            if node.variable is not None:
                working[node.variable] = created
        for index, relationship in enumerate(pattern.relationships):
            properties = self._properties(
                relationship.properties,
                working,
                evaluator,
                parameters,
                reject_null_properties=reject_null_properties,
            )
            created_relationship = self._relationships.create(
                nodes[index].id,
                relationship.types,
                nodes[index + 1].id,
                properties=properties,
            )
            self._tally.created_relationships += 1
            if relationship.variable is not None:
                working[relationship.variable] = created_relationship
        return working

    @staticmethod
    def _existing_node(
        variable: str | None,
        binding: Mapping[str, QueryValue],
    ) -> Node | None:
        """Return the node already bound to a pattern variable.

        Parameters
        ----------
        variable : str | None
            Pattern variable, or ``None`` for an anonymous node.
        binding : Mapping[str, QueryValue]
            Current binding.

        Returns
        -------
        Node | None
            Bound node, or ``None`` when the position creates a node.

        Raises
        ------
        QueryExecutionError
            If the variable is bound to something other than a node.
        """
        if variable is None or variable not in binding:
            return None
        value = binding[variable]
        if isinstance(value, Node):
            return value
        message = f"variable {variable!r} is not a node"
        raise QueryExecutionError(message)

    @staticmethod
    def _properties(
        entries: Sequence[PropertyEntry],
        binding: Mapping[str, QueryValue],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        *,
        reject_null_properties: bool,
    ) -> dict[str, Value]:
        """Evaluate a pattern property map for one row.

        Parameters
        ----------
        entries : Sequence[PropertyEntry]
            Property entries to evaluate.
        binding : Mapping[str, QueryValue]
            Variables bound so far.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        reject_null_properties : bool
            Whether a null value raises instead of being omitted.

        Returns
        -------
        dict[str, Value]
            Stored properties.

        Raises
        ------
        QueryExecutionError
            If a null value is rejected.
        """
        properties: dict[str, Value] = {}
        for entry in entries:
            value = evaluator.evaluate(entry.value, binding, parameters)
            if value is None:
                if reject_null_properties:
                    message = f"MERGE pattern property {entry.key!r} is null"
                    raise QueryExecutionError(message)
                continue
            properties[entry.key] = typing.cast(Value, value)
        return properties


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
        matcher: typing.Callable[[PathPattern, Binding], list[Binding]] | None = None,
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
        matcher : typing.Callable[[PathPattern, Binding], list[Binding]] | None, optional
            Callback that matches one pattern for a row, by default ``None``.

        Returns
        -------
        list[Binding]
            Bindings after every write clause.
        """
        current = list(bindings)
        for clause in clauses:
            if isinstance(clause, Create):
                current = self._create(clause, current, evaluator, parameters)
            elif isinstance(clause, Merge):
                current = self._merge(clause, current, evaluator, parameters, matcher)
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
        creator = PatternCreator(self._nodes, self._relationships, self._tally)
        return [
            creator.create(clause.pattern, binding, evaluator, parameters) for binding in bindings
        ]

    def _merge(
        self,
        clause: Merge,
        bindings: Sequence[Binding],
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        matcher: typing.Callable[[PathPattern, Binding], list[Binding]] | None,
    ) -> list[Binding]:
        """Match or create one pattern per input row, in order.

        Parameters
        ----------
        clause : Merge
            Clause to apply.
        bindings : Sequence[Binding]
            Input bindings.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        matcher : typing.Callable[[PathPattern, Binding], list[Binding]] | None
            Callback that matches one pattern against the current database.

        Returns
        -------
        list[Binding]
            One row per match or per created pattern.

        Raises
        ------
        QueryExecutionError
            If no matcher is available or a merge property is null.
        """
        if matcher is None:
            message = "MERGE requires a pattern matcher"
            raise QueryExecutionError(message)
        creator = PatternCreator(self._nodes, self._relationships, self._tally)
        results: list[Binding] = []
        for binding in bindings:
            matches = matcher(clause.pattern, binding)
            if matches:
                for match in matches:
                    row = {**binding, **match}
                    if clause.on_match is not None:
                        row = self._set_row(clause.on_match, row, evaluator, parameters)
                    results.append(row)
                continue
            created = creator.create(
                clause.pattern,
                binding,
                evaluator,
                parameters,
                reject_null_properties=True,
            )
            if clause.on_create is not None:
                created = self._set_row(clause.on_create, created, evaluator, parameters)
            results.append(created)
        return results

    def _set_row(
        self,
        clause: Set,
        binding: Binding,
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
    ) -> Binding:
        """Apply one ``SET`` clause to one row.

        Parameters
        ----------
        clause : Set
            Clause to apply.
        binding : Binding
            Row to update.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        Binding
            The row with refreshed element snapshots.
        """
        properties: dict[EntityKey, dict[str, Value | None]] = {}
        labels: dict[EntityKey, set[str]] = {}
        self._collect_set(clause, binding, evaluator, parameters, properties, labels)
        updates = self._apply_properties(properties)
        updates.update(self._apply_labels(labels))
        return self._refresh([binding], updates)[0]

    def _collect_set(
        self,
        clause: Set,
        binding: Binding,
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        properties: dict[EntityKey, dict[str, Value | None]],
        labels: dict[EntityKey, set[str]],
    ) -> None:
        """Collect one row's ``SET`` assignments into the clause accumulators.

        Parameters
        ----------
        clause : Set
            Clause to apply.
        binding : Binding
            Row to read.
        evaluator : ExpressionEvaluator
            Scalar expression evaluator.
        parameters : Mapping[str, QueryValue]
            Query parameter values.
        properties : dict[EntityKey, dict[str, Value | None]]
            Property assignments keyed by entity.
        labels : dict[EntityKey, set[str]]
            Label additions keyed by entity.
        """
        for assignment in clause.assignments:
            key, _target = self._target(binding, assignment.variable)
            value = evaluator.evaluate(assignment.value, binding, parameters)
            slot = properties.setdefault(key, {})
            slot[assignment.key] = typing.cast(Value | None, value)
        for addition in clause.labels:
            key, target = self._target(binding, addition.variable)
            if not isinstance(target, (Node, Relationship)):
                message = "labels can only be added to nodes or relationships"
                raise QueryExecutionError(message)
            labels.setdefault(key, set()).update(addition.labels)

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
        labels: dict[EntityKey, set[str]] = {}
        for binding in bindings:
            self._collect_set(clause, binding, evaluator, parameters, properties, labels)
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
        labels: dict[EntityKey, set[str]] = {}
        for binding in bindings:
            for removal in clause.properties:
                key, _target = self._target(binding, removal.variable)
                keys = removals.setdefault(key, [])
                if removal.key not in keys:
                    keys.append(removal.key)
            for removal in clause.labels:
                key, target = self._target(binding, removal.variable)
                if not isinstance(target, (Node, Relationship)):
                    message = "labels can only be removed from nodes or relationships"
                    raise QueryExecutionError(message)
                labels.setdefault(key, set()).update(removal.labels)
        updates: dict[EntityKey, Node | Relationship] = {}
        for (kind, entity_id), keys in removals.items():
            updated = self._remove_properties(kind, entity_id, keys)
            updates[(kind, entity_id)] = updated
            self._tally.properties_removed += len(keys)
        for (kind, entity_id), names in labels.items():
            updates[(kind, entity_id)] = self._remove_labels(kind, entity_id, sorted(names))
            self._tally.labels_removed += len(names)
        return self._refresh(bindings, updates)

    def _remove_labels(
        self,
        kind: str,
        entity_id: int,
        names: Sequence[str],
    ) -> Node | Relationship:
        """Remove labels from one element.

        Parameters
        ----------
        kind : str
            Entity kind, either ``node`` or ``relationship``.
        entity_id : int
            Entity identifier.
        names : Sequence[str]
            Labels to remove.

        Returns
        -------
        Node | Relationship
            Snapshot of the updated element.
        """
        if kind == NODE:
            return self._nodes.remove_labels(entity_id, names)
        return self._relationships.remove_labels(entity_id, names)

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

    def _apply_labels(
        self,
        labels: Mapping[EntityKey, set[str]],
    ) -> dict[EntityKey, Node | Relationship]:
        """Apply deduplicated label additions once per element.

        Parameters
        ----------
        labels : Mapping[EntityKey, set[str]]
            Labels to add, keyed by entity.

        Returns
        -------
        dict[EntityKey, Node | Relationship]
            Updated element snapshots keyed by entity.
        """
        updates: dict[EntityKey, Node | Relationship] = {}
        for (kind, entity_id), names in labels.items():
            if kind == NODE:
                updates[(kind, entity_id)] = self._nodes.add_labels(entity_id, sorted(names))
            else:
                updates[(kind, entity_id)] = self._relationships.add_labels(
                    entity_id, sorted(names)
                )
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
