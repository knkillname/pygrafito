# graph-indexes Specification

## Purpose

Defines declared indexes over stored property values and relationship types: how a caller
declares, lists, and removes them, how they persist, and the guarantee that an index
accelerates matching without changing any observable result.

## Requirements

### Requirement: Declared property index

The system SHALL let a caller declare an index on one node property key or one
relationship property key. A declaration SHALL be idempotent and SHALL NOT change stored
data. A property key that is not a non-empty string SHALL be rejected with a validation
error and SHALL NOT declare anything.

#### Scenario: Declare a node index

- **WHEN** a caller declares an index on a node property key
- **THEN** the index is reported among the declared indexes with the node element kind

#### Scenario: Declare a relationship index

- **WHEN** a caller declares an index on a relationship property key
- **THEN** the index is reported among the declared indexes with the relationship element kind

#### Scenario: Declare twice

- **WHEN** a caller declares the same index twice
- **THEN** both calls succeed and exactly one index is reported

#### Scenario: Invalid key

- **WHEN** a caller declares an index on an empty key
- **THEN** the system raises a validation error and reports no new index


### Requirement: Index listing and removal

The system SHALL report every declared index, identifying its element kind and property
key, and SHALL remove a declared index on request. A declared index SHALL remain in place
until it is removed. Removing an index that is not declared SHALL raise a not-found error.

#### Scenario: List declared indexes

- **WHEN** a caller declares two indexes and lists them
- **THEN** both are reported with their element kinds and keys

#### Scenario: Remove an index

- **WHEN** a caller removes a declared index and lists the indexes again
- **THEN** the removed index is no longer reported and graph content is unchanged

#### Scenario: Remove a missing index

- **WHEN** a caller removes an index that was never declared
- **THEN** the system raises a not-found error


### Requirement: Index transparency

A declared index SHALL NOT change statement or lookup results, result ordering, or value
equality. The same query SHALL return the same rows in the same order whether or not an
index is declared for the filtered key.

#### Scenario: Equality with an index

- **WHEN** a caller runs a property equality filter after declaring the matching index
- **THEN** the returned elements are identical to the results before the index existed

#### Scenario: Type distinction preserved

- **WHEN** an index covers a key holding a boolean, an integer, and a float, and a caller
  filters on one of those values
- **THEN** only elements with that exact stored type match

#### Scenario: List order preserved

- **WHEN** an indexed key holds lists and a caller filters on one list value
- **THEN** only elements whose list matches in order are returned

#### Scenario: Range with an index

- **WHEN** a caller runs a comparison filter on an indexed key
- **THEN** the same elements match as without the index, and results remain ordered by id


### Requirement: Index maintenance

The system SHALL keep a declared index consistent with stored data across property
updates, property removal, element deletion, and rolled-back writes.

#### Scenario: Property update

- **WHEN** a caller changes an indexed property value and queries for the new value
- **THEN** the element is returned for the new value and not for the old value

#### Scenario: Property removal

- **WHEN** a caller removes an indexed property by assigning null
- **THEN** the element no longer matches a filter for the removed value

#### Scenario: Element deletion

- **WHEN** a caller deletes an element indexed by one of its properties
- **THEN** later filters return no result for it and no stale index entry is observed

#### Scenario: Rolled-back write

- **WHEN** a transaction changes an indexed property and rolls back
- **THEN** the index matches the state before the transaction


### Requirement: Index persistence

Declared indexes SHALL persist in a file-backed database and SHALL be reported and used
after the graph is reopened without being declared again. Declaring or removing an index
SHALL NOT change the recorded schema version.

#### Scenario: Reopen with declared indexes

- **WHEN** a caller declares an index, closes the graph, and opens the same path again
- **THEN** the index is reported and filters on that key continue to match

#### Scenario: Schema version unchanged

- **WHEN** a caller declares and removes indexes on an existing database
- **THEN** the recorded schema version is the same as before the declarations

#### Scenario: In-memory graph

- **WHEN** a caller declares an index on an in-memory graph
- **THEN** the index is reported and usable for the lifetime of that handle


### Requirement: Query planning statistics

The system SHALL refresh query planning statistics after an index is declared and when a
file-backed graph is closed, so later connections plan with current information.

#### Scenario: Statistics after declaration

- **WHEN** a caller declares an index on a populated graph
- **THEN** planning statistics are refreshed before the next statement is planned

#### Scenario: Statistics after close

- **WHEN** a file-backed graph with declared indexes is closed
- **THEN** the database retains refreshed planning statistics for the next open

#### Scenario: Statistics do not change results

- **WHEN** planning statistics are refreshed
- **THEN** statement results and result ordering are unchanged


### Requirement: Plan inspection

The system SHALL expose the execution plan for a statement without executing it. Plan
inspection SHALL NOT read, create, update, or delete graph elements.

#### Scenario: Plan for an indexed filter

- **WHEN** a caller inspects a statement whose property filter has a declared index
- **THEN** the plan reports an index search rather than a full scan of the element table

#### Scenario: Plan for an unindexed filter

- **WHEN** a caller inspects a statement whose property filter has no declared index
- **THEN** the plan reports a scan of the element table

#### Scenario: Invalid statement

- **WHEN** a caller inspects a statement that does not parse
- **THEN** the system raises a query error

#### Scenario: Inspection is side-effect free

- **WHEN** a caller inspects a write statement
- **THEN** no element is created, changed, or deleted


### Requirement: Property key escaping

The system SHALL match property keys literally and SHALL NOT let a key alter statement
structure. Keys containing single quotes, double quotes, backslashes, dots, spaces, or
SQL-like text SHALL be matched as exact keys with their stored values.

#### Scenario: Key with punctuation

- **WHEN** a caller queries a key containing a dot, a space, or a Unicode character
- **THEN** only elements stored under that exact key match

#### Scenario: Key with a quote

- **WHEN** a caller queries a key containing a single quote or a double quote
- **THEN** the key matches literally and the statement structure is unchanged

#### Scenario: Key with a backslash

- **WHEN** a caller queries a key containing a backslash
- **THEN** the key matches literally and no other key matches

#### Scenario: SQL-shaped key

- **WHEN** a caller queries a key whose text resembles a SQL fragment
- **THEN** the fragment is treated as a key name and no additional SQL is executed


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
