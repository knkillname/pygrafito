# gql-profile Specification

## Purpose

Defines the published GQL language profile: its five-tier construct classification, canonical
surface, compatibility aliases and constructs, pygrafito extensions, path-mode and query-budget
policy, conformance claims, and migration guidance.

## Requirements

### Requirement: Profile publication and status

The project SHALL publish a GQL profile in the documentation reference navigation. The profile
SHALL state, per construct, whether it is current or target behavior, and SHALL NOT present an
unimplemented canonical form as working.

#### Scenario: Profile page is listed

- **WHEN** a reader opens the documentation reference navigation
- **THEN** the GQL profile page is listed and links to the query-language reference and the migration guidance

#### Scenario: Target and current are distinct

- **WHEN** a canonical GQL form is implemented by the current release
- **THEN** the profile marks it supported and a conformance case covers it

#### Scenario: Unimplemented forms stay gated

- **WHEN** a canonical GQL form is not implemented by the current release
- **THEN** the profile marks it gated or deferred rather than supported

### Requirement: Construct classification

The profile SHALL classify every supported query construct into exactly one tier: canonical GQL,
synthetic alias, compatibility construct, pygrafito extension, or out of profile. A construct not
listed in the profile SHALL be treated as out of profile and rejected with an explicit query error
rather than ignored.

#### Scenario: Every construct has one tier

- **WHEN** a reader inspects the profile
- **THEN** each canonical, alias, compatibility, and extension construct appears under exactly one tier

#### Scenario: Unlisted construct is rejected

- **WHEN** a statement uses a construct that the profile does not list
- **THEN** the language contract rejects it with an explicit error and does not silently ignore it

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

### Requirement: Canonical GQL surface

The profile SHALL designate GQL spellings as canonical for data modification, iteration,
filtering, binding, composition, grouping, projection, pagination, path quantifiers, label
expressions, edge directions, and comments. New documentation examples SHALL use the canonical
spelling where the current release supports it.

#### Scenario: Canonical spellings are listed

- **WHEN** a reader inspects the canonical table
- **THEN** it lists `INSERT`, `FOR`, `FILTER`, `LET`, `NEXT`, `YIELD`, `GROUP BY`, `FINISH`, `OFFSET`, `SKIP`, `{n,m}`, label expressions, the GQL edge-direction forms, and both GQL comment forms

#### Scenario: Canonical examples lead

- **WHEN** a new documentation example covers a feature that the current release supports
- **THEN** the example uses the canonical spelling and the alias appears only in the compatibility section

### Requirement: Synthetic aliases

The profile SHALL designate compatibility aliases that differ from a canonical form only in
spelling and SHALL require identical semantics. The profile SHALL list at least `CREATE` for
`INSERT` in data statements, `UNWIND` for `FOR`, a stage-level `WHERE` for `FILTER`, the
double-dash arrow forms, and `:A:B` node labels for `:A&B`.

#### Scenario: Aliases are paired and marked equivalent

- **WHEN** a reader inspects the alias table
- **THEN** each alias is paired with its canonical form and marked as having identical semantics

#### Scenario: Supported alias has an equivalence case

- **WHEN** an alias is marked supported in the matrix
- **THEN** at least one conformance case compares it with the canonical form and runs in CI

### Requirement: Legacy quantifier semantics

The profile SHALL designate `*n`, `*n..m`, and `*0..m` as a compatibility construct whose default
path mode is `TRAIL`. `{n,m}` SHALL use the path-mode default. An explicit path mode SHALL override
both defaults. Mixing a legacy quantifier and a `{n,m}` quantifier in one path without an explicit
mode SHALL be a semantic error.

#### Scenario: Legacy quantifier defaults to trail

- **WHEN** a reader inspects the path-mode table for `*1..3` with no explicit mode
- **THEN** the profile records `TRAIL` as the default for that form

#### Scenario: GQL quantifier uses the profile default

- **WHEN** a reader inspects the path-mode table for `{1,3}` with no explicit mode
- **THEN** the profile records the canonical default path mode for that form

#### Scenario: Explicit mode wins

- **WHEN** a path uses `*1..3` and an explicit `WALK` mode
- **THEN** the profile records `WALK` as the effective mode

#### Scenario: Mixed quantifiers require a mode

- **WHEN** one path mixes `*1..2` and `{1,2}` without an explicit mode
- **THEN** the profile records a semantic error rather than a guessed default

### Requirement: Default path mode and budget gate

The profile SHALL designate `WALK` as the default path mode for canonical GQL path patterns and
SHALL list `WALK`, `TRAIL`, `SIMPLE`, and `ACYCLIC` as in scope. `WALK` SHALL be marked supported
only while the query budget is enforced and at least one conformance case covers it. If the budget
ceases to be enforced, `WALK` SHALL return to gated.

#### Scenario: Default is WALK

- **WHEN** a reader inspects the path-mode section
- **THEN** it states that `WALK` is the canonical default and that `TRAIL` is available explicitly

#### Scenario: WALK is gated

- **WHEN** the conformance matrix is inspected for a release that does not enforce the query budget
- **THEN** `WALK` is marked gated, not supported

#### Scenario: WALK is supported with the budget

- **WHEN** the conformance matrix is inspected in a release that enforces the query budget
- **THEN** `WALK` is marked supported and covered by a corpus case

#### Scenario: Path modes in scope are listed

- **WHEN** a reader inspects the path-mode section
- **THEN** `WALK`, `TRAIL`, `SIMPLE`, and `ACYCLIC` are listed as in scope

### Requirement: Query budget policy

The profile SHALL define a query budget that counts relationship expansions and intermediate rows
and SHALL state that exceeding it raises a query execution error. A write statement that exceeds
the budget SHALL roll back entirely. The budget SHALL be configurable per query and SHALL have a
documented default.

#### Scenario: Counters and default are documented

- **WHEN** a reader inspects the query-budget section
- **THEN** it names the expansion and intermediate-row counters and states the default budget

#### Scenario: Exceeding the budget is an error

- **WHEN** a query exceeds either counter
- **THEN** the profile requires an execution error that names the budget and the limit, with no partial result

#### Scenario: Write rolls back

- **WHEN** a write statement exceeds the budget
- **THEN** the profile requires every mutation of that statement to roll back and the graph handle to remain usable

#### Scenario: Per-query override

- **WHEN** a caller supplies a larger budget for one execution
- **THEN** the profile requires that execution to use the supplied budget without changing the graph default

### Requirement: Extensions

The profile SHALL designate `MERGE`, `WITH` aggregation and scope, implicit grouping, `type()`, and
`RETURN NO BINDINGS` as pygrafito extensions with no GQL equivalent. The profile SHALL state that
extensions are not claimed as GQL and remain part of the supported compatibility surface.
`RETURN NO BINDINGS` SHALL name `FINISH` as its canonical no-result alternative.

#### Scenario: Extensions are labeled

- **WHEN** a reader inspects the extension table
- **THEN** each extension is labeled pygrafito-only and is not presented as a GQL feature

#### Scenario: Canonical alternative is shown

- **WHEN** an extension has a canonical GQL alternative, such as `FINISH` for `RETURN NO BINDINGS` or `GROUP BY` for implicit grouping
- **THEN** the canonical alternative is documented alongside the extension

### Requirement: Out-of-profile GQL

The profile SHALL list catalog statements, graph types, sessions, procedures, in-language
transactions, `SELECT`, and full temporal values as out of profile for 1.0. A statement that uses
an out-of-profile construct SHALL be rejected with an explicit query error rather than ignored or
partially executed.

#### Scenario: Catalog statement is out of profile

- **WHEN** a caller submits `CREATE GRAPH` or another catalog statement
- **THEN** the profile requires a query error that names the construct as out of profile

#### Scenario: SELECT is out of profile

- **WHEN** a caller submits a GQL `SELECT` statement
- **THEN** the profile requires an explicit query error rather than a partial parse

#### Scenario: Temporal literal is out of profile

- **WHEN** a caller submits a full temporal literal that the profile does not include
- **THEN** the profile requires a query error rather than a coerced stored value

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

### Requirement: Conformance matrix

The profile SHALL publish a feature matrix that states, for each in-scope GQL feature, whether it
is supported, gated, deferred, or out of profile, and SHALL record every deliberate deviation from
ISO GQL. The project SHALL NOT claim ISO conformance beyond that matrix.

#### Scenario: Matrix statuses are explicit

- **WHEN** a reader inspects the matrix
- **THEN** each feature has a status and every deviation, including the legacy quantifier and the extension set, is recorded

#### Scenario: No blanket conformance claim

- **WHEN** the README, documentation, or release notes describe GQL support
- **THEN** they use the profile's wording and do not claim ISO conformance beyond the matrix

### Requirement: Conformance corpus

The profile SHALL define a conformance corpus contract with a query, a graph fixture, expected
rows or an expected error, and the profile feature it covers. The corpus SHALL run in continuous
integration, and a feature SHALL NOT be marked supported until at least one corpus case covers it.

#### Scenario: Corpus case shape

- **WHEN** a reader inspects the corpus contract
- **THEN** it defines the query, fixture, expected result or error, and feature fields

#### Scenario: Support requires coverage

- **WHEN** a feature is marked supported in the matrix
- **THEN** at least one conformance case covers it and runs in CI

#### Scenario: Regression fails CI

- **WHEN** a corpus case's actual result differs from its expected result
- **THEN** the CI run fails and names the case and feature

### Requirement: Migration guidance

The profile SHALL include migration guidance for the pre-1.0 transition from the transitional
dialect: the legacy quantifier's `TRAIL` default, canonical `{n,m}` under `WALK`, the alias
mapping, and the extension set. It SHALL state that the Python `paths()` API remains a
relationship-unique trail enumerator.

#### Scenario: Legacy behavior is reachable

- **WHEN** a reader wants the old relationship-unique behavior
- **THEN** the migration guidance shows `MATCH TRAIL` and the legacy `*n..m` form

#### Scenario: Paths API remains trail

- **WHEN** a reader compares the query language with the Python traversal API
- **THEN** the guidance states that `paths()` remains trail-only and does not follow the query language's `WALK` default

### Requirement: Change control

A change that adds, removes, or changes a query construct SHALL update the profile, the
conformance matrix, and the conformance corpus in the same change. A construct added without a
profile entry or a corpus case SHALL be rejected in review.

#### Scenario: New construct updates the profile

- **WHEN** a change adds a query construct
- **THEN** the same change updates the profile, the matrix, and the corpus

#### Scenario: Missing entry blocks the change

- **WHEN** a query construct is added without a profile entry
- **THEN** the change is not accepted as complete
