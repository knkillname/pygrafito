# Spec Delta

## REMOVED Requirements

### Requirement: Relationship type index

**Reason**: Relationships no longer have exactly one type; they carry a label set, so a structural index on a single type cannot describe the new model.

**Migration**: Use the relationship label index, which answers filters on any label a relationship carries.

## ADDED Requirements

### Requirement: Relationship label index

The system SHALL maintain a structural index on relationship labels so that filtering by one or more labels without a bound endpoint does not read every relationship. A relationship carrying several labels SHALL be indexed under each label. The index SHALL stay current when a relationship is created, deleted, or has a label added or removed.

#### Scenario: Label filter without an endpoint

- **WHEN** a caller matches a relationship label without constraining either endpoint
- **THEN** the returned relationships are complete and the plan names an index search

#### Scenario: Multi-label relationship

- **WHEN** a relationship carries labels ALLIES_WITH and TRUSTS
- **THEN** a filter on either label returns it

#### Scenario: Label added

- **WHEN** a caller adds a label to an existing relationship
- **THEN** a filter on the added label returns that relationship

#### Scenario: Label removed

- **WHEN** a caller removes a label from a relationship
- **THEN** a filter on the removed label no longer returns that relationship

#### Scenario: Relationship deleted

- **WHEN** a caller deletes a relationship
- **THEN** later label filters return no result for it and no stale index entry is observed

### Requirement: Relationship property index scope

A declared index on a relationship property key SHALL cover every relationship that stores that key, regardless of its labels or directed flag. Label and direction filters SHALL narrow the candidates without changing the indexed property comparison.

#### Scenario: Indexed property on a multi-label edge

- **WHEN** a caller declares an index on a relationship property and filters on that property on edges carrying two labels
- **THEN** the matching edges are returned and the plan uses the property index

#### Scenario: Indexed property on an undirected edge

- **WHEN** a caller declares an index on a relationship property and filters on that property on an undirected edge
- **THEN** the matching edge is returned

#### Scenario: Label filter with an indexed property

- **WHEN** a caller combines a label filter with an indexed property filter
- **THEN** only edges carrying the label and matching the property value are returned
