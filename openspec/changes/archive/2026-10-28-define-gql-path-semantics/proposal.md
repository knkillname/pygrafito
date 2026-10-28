# Proposal: define the GQL path-semantics matrix

## Why

The remaining path-engine rows — match modes, open-ended quantifiers, path search, and grouped
quantified paths — are gated in the profile, and their interactions are not decided. Path mode,
match mode, quantifier, and search prefix each constrain repetition, but they do so at different
scopes and with different termination behavior. Implementing any one of them first would lock in
accidental semantics for the other three. The roadmap makes this change the gate for the rest of
the path engine.

## What Changes

- Define one decision table for path mode × match mode × quantifier × search prefix.
- Fix the match-mode default to `REPEATABLE ELEMENTS` and scope `DIFFERENT EDGES` to the whole
  `MATCH` clause, so the existing default behavior does not change.
- Define zero-hop and zero-iteration bindings, including what node, relationship, and path
  variables bind when a segment matches nothing.
- Define the canonical open quantifiers: `*` is zero or more, `+` is one or more, `{m,}` is `m` or
  more, and the legacy `*n..` keeps its trail default.
- Define path-search semantics: partition by the path's first and last node within each input row,
  selection rules for each prefix, duplicate-path rules, and a deterministic tie-break order.
- Define grouped quantified path patterns: juxtaposed path terms, group-local variables binding
  lists, outer-variable constraints, zero-iteration rules, and a progress rule.
- Define termination and demand: which shapes can stop early, which require full evaluation, and
  when an open-ended `WALK` must fail instead of running forever or truncating silently.
- Define budget accounting for open walks, search, and group iterations.
- Record the profile entries and the conformance corpus cases each later change must add.
- Record the combinations that remain semantic errors, and the migration notes for the behavior
  changes that the later changes may introduce.
- Update the 1.0 target semantics on the published profile page. No parser, engine, public API, or
  profile-status change lands here; the four implementing changes move their own rows.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change decides semantics and publishes the target matrix in the profile page; it does
not change the current behavior that the specs describe.

## Impact

- Documentation: a new "Path semantics" section in `docs/reference/gql-profile.md`, the target
  matrix, the corpus-case plan, and the migration notes. The query-language reference keeps
  describing only current behavior.
- `CHANGELOG.md`: an entry for the published path-semantics decisions.
- No runtime code, parser, AST, semantic analysis, executor, storage, CLI, dependency, or public
  API changes.
- Downstream work: `add-gql-unbounded-traversal`, `add-gql-match-modes`, `add-gql-path-search`, and
  `add-gql-grouped-quantified-paths` implement this matrix in dependency order.
