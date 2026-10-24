# graph-constraints Specification

## Purpose

Defines uniqueness constraints over stored property values: how a caller declares, lists, and
removes them, how they persist, how the database enforces them on every write, and how a
violation is reported.

## Requirements

### Requirement: Declared node uniqueness constraint

The system SHALL let a caller declare that nodes carrying one label hold distinct values for one
property key. A declaration SHALL require a non-empty label and a non-empty property key and
SHALL be idempotent. Invalid input SHALL raise a validation error and declare nothing.

#### Scenario: Declare a node constraint

- **WHEN** a caller declares a constraint on label `Program` and property key `designation`
- **THEN** the constraint is reported among the declared constraints with the node element kind,
  the label, and the key

#### Scenario: Declare twice

- **WHEN** a caller declares the same node constraint twice
- **THEN** both calls succeed and exactly one constraint is reported

#### Scenario: Empty label

- **WHEN** a caller declares a node constraint with an empty label
- **THEN** the system raises a validation error and reports no new constraint

#### Scenario: Empty property key

- **WHEN** a caller declares a node constraint with an empty property key
- **THEN** the system raises a validation error and reports no new constraint

### Requirement: Declared relationship uniqueness constraint

The system SHALL let a caller declare that relationships of one type hold distinct values for
one property key. A declaration SHALL require a non-empty relationship type and a non-empty
property key and SHALL be idempotent. Invalid input SHALL raise a validation error and declare
nothing.

#### Scenario: Declare a relationship constraint

- **WHEN** a caller declares a constraint on relationship type `ALLIES_WITH` and property key
  `since`
- **THEN** the constraint is reported with the relationship element kind, the type, and the key

#### Scenario: Declaring twice

- **WHEN** a caller declares the same relationship constraint twice
- **THEN** both calls succeed and exactly one constraint is reported

### Requirement: Constraint listing and removal

The system SHALL report every declared constraint with its element kind, scope name, and
property key, and SHALL remove a declared constraint on request. A constraint SHALL remain until
removed. Removing a constraint that is not declared SHALL raise a not-found error and change no
data.

#### Scenario: List declared constraints

- **WHEN** a caller declares a node constraint and a relationship constraint and lists them
- **THEN** both are reported with their element kinds, scope names, and keys

#### Scenario: Remove a constraint

- **WHEN** a caller removes a declared constraint and lists the constraints again
- **THEN** the removed constraint is no longer reported and graph content is unchanged

#### Scenario: Remove a missing constraint

- **WHEN** a caller removes a constraint that was never declared
- **THEN** the system raises a not-found error

### Requirement: Constraint persistence

Declared constraints SHALL persist in a file-backed database and SHALL be reported and enforced
after the graph is reopened without being declared again. Declaring or removing a constraint
SHALL NOT change the recorded schema version.

#### Scenario: Reopen with declared constraints

- **WHEN** a caller declares a constraint, closes the graph, and opens the same path again
- **THEN** the constraint is reported and still enforced

#### Scenario: Schema version unchanged

- **WHEN** a caller declares and removes constraints on an existing database
- **THEN** the recorded schema version is the same as before the declarations

### Requirement: Type-sensitive uniqueness

A constraint SHALL compare stored values by type and value, so that booleans, integers, floats,
and strings never share a value. An element that does not carry the scope label or type, or that
does not have the property, SHALL be exempt.

#### Scenario: Boolean does not collide with integer

- **WHEN** a constrained node holds `true` and a second node with the label is given `1`
- **THEN** both are stored, and giving the second node `true` fails

#### Scenario: Integer does not collide with float

- **WHEN** a constrained node holds `1` and a second node with the label is given `1.0`
- **THEN** both are stored

#### Scenario: String does not collide with number

- **WHEN** a constrained node holds `"1"` and a second node with the label is given `1`
- **THEN** both are stored

#### Scenario: Missing property is exempt

- **WHEN** two nodes with the constrained label both lack the property
- **THEN** both are stored

#### Scenario: Outside the scope is exempt

- **WHEN** a node without the constrained label holds the same value as a node with the label
- **THEN** both are stored

#### Scenario: List values compared by content and order

- **WHEN** a constrained node holds `["ISO", "Grid"]` and another is given the same list
- **THEN** the second write fails, and a list with the same items in another order is stored

### Requirement: Enforcement on every write

The database SHALL enforce every declared constraint on every write, including element creation,
property assignment and removal, label acquisition, statement-driven writes, and batch imports.
A write that would create a duplicate SHALL fail and change nothing. Deleting the holder SHALL
release the value.

#### Scenario: Create a duplicate

- **WHEN** a caller creates a node with the constrained label and a value already held in scope
- **THEN** the creation fails and no node is stored

#### Scenario: Assign a duplicate value

- **WHEN** a caller sets the constrained property on a labeled node to a value held in scope
- **THEN** the assignment fails and the element keeps its previous value

#### Scenario: Acquire the label

- **WHEN** a node already holding a duplicate value is given the constrained label
- **THEN** the label addition fails and the node keeps its previous labels

#### Scenario: Statement-driven upsert

- **WHEN** a `MERGE` matches an existing element and does not change the constrained property
- **THEN** the statement succeeds without a violation

#### Scenario: Batch import

- **WHEN** the second row of a batch repeats a value already written in that batch
- **THEN** the batch fails and reports the row that caused the violation

#### Scenario: Delete releases the value

- **WHEN** a caller deletes the only element holding a value and then stores that value again
- **THEN** the second write succeeds

### Requirement: Immediate enforcement

A violation SHALL fail the statement that causes it, not the transaction's commit. A transaction
SHALL NOT hold a transient duplicate, and a failed statement SHALL undo only its own changes
while leaving the transaction usable.

#### Scenario: Two duplicates in one transaction

- **WHEN** a transaction creates a value and then creates the same value again
- **THEN** the second creation fails, the first remains, and the transaction can still commit

#### Scenario: Swapping values fails

- **WHEN** a transaction assigns two elements each other's constrained values in one statement
- **THEN** the statement fails because it passes through a duplicate

#### Scenario: Rollback keeps the graph unchanged

- **WHEN** a transaction that hit a violation is rolled back
- **THEN** every value in the constrained scope is what it was before the transaction

### Requirement: Violation reporting

A violation SHALL raise a constraint-violation error carrying the element kind, the scope name,
the property key, the offending value, and the identifier of the existing element that holds the
value when one survives. A storage failure that is not a uniqueness violation SHALL NOT raise
this error.

#### Scenario: Existing holder named

- **WHEN** a write duplicates a value held by an existing element
- **THEN** the error names that element's identifier together with the scope and the value

#### Scenario: Duplicate removed with the statement

- **WHEN** the duplicate was created and rolled back within the same statement
- **THEN** the error reports no existing element and still names the scope and the value

#### Scenario: Unrelated integrity failure

- **WHEN** a write fails because a node still has relationships
- **THEN** the system does not report a constraint violation

### Requirement: Declaration over existing data

Declaring a constraint SHALL validate existing elements in the same write transaction that
creates it. When existing data violates the constraint, the declaration SHALL raise the
constraint-violation error and SHALL create nothing.

#### Scenario: Conflicting data refuses declaration

- **WHEN** a caller declares a constraint over a scope that already holds two equal values
- **THEN** the declaration raises the constraint-violation error and no constraint is reported

#### Scenario: Clean data accepts declaration

- **WHEN** a caller declares a constraint over a scope whose values are all distinct
- **THEN** the declaration succeeds and the constraint is reported

### Requirement: Constraint changes outside transactions

Declaring or removing a constraint SHALL raise a transaction error while an explicit transaction
is active on the same handle, and a read-only error on a read-only handle. Listing constraints
SHALL remain available on a read-only handle.

#### Scenario: Declare inside a transaction

- **WHEN** a caller declares a constraint while an explicit transaction is active
- **THEN** the system raises a transaction error and declares nothing

#### Scenario: Remove inside a transaction

- **WHEN** a caller removes a constraint while an explicit transaction is active
- **THEN** the system raises a transaction error and the constraint remains

#### Scenario: Declare on a read-only handle

- **WHEN** a caller declares a constraint on a read-only handle
- **THEN** the system raises a read-only error and declares nothing

#### Scenario: List on a read-only handle

- **WHEN** a caller lists constraints on a read-only handle
- **THEN** the declared constraints are reported
