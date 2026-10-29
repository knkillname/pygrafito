# Spec Delta

## ADDED Requirements

### Requirement: Exact real uniqueness

A uniqueness constraint SHALL compare real property values by their exact stored value,
independently of how the SQLite JSON parser converts the canonical number text. Two equal
finite floats SHALL collide even when the parser would round the literal, while
neighboring floats SHALL remain distinct.

#### Scenario: Duplicate tiny real rejected

- **WHEN** a constrained node already holds `2.7710821668887726e-173` and another node in
  the same scope is given that same value
- **THEN** the second write fails with a constraint violation and changes nothing

#### Scenario: Neighboring tiny reals both stored

- **WHEN** a constrained node holds a finite float and another node in the same scope is
  given the next representable float
- **THEN** both nodes are stored

#### Scenario: Violation reports the exact value

- **WHEN** a write duplicates a tiny real value held by an existing element
- **THEN** the violation names the exact stored value together with the existing holder

#### Scenario: Existing data refuses declaration

- **WHEN** a caller declares a constraint over a scope that already holds two equal tiny
  real values
- **THEN** the declaration raises the constraint-violation error and creates nothing
