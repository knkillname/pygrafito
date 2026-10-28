# Spec Delta

## MODIFIED Requirements

### Requirement: GQL tour classification and migration

Every `.gql` tour SHALL execute against the built sample dataset in the current release and SHALL
declare its GQL profile tier and the profile section it relies on. A tour that relies on a gated
construct SHALL name the follow-up change that implements it. A tour SHALL NOT present an alias or
extension as canonical GQL and SHALL NOT introduce a query construct absent from the profile.

#### Scenario: Tier is declared

- **WHEN** a reader opens a tour
- **THEN** its tier and profile section are stated in the tour catalog

#### Scenario: Gated construct names its change

- **WHEN** a tour relies on a gated construct
- **THEN** the catalog names the follow-up change that implements it

#### Scenario: Supported-only tour names no migrating change

- **WHEN** a tour relies only on supported constructs
- **THEN** the catalog does not claim a pending migration for it

#### Scenario: Tour executes

- **WHEN** the tour runs against the built dataset in the current release
- **THEN** every statement succeeds

#### Scenario: Extension is not claimed as GQL

- **WHEN** a tour uses `MERGE`, `WITH`, implicit grouping, or `type()`
- **THEN** the catalog labels it as a pygrafito extension

#### Scenario: No new construct is introduced

- **WHEN** the example layer needs a query construct that the profile does not list
- **THEN** the construct is left out and a separate profile change is required
