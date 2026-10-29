# Spec Delta

## ADDED Requirements

### Requirement: Real equality index transparency

Declaring an index SHALL NOT change which real property values match. An indexed
equality filter SHALL return the same elements as the same filter without the index,
including finite floats that the runtime's SQLite JSON parser would round.

#### Scenario: Indexed tiny real matches unindexed result

- **WHEN** a caller filters a key for `2.7710821668887726e-173` before and after
  declaring an index on that key
- **THEN** both filters return the same element on every supported SQLite runtime

#### Scenario: Indexed integer and real stay distinct

- **WHEN** an index covers a key holding the integer `1` and the real `1.0`, and a caller
  filters for `1.0`
- **THEN** only the element storing the real value is returned

#### Scenario: Indexed range results stay unchanged

- **WHEN** a caller runs a comparison filter on an indexed key holding real values
- **THEN** the same elements match before and after the index exists, ordered by id
