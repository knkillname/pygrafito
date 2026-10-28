# Spec Delta

## MODIFIED Requirements

### Requirement: Declared relationship uniqueness constraint

The system SHALL let a caller declare that relationships carrying one label hold distinct values for one property key. A declaration SHALL require a non-empty label and a non-empty property key and SHALL be idempotent. Invalid input SHALL raise a validation error and declare nothing.

#### Scenario: Declare a relationship constraint

- **WHEN** a caller declares a constraint on relationship label `ALLIES_WITH` and property key `since`
- **THEN** the constraint is reported with the relationship element kind, the label, and the key

#### Scenario: Declaring twice

- **WHEN** a caller declares the same relationship constraint twice
- **THEN** both calls succeed and exactly one constraint is reported

#### Scenario: Empty label

- **WHEN** a caller declares a relationship constraint with an empty label
- **THEN** the system raises a validation error and reports no new constraint

#### Scenario: Empty property key

- **WHEN** a caller declares a relationship constraint with an empty property key
- **THEN** the system raises a validation error and reports no new constraint

#### Scenario: Multi-label relationship is subject

- **WHEN** a relationship carries the constrained label and another label
- **THEN** its constrained property value participates in the uniqueness scope

#### Scenario: Relationship without the label is exempt

- **WHEN** a relationship does not carry the constrained label and holds the same value
- **THEN** both relationships are stored

### Requirement: Type-sensitive uniqueness

A constraint SHALL compare stored values by type and value, so that booleans, integers, floats, and strings never share a value. An element that does not carry the scope label, or that does not have the property, SHALL be exempt.

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

#### Scenario: Relationship outside the scope is exempt

- **WHEN** a relationship without the constrained label holds the same value as a relationship with the label
- **THEN** both are stored

#### Scenario: List values compared by content and order

- **WHEN** a constrained node holds `["ISO", "Grid"]` and another is given the same list
- **THEN** the second write fails, and a list with the same items in another order is stored

### Requirement: Enforcement on every write

The database SHALL enforce every declared constraint on every write, including element creation, property assignment and removal, label acquisition and removal, statement-driven writes, and batch imports. A write that would create a duplicate SHALL fail and change nothing. Deleting the holder SHALL release the value.

#### Scenario: Create a duplicate

- **WHEN** a caller creates a node with the constrained label and a value already held in scope
- **THEN** the creation fails and no node is stored

#### Scenario: Assign a duplicate value

- **WHEN** a caller sets the constrained property on a labeled node to a value held in scope
- **THEN** the assignment fails and the element keeps its previous value

#### Scenario: Acquire the label

- **WHEN** a node already holding a duplicate value is given the constrained label
- **THEN** the label addition fails and the node keeps its previous labels

#### Scenario: Acquire the relationship label

- **WHEN** a relationship already holding a duplicate value is given the constrained label
- **THEN** the label addition fails and the relationship keeps its previous labels

#### Scenario: Remove the relationship label

- **WHEN** a caller removes the constrained label from a relationship
- **THEN** the relationship leaves that uniqueness scope

#### Scenario: Statement-driven upsert

- **WHEN** a `MERGE` matches an existing element and does not change the constrained property
- **THEN** the statement succeeds without a violation

#### Scenario: Batch import

- **WHEN** the second row of a batch repeats a value already written in that batch
- **THEN** the batch fails and reports the row that caused the violation

#### Scenario: Delete releases the value

- **WHEN** a caller deletes the only element holding a value and then stores that value again
- **THEN** the second write succeeds
