# Spec Delta

## MODIFIED Requirements

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
