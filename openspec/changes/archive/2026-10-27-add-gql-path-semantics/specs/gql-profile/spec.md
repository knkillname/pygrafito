# Spec Delta

## MODIFIED Requirements

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

### Requirement: Deferred path features

The profile SHALL list GQL match modes, grouped quantified path patterns, path search prefixes,
unbounded `WALK`, and open-ended upper bounds (`*`, `+`, `*n..`, `{m,}`) as deferred. A deferred
feature SHALL be marked gated in the conformance matrix and SHALL NOT be presented as supported.

#### Scenario: Deferred features are gated

- **WHEN** a reader inspects the conformance matrix
- **THEN** match modes, grouped quantified paths, path search, unbounded `WALK`, and open-ended upper bounds are marked deferred or gated

#### Scenario: Unbounded WALK has an explicit gate

- **WHEN** unbounded `WALK` is considered
- **THEN** the profile requires a lazy traversal strategy and the query budget before it can be marked supported
