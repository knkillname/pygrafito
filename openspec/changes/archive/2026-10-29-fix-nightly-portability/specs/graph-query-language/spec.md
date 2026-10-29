# Spec Delta

## ADDED Requirements

### Requirement: Exact stored numeric equality

The dialect SHALL compare numeric property values by their exact stored value, so
equality and `IN` return the same rows regardless of how the SQLite JSON parser converts
a real literal. Integers and floats SHALL remain one numeric family for equality.

#### Scenario: Tiny real value matches through WHERE

- **WHEN** a node stores `2.7710821668887726e-173` under a property key and a caller
  filters with `WHERE n.key = $value` using that same value
- **THEN** the node is returned even when the runtime's JSON parser would round the
  stored literal

#### Scenario: Tiny real value matches through IN

- **WHEN** a node stores `1.6287812207021506e-109` under a property key and a caller
  filters with that value inside an `IN` list
- **THEN** the node is returned on every supported SQLite runtime

#### Scenario: Integer and float equality remains numeric

- **WHEN** a node stores the integer `36` and a caller compares it with the float `36.0`
- **THEN** the comparison reports equality

#### Scenario: Neighboring reals remain unequal

- **WHEN** a node stores a finite float and a caller compares it with the next
  representable float
- **THEN** the comparison does not report equality
