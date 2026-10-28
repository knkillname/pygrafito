# Proposal

## Why

Repository-wide `openspec validate --specs --strict` fails because five requirements in
`graph-query-language` have descriptions longer than the validator's 500-character limit. The
warnings obscure real validation failures and block clean strict validation. The existing archived
profile work already recorded this as a release-hygiene follow-up.

## What Changes

- Split `Core dialect profile` into focused requirements for statement/segment structure, `NEXT`
  and segment results, and statement row-source requirements.
- Split `UNWIND clause` into expansion semantics and ordinality semantics.
- Split `CREATE clause` into element creation and relationship constraints.
- Split `Projection and result columns` into projection rules and the `RETURN NO BINDINGS`
  extension.
- Split `Aggregation and grouping` into aggregate functions and grouping keys.
- Keep every existing normative rule and scenario; redistribute scenarios under the new
  requirement that owns them.
- Keep behavior unchanged. This is a spec-organization change only: no parser, engine, storage,
  CLI, public API, dependency, or Sphinx documentation behavior changes.
- Change requirement names and boundaries, but not observable query behavior.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `graph-query-language`: split five over-long requirements into focused requirements so strict
  validation passes without weakening or deleting behavior.

## Impact

- Spec text only: `openspec/specs/graph-query-language/spec.md`, delivered through this change's
  delta spec.
- No source, test, documentation, or runtime changes.
- The validator's 500-character warning for these five requirements disappears, allowing
  `openspec validate --specs --strict` to pass.
