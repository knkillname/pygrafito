# Spec Delta

## ADDED Requirements

### Requirement: Exact real property equality

The system SHALL match a finite real property value by the exact value that was stored,
independently of how the SQLite JSON parser converts the canonical number text. Node and
relationship property filters SHALL return the element that stores the requested value on
every supported SQLite runtime.

#### Scenario: Tiny real value survives a node filter

- **WHEN** a node stores `2.7710821668887726e-173` under a property key and a caller
  filters for that same value
- **THEN** the node is returned even when the runtime's JSON parser would round the
  stored literal to a neighboring float

#### Scenario: Tiny real value survives a relationship filter

- **WHEN** a relationship stores `3.277095539246836e-284` under a property key and a
  caller filters for that same value
- **THEN** the relationship is returned on every supported SQLite runtime

#### Scenario: Neighboring real values remain distinct

- **WHEN** one node stores a finite float and another node stores the next representable
  float for the same key
- **THEN** a filter for either value returns only the node that stores it

#### Scenario: Type distinction stays intact

- **WHEN** one node stores the integer `1` and another stores the real `1.0`
- **THEN** a filter for `1.0` returns only the node that stores the real value
