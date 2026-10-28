# public-api Specification

## Purpose

Defines the stability of the exported Python surface and the deprecation rules a 1.x user can rely
on.

## Requirements

### Requirement: Frozen public surface

The exported names in `__all__`, the public methods and properties of `Graph`, `Transaction`, and
`PreparedQuery`, the public dataclass fields, and the exception hierarchy SHALL be frozen for 1.x.
Minor releases MAY add names and optional parameters; removing or renaming a public name, changing
an existing signature incompatibly, or changing a documented default SHALL require a major release.

#### Scenario: Golden surface matches

- **WHEN** the public-surface snapshot test runs
- **THEN** every exported name, signature, field, and exception base matches the checked-in snapshot

#### Scenario: Additive change is allowed

- **WHEN** a minor release adds a new public method or an optional parameter
- **THEN** the snapshot is updated intentionally and existing calls still work

#### Scenario: Removal is caught

- **WHEN** a change removes or renames a public name without a major-version plan
- **THEN** the snapshot test fails

#### Scenario: Signature drift is caught

- **WHEN** a change alters an existing public signature or documented default
- **THEN** the snapshot test fails and the change must be treated as a major version

### Requirement: Deprecation policy

A deprecated public name SHALL emit `DeprecationWarning`, SHALL remain functional for at least one
minor release, and SHALL be documented in the reference and changelog. Removal SHALL occur only in
a major release. On Python 3.13 and newer, the deprecation SHALL also be visible to static type
checkers.

#### Scenario: Deprecated call warns

- **WHEN** a caller uses a deprecated public name
- **THEN** the call works and emits `DeprecationWarning`

#### Scenario: Documentation and changelog

- **WHEN** a name is deprecated
- **THEN** the reference documentation and changelog name the replacement and the removal version

#### Scenario: Removal waits for a major

- **WHEN** a deprecated name has existed for fewer than one minor release
- **THEN** it is not removed

#### Scenario: Static visibility

- **WHEN** a typed caller uses a deprecated name on Python 3.13 or newer
- **THEN** the type checker reports the deprecation

### Requirement: Documented error hierarchy

Every documented failure mode of a public call SHALL raise a `PygrafitoError` subclass. Invalid
values and invalid states SHALL NOT escape as built-in exceptions. The error reference SHALL
document each public exception, its cause, and the recovery action.

#### Scenario: Invalid input raises a library error

- **WHEN** a public call receives an invalid value or an invalid handle state
- **THEN** it raises a `PygrafitoError` subclass rather than a built-in exception

#### Scenario: Query failures stay in the query hierarchy

- **WHEN** a query fails to parse or execute
- **THEN** the error is a `QueryError` subclass

#### Scenario: Hierarchy is documented

- **WHEN** a user reads the error reference
- **THEN** every public exception and its base class are listed
