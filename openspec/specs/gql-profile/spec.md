# gql-profile Specification

## Purpose

Defines the published GQL language profile: its five-tier construct classification, canonical
surface, compatibility aliases and constructs, pygrafito extensions, path-mode and query-budget
policy, conformance claims, and migration guidance.

## Requirements

### Requirement: Profile publication and status

The project SHALL publish a GQL profile in the documentation reference navigation. The profile
SHALL distinguish target behavior from current behavior until the frontend, budget, and
path-semantics changes are implemented, and SHALL NOT present an unimplemented canonical form as
working.

#### Scenario: Profile page is listed

- **WHEN** a reader opens the documentation reference navigation
- **THEN** the GQL profile page is listed and links to the query-language reference and the migration guidance

#### Scenario: Target and current are distinct

- **WHEN** a canonical GQL form is not implemented by the current release
- **THEN** the profile marks it as target or gated rather than supported, and current examples remain runnable against the transitional dialect

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

### Requirement: Canonical GQL surface

The profile SHALL designate GQL spellings as canonical for data modification, iteration,
filtering, binding, composition, grouping, pagination, path quantifiers, label expressions, edge
directions, and comments. New documentation examples SHALL use the canonical spelling where the
current release supports it.

#### Scenario: Canonical spellings are listed

- **WHEN** a reader inspects the canonical table
- **THEN** it lists `INSERT`, `FOR`, `FILTER`, `LET`, `NEXT`, `GROUP BY`, `OFFSET`, `SKIP`, `{n,m}`, label expressions, the GQL edge-direction forms, and both GQL comment forms

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
SHALL list `WALK`, `TRAIL`, `SIMPLE`, and `ACYCLIC` as in scope. `WALK` SHALL be gated on the query
budget: the profile SHALL NOT mark `WALK` supported until the budget is implemented.

#### Scenario: Default is WALK

- **WHEN** a reader inspects the path-mode section
- **THEN** it states that `WALK` is the canonical default and that `TRAIL` is available explicitly

#### Scenario: WALK is gated

- **WHEN** the conformance matrix is inspected before the budget change lands
- **THEN** `WALK` is marked gated or pending, not supported

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

The profile SHALL designate `MERGE`, `WITH` aggregation and scope, implicit grouping, and `type()`
as pygrafito extensions with no GQL equivalent. The profile SHALL state that extensions are not
claimed as GQL and remain part of the supported compatibility surface.

#### Scenario: Extensions are labeled

- **WHEN** a reader inspects the extension table
- **THEN** each extension is labeled pygrafito-only and is not presented as a GQL feature

#### Scenario: Canonical alternative is shown

- **WHEN** an extension has a canonical GQL alternative, such as `GROUP BY` for implicit grouping
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

### Requirement: Deferred path features

The profile SHALL list GQL match modes, grouped quantified path patterns, path search prefixes,
and unbounded `WALK` as deferred. A deferred feature SHALL be marked gated in the conformance
matrix and SHALL NOT be presented as supported.

#### Scenario: Deferred features are gated

- **WHEN** a reader inspects the conformance matrix
- **THEN** match modes, grouped quantified paths, path search, and unbounded `WALK` are marked deferred or gated

#### Scenario: Unbounded WALK has an explicit gate

- **WHEN** unbounded `WALK` is considered
- **THEN** the profile requires a lazy traversal strategy and the query budget before it can be marked supported

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
