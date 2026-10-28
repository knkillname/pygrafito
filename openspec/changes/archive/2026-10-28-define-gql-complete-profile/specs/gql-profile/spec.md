# Spec Delta: gql-profile

## ADDED Requirements

### Requirement: Exhaustive construct inventory

The profile SHALL publish an inventory that classifies every in-scope GQL construct, every supported alias and extension, and every out-of-profile or rejected form. The inventory SHALL cover every matrix row and every construct named in the query-language reference's gated and unsupported sections.

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

The profile SHALL use exactly four statuses: `supported`, `gated`, `deferred`, and `out of profile`. `gated` SHALL mean in the 1.0 target profile but not yet implemented; `deferred` SHALL mean post-1.0 language direction and not in the 1.0 profile. At the 1.0 release gate, no row SHALL be `gated` or `deferred`.

#### Scenario: In-scope work is gated

- **WHEN** a construct is in the 1.0 target profile but is not implemented
- **THEN** the matrix marks it `gated` and names the follow-up change that implements it

#### Scenario: Post-1.0 work is deferred

- **WHEN** a construct is not part of the 1.0 target profile but remains in the long-term language direction
- **THEN** the matrix marks it `deferred` rather than `gated`

#### Scenario: 1.0 has no gated or deferred rows

- **WHEN** the 1.0 release gate is evaluated
- **THEN** every matrix row is `supported` or `out of profile`

### Requirement: 1.0 target language scope

The 1.0 profile SHALL include the existing supported surface plus the expression, subquery, set-operation, and full path surfaces as in-scope target work.

#### Scenario: Expression surface is in scope

- **WHEN** a reader inspects the 1.0 target scope
- **THEN** it includes simple and searched `CASE`, map literals, list indexing and slicing, list comprehensions, canonical `||` concatenation with `+` as a compatibility alias, `nodes`, `relationships`, `length`, the extended scalar function set, and `WITH *` as part of the `WITH` extension

#### Scenario: Subqueries are in scope

- **WHEN** a reader inspects the 1.0 target scope
- **THEN** it includes read-only `EXISTS { ... }` and `COUNT { ... }` query expressions with correlated and uncorrelated forms

#### Scenario: Set operations are in scope

- **WHEN** a reader inspects the 1.0 target scope
- **THEN** it includes `UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT`

#### Scenario: Path surface is in scope

- **WHEN** a reader inspects the 1.0 target scope
- **THEN** it includes `DIFFERENT EDGES`, `REPEATABLE ELEMENTS`, grouped quantified paths, `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`, open-ended quantifiers, and unbounded traversal

### Requirement: Expanded out-of-profile boundary

The profile SHALL list the Cypher-only and non-language capabilities that remain out of profile for 1.0, in addition to the catalog, graph-type, session, procedure, transaction, `SELECT`, and temporal entries.

#### Scenario: Cypher-only syntax is out of profile

- **WHEN** a reader inspects the out-of-profile list
- **THEN** it includes `CALL { ... }`, whole-map assignment, `exists(n.prop)`, regex predicates, and `shortestPath()`

#### Scenario: Non-language capabilities are out of profile

- **WHEN** a reader inspects the out-of-profile list
- **THEN** it includes servers and drivers, clustering, authentication, multi-tenancy, multi-graph storage, graph-algorithm APIs, full Cypher compatibility, vector search, and full-text search

#### Scenario: Out-of-profile constructs are rejected

- **WHEN** a statement uses an out-of-profile construct
- **THEN** the language contract raises an explicit query error instead of ignoring or partially executing it

### Requirement: Rejected-form coverage

The profile SHALL list rejected combinations and forms that are not separate matrix features, including `MERGE` over a quantified pattern, a path variable, or more than one pattern, and catalog operations such as `INSERT GRAPH`.

#### Scenario: Rejected combinations are explicit

- **WHEN** a reader inspects the rejected-forms list
- **THEN** each invalid combination or unsupported operation has a stated reason and an explicit error contract

#### Scenario: Rejected forms are tested

- **WHEN** the 1.0 release gate is evaluated
- **THEN** every rejected form has an explicit rejection test in the corpus or a focused unit test

### Requirement: 1.0 release gate

The 1.0 profile SHALL define a release gate that blocks 1.0 until the profile is complete and verified.

#### Scenario: Profile is complete

- **WHEN** the release gate is evaluated
- **THEN** there are no `gated` or `deferred` rows and every supported row has at least one conformance case

#### Scenario: Out-of-profile and rejected forms are covered

- **WHEN** the release gate is evaluated
- **THEN** every out-of-profile row and every rejected form has an explicit rejection test

#### Scenario: Documentation agrees

- **WHEN** the release gate is evaluated
- **THEN** the matrix, prose, construct inventory, grammar summary, query-language reference, and tours describe the same status for every construct

#### Scenario: Quality checks pass

- **WHEN** the release gate is evaluated
- **THEN** `hatch check --fix`, `hatch test`, and `hatch run docs:build` pass, coverage is at least 80%, package smoke tests pass, and `py.typed` and `LICENSE.txt` are packaged

#### Scenario: Release notes are ready

- **WHEN** the release gate is evaluated
- **THEN** the 1.0 changelog section, migration notes, and out-of-profile list exist and the version is set with `hatch version 1.0.0`

### Requirement: Profile freeze policy

The 1.0 profile SHALL be frozen at release. After 1.0, profile changes SHALL be additive or require a major version, and the profile SHALL state that policy.

#### Scenario: Additive change after 1.0

- **WHEN** a post-1.0 change adds a construct without changing existing semantics
- **THEN** it updates the profile, matrix, inventory, and corpus in the same change

#### Scenario: Breaking profile change

- **WHEN** a post-1.0 change alters the meaning of a supported construct
- **THEN** it requires a major version and a migration section

## REMOVED Requirements

### Requirement: Deferred path features

**Reason**: Match modes, grouped quantified paths, path search, and open-ended traversal are now in the 1.0 target profile. They are `gated`, not `deferred`, and the status vocabulary and target scope requirements replace this requirement.

**Migration**: Use the status vocabulary and 1.0 target language scope requirements. Reclassify the affected matrix rows as `gated` with their follow-up changes until implementation lands.
