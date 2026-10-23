# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Tests for explicit transaction commit, rollback, and reuse."""

import typing
from collections.abc import Iterator, Sequence
from sqlite3 import Connection, OperationalError

import pytest

from pygrafito.engine.transaction import Transaction
from pygrafito.model import (
    Node,
    Relationship,
    TransactionError,
    ValidationError,
    Value,
)
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository

type Storage = tuple[
    Database,
    NodeRepository,
    RelationshipRepository,
]


class _TransactionTestCase:
    """Provide a database and repositories on an in-memory graph."""

    @pytest.fixture
    def storage(self) -> Iterator[Storage]:
        """Return the database and repositories under test.

        Yields
        ------
        Storage
            Database, node repository, and relationship repository.
        """
        database = Database(":memory:")
        try:
            property_codec = PropertyCodec()
            yield (
                database,
                NodeRepository(database.connection, property_codec),
                RelationshipRepository(database.connection, property_codec),
            )
        finally:
            database.close()

    @staticmethod
    def make_transaction(storage: Storage) -> Transaction:
        """Create a transaction bound to the fixture repositories.

        Parameters
        ----------
        storage : Storage
            Database and repositories under test.

        Returns
        -------
        Transaction
            A fresh transaction object.
        """
        database, node_repository, relationship_repository = storage
        return Transaction(
            database.connection,
            node_repository,
            relationship_repository,
        )


class TestCommit(_TransactionTestCase):
    """Verify committed writes."""

    def test_writes_are_visible_after_commit(self, storage: Storage) -> None:
        database, node_repository, relationship_repository = storage
        with self.make_transaction(storage) as active:
            first = active.add_node("Person", name="Ada")
            second = active.add_node("Person", name="Grace")
            relationship = active.add_relationship(first, "KNOWS", second, since=2020)
            assert database.connection.in_transaction
        assert node_repository.get(first.id)["name"] == "Ada"
        assert relationship_repository.get(relationship.id)["since"] == 2020

    def test_reads_inside_transaction_see_writes(self, storage: Storage) -> None:
        with self.make_transaction(storage) as active:
            node = active.add_node(name="Ada")
            assert active.node(node.id) == node
            relationship = active.add_relationship(node, "KNOWS", node)
            assert active.relationship(relationship.id) == relationship

    def test_property_and_label_updates(self, storage: Storage) -> None:
        _, node_repository, _ = storage
        with self.make_transaction(storage) as active:
            node = active.add_node("Person", name="Ada")
            node = active.add_labels(node, "Employee")
            updated_node = active.set_properties(node, name="Grace", age=36)
            assert isinstance(updated_node, Node)
            without_age = active.remove_properties(updated_node, "age")
            assert isinstance(without_age, Node)
            node = active.remove_labels(without_age, "Person")
        stored = node_repository.get(node.id)
        assert stored.labels == frozenset({"Employee"})
        assert dict(stored) == {"name": "Grace"}

    def test_relationship_property_updates(self, storage: Storage) -> None:
        with self.make_transaction(storage) as active:
            first = active.add_node()
            second = active.add_node()
            relationship = active.add_relationship(first, "KNOWS", second)
            updated_relationship = active.set_properties(relationship, since=2020)
            assert isinstance(updated_relationship, Relationship)
            assert updated_relationship["since"] == 2020
            without_since = active.remove_properties(updated_relationship, "since")
            assert isinstance(without_since, Relationship)
            assert dict(without_since) == {}

    def test_deletes_inside_transaction(self, storage: Storage) -> None:
        _, node_repository, relationship_repository = storage
        with self.make_transaction(storage) as active:
            first = active.add_node()
            second = active.add_node()
            relationship = active.add_relationship(first, "KNOWS", second)
            active.delete(relationship)
            active.delete(second)
            active.delete(first, detach=True)
        assert list(node_repository.all()) == []
        assert list(relationship_repository.all()) == []

    def test_find_inside_transaction(self, storage: Storage) -> None:
        with self.make_transaction(storage) as active:
            active.add_node("Person", name="Ada")
            active.add_node("Robot", name="R2")
            found_nodes = list(active.find_nodes("Person"))
            found_relationships = list(active.find_relationships("KNOWS"))
        assert len(found_nodes) == 1
        assert found_nodes[0]["name"] == "Ada"
        assert found_relationships == []


class TestRollback(_TransactionTestCase):
    """Verify rolled-back writes."""

    @staticmethod
    def _failing_writes(active: Transaction) -> None:
        """Write two nodes and a relationship, then fail.

        Parameters
        ----------
        active : Transaction
            Transaction that should roll back.

        Raises
        ------
        RuntimeError
            Always, to trigger rollback.
        """
        with active:
            first = active.add_node()
            second = active.add_node()
            active.add_relationship(first, "KNOWS", second)
            message = "boom"
            raise RuntimeError(message)

    @staticmethod
    def _invalid_write(active: Transaction) -> None:
        """Write a valid node followed by an invalid value.

        Parameters
        ----------
        active : Transaction
            Transaction that should roll back.

        Raises
        ------
        ValidationError
            Because the second node has a mixed list.
        """
        with active:
            active.add_node(name="Ada")
            active.add_node(bad=typing.cast(Value, [1, "a"]))

    def test_exception_rolls_back_every_write(self, storage: Storage) -> None:
        _, node_repository, relationship_repository = storage
        active = self.make_transaction(storage)
        with pytest.raises(RuntimeError):
            self._failing_writes(active)
        assert list(node_repository.all()) == []
        assert list(relationship_repository.all()) == []

    def test_validation_error_rolls_back_earlier_writes(self, storage: Storage) -> None:
        _, node_repository, _ = storage
        active = self.make_transaction(storage)
        with pytest.raises(ValidationError):
            self._invalid_write(active)
        assert list(node_repository.all()) == []

    def test_transaction_is_inactive_after_rollback(self, storage: Storage) -> None:
        active = self.make_transaction(storage)
        with pytest.raises(RuntimeError):
            self._failing_writes(active)
        with pytest.raises(TransactionError):
            active.add_node()


class TestReuse(_TransactionTestCase):
    """Verify transaction lifecycle errors."""

    def test_transaction_cannot_be_entered_twice(self, storage: Storage) -> None:
        active = self.make_transaction(storage)
        with active, pytest.raises(TransactionError):
            active.__enter__()

    def test_finished_transaction_cannot_be_reused(self, storage: Storage) -> None:
        active = self.make_transaction(storage)
        with active:
            pass
        with pytest.raises(TransactionError), active:
            pass

    def test_methods_require_active_transaction(self, storage: Storage) -> None:
        active = self.make_transaction(storage)
        with pytest.raises(TransactionError):
            active.add_node()
        with pytest.raises(TransactionError):
            active.node(1)

    def test_exit_without_enter_rejected(self, storage: Storage) -> None:
        active = self.make_transaction(storage)
        with pytest.raises(TransactionError):
            active.__exit__(None, None, None)

    def test_invalid_node_argument_rejected(self, storage: Storage) -> None:
        with self.make_transaction(storage) as active:
            with pytest.raises(ValidationError):
                active.add_relationship(typing.cast(Node, True), "KNOWS", 1)
            with pytest.raises(ValidationError):
                active.add_labels(typing.cast(Node, "1"), "Person")

    def test_invalid_element_rejected(self, storage: Storage) -> None:
        missing = typing.cast(Node, "not a node")
        with self.make_transaction(storage) as active:
            with pytest.raises(ValidationError):
                active.set_properties(missing, name="Ada")
            with pytest.raises(ValidationError):
                active.remove_properties(missing, "name")
            with pytest.raises(ValidationError):
                active.delete(missing)


class _FailingConnection:
    """Connection stand-in that fails every statement."""

    in_transaction = False

    def execute(
        self,
        statement: str,
        parameters: Sequence[object] = (),
    ) -> _FailingConnection:
        message = "database is locked"
        raise OperationalError(message)


class _FailingCommitConnection:
    """Connection stand-in that starts a transaction but fails to commit."""

    def __init__(self) -> None:
        self.in_transaction = False

    def execute(
        self,
        statement: str,
        parameters: Sequence[object] = (),
    ) -> _FailingCommitConnection:
        if statement.startswith("BEGIN"):
            self.in_transaction = True
            return self
        if statement.startswith("ROLLBACK"):
            self.in_transaction = False
            return self
        message = "disk I/O error"
        raise OperationalError(message)


class TestSqliteFailures(_TransactionTestCase):
    """Verify SQLite failures are wrapped as transaction errors."""

    def test_begin_failure_is_wrapped(self, storage: Storage) -> None:
        _, node_repository, relationship_repository = storage
        active = Transaction(
            typing.cast(Connection, _FailingConnection()),
            node_repository,
            relationship_repository,
        )
        with pytest.raises(TransactionError):
            active.__enter__()

    def test_commit_failure_is_wrapped(self, storage: Storage) -> None:
        _, node_repository, relationship_repository = storage
        active = Transaction(
            typing.cast(Connection, _FailingCommitConnection()),
            node_repository,
            relationship_repository,
        )
        with pytest.raises(TransactionError), active:
            pass
