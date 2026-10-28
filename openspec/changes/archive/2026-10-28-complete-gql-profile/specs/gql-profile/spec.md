# Spec Delta

## MODIFIED Requirements

### Requirement: Exhaustive construct inventory

The profile SHALL publish an inventory that classifies every in-scope GQL construct, every supported alias and extension, and every out-of-profile or rejected form. The inventory SHALL cover every matrix row and every construct named in the query-language reference's unsupported and out-of-profile sections.

#### Scenario: Matrix and inventory agree

- **WHEN** a reader compares the conformance matrix with the construct inventory
- **THEN** every matrix row maps to an inventory entry and every inventory entry maps to a matrix row or a rejected form

#### Scenario: Unlisted construct is a defect

- **WHEN** a construct appears in the query-language reference but not in the inventory
- **THEN** the profile is incomplete and the change is not accepted as complete

#### Scenario: Aliases and extensions are explicit

- **WHEN** a reader inspects the inventory
- **THEN** every alias, compatibility construct, and pygrafito extension has exactly one tier and a canonical alternative or a stated reason for having none

### Requirement: Status vocabulary and gated semantics

The profile SHALL use exactly four statuses: `supported`, `gated`, `deferred`, and `out of profile`. `gated` SHALL mean in the 1.0 target profile but not yet implemented; `deferred` SHALL mean post-1.0 language direction and not in the 1.0 profile. At the 1.0 release gate, no row SHALL be `gated` or `deferred`. A supported row SHALL NOT retain gated prose or a follow-up owner.

#### Scenario: In-scope work is gated

- **WHEN** a construct is in the 1.0 target profile but is not implemented
- **THEN** the matrix marks it `gated` and names the follow-up change that implements it

#### Scenario: Post-1.0 work is deferred

- **WHEN** a construct is not part of the 1.0 target profile but remains in the long-term language direction
- **THEN** the matrix marks it `deferred` rather than `gated`

#### Scenario: 1.0 has no gated or deferred rows

- **WHEN** the 1.0 release gate is evaluated
- **THEN** every matrix row is `supported` or `out of profile`

#### Scenario: Supported rows lose their gated prose

- **WHEN** a construct becomes supported
- **THEN** the profile and the query-language reference describe it as current behavior and no longer list it under a gated heading, a follow-up change, or target-only wording

### Requirement: Out-of-profile GQL

The profile SHALL list catalog statements, graph types, sessions, procedures, in-language transactions, `SELECT`, and full temporal values as out of profile for 1.0. A statement that uses an out-of-profile construct SHALL be rejected with an explicit query error rather than ignored or partially executed. The profile SHALL record, for each out-of-profile row, whether the rejection is a recognized semantic boundary or unrecognized syntax.

#### Scenario: Catalog statement is out of profile

- **WHEN** a caller submits `CREATE GRAPH` or another catalog statement
- **THEN** the profile requires a query error that names the construct as out of profile

#### Scenario: SELECT is out of profile

- **WHEN** a caller submits a GQL `SELECT` statement
- **THEN** the profile requires an explicit query error rather than a partial parse

#### Scenario: Temporal literal is out of profile

- **WHEN** a caller submits a full temporal literal that the profile does not include
- **THEN** the profile requires a query error rather than a coerced stored value

#### Scenario: Rejection form is stated per row

- **WHEN** a reader inspects an out-of-profile row
- **THEN** the row states whether the construct is a recognized boundary with a semantic error or unrecognized text with a syntax error

### Requirement: 1.0 release gate

The 1.0 profile SHALL define a release gate that blocks 1.0 until the profile is complete and verified. The gate SHALL be checked by automated tests rather than by prose inspection alone.

#### Scenario: Profile is complete

- **WHEN** the release gate is evaluated
- **THEN** there are no `gated` or `deferred` rows and every supported row has at least one conformance case

#### Scenario: Out-of-profile and rejected forms are covered

- **WHEN** the release gate is evaluated
- **THEN** every out-of-profile row and every rejected form has an explicit rejection test

#### Scenario: Documentation agrees

- **WHEN** the release gate is evaluated
- **THEN** the matrix, prose, construct inventory, grammar summary, query-language reference, and tours describe the same status for every construct

#### Scenario: Gate checks are automated

- **WHEN** the release gate is evaluated
- **THEN** a test suite checks for no `gated` or `deferred` rows, inventory status equal to matrix status, supported-row coverage, and rejection coverage for every out-of-profile row

#### Scenario: Quality checks pass

- **WHEN** the release gate is evaluated
- **THEN** `hatch check --fix`, `hatch test`, and `hatch run docs:build` pass, coverage is at least 80%, package smoke tests pass, and `py.typed` and `LICENSE.txt` are packaged

#### Scenario: Release notes are ready

- **WHEN** the release gate is evaluated
- **THEN** the 1.0 changelog section, migration notes, and out-of-profile list exist and the version is set with `hatch version 1.0.0`

### Requirement: Conformance corpus

The profile SHALL define a conformance corpus contract with a query, a graph fixture, expected
rows or an expected error, and the profile feature it covers. The corpus SHALL run in continuous
integration, and a feature SHALL NOT be marked supported until at least one corpus case covers it.
An out-of-profile rejection case SHALL carry a `rejection` tag and an expected error type and
message fragment.

#### Scenario: Corpus case shape

- **WHEN** a reader inspects the corpus contract
- **THEN** it defines the query, fixture, expected result or error, and feature fields

#### Scenario: Support requires coverage

- **WHEN** a feature is marked supported in the matrix
- **THEN** at least one conformance case covers it and runs in CI

#### Scenario: Regression fails CI

- **WHEN** a corpus case's actual result differs from its expected result
- **THEN** the CI run fails and names the case and feature

#### Scenario: Rejection cases assert the boundary

- **WHEN** a corpus case documents an out-of-profile construct
- **THEN** it is tagged `rejection`, expects an error type and a message fragment, and fails if the statement executes
