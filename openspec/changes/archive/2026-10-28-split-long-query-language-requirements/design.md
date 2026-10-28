# Design

## Context

See `proposal.md` for motivation. The affected capability is `graph-query-language`, whose main spec
has five requirements over the validator's 500-character description limit. OpenSpec requires a
`MODIFIED` requirement block to retain every scenario from the current spec; removing scenarios from
a modified block makes validation and archive fail. The change therefore has to reduce description
size without dropping or rewriting existing scenarios.

## Goals / Non-Goals

**Goals:**

- Split each of the five over-long requirements into focused requirements with descriptions at or
  below 500 characters.
- Preserve every existing normative rule and every existing scenario.
- Keep query behavior, parser behavior, public API, and documentation semantics unchanged.
- Make `openspec validate --specs --strict` pass after the delta is synced.

**Non-Goals:**

- No new query features or behavior changes.
- No parser, engine, storage, CLI, or public API changes.
- No Sphinx documentation content changes.
- No changes to other capabilities or to archived change records.

## Decisions

### Use `MODIFIED` plus `ADDED`, not `REMOVED` plus `ADDED`

The five original requirements remain in place with their existing headers and all existing
scenarios. Their descriptions are narrowed to one behavior, and the removed behaviors become new
`ADDED` requirements. This matches OpenSpec's requirement that a `MODIFIED` block replace the whole
current block without dropping scenarios. A `REMOVED` plus `ADDED` split was rejected because it
would falsely describe preserved behavior as removed.

### Keep original scenarios under `MODIFIED`

Each original requirement keeps its full scenario set exactly as it appears today. The new `ADDED`
requirements receive new, focused scenarios with distinct names. This is intentionally redundant at
the coverage level, but it is the only shape that preserves the current scenario inventory while
satisfying the archive contract. The alternative of moving scenarios from `MODIFIED` to `ADDED`
fails validation with an omitted-scenario error.

### Split boundaries

- `Core dialect profile` keeps the statement/segment ordering behavior. `NEXT and segment results`
  owns `NEXT`, `YIELD`, non-final `RETURN`, final results, and `FINISH`. `Statement row sources and
  result requirements` owns read/write completion rules, row-source requirements, and unsupported
  statement forms.
- `UNWIND clause` keeps list expansion and non-list errors. `UNWIND ordinality` owns
  `WITH ORDINALITY` and `WITH OFFSET`. `UNWIND placement and scope` owns freshness, scope, and read
  stage placement.
- `CREATE clause` keeps creation and alias semantics. `CREATE element validation` owns node
  bindings and property/label validation. `CREATE relationship constraints` owns endpoint binding,
  label cardinality, and direction.
- `Projection and result columns` keeps `RETURN` projection rules. `RETURN NO BINDINGS extension`
  owns the pygrafito-specific no-result form and its modifier restrictions.
- `Aggregation and grouping` keeps aggregate functions and empty-input behavior. `Grouping keys`
  owns implicit and explicit grouping.

### Preserve scenario text exactly

The new `ADDED` scenarios are additional examples, not replacements. Original scenario blocks are
copied verbatim into the `MODIFIED` blocks. This makes it possible to audit the change mechanically:
the affected original scenario set must be a subset of the delta's `MODIFIED` scenario set, with no
missing scenario names.

### No documentation or changelog change

The change does not alter observable behavior, the public API, dependencies, or packaging. The
Sphinx reference already describes query behavior independently of requirement boundaries, so no
docs page needs an update. A user-facing changelog entry would describe internal specification
organization and would not help library users.

## Risks / Trade-offs

- **Duplicate scenario intent under `MODIFIED` and `ADDED`** → Keep original scenarios untouched
  under `MODIFIED`; make added scenarios focused and give them distinct names so the duplication is
  visible and intentional.
- **Requirement-name changes could break future references** → No active change or source file
  references these requirement names. Archived deltas remain historical and are not rewritten.
- **Archive sync may append new requirements at the end of the spec** → When syncing, place each
  added requirement immediately after its parent requirement so the main spec remains readable.
- **The validator may still flag a rewritten description** → Keep every replaced description well
  below 500 characters and run strict validation on the change before implementation.

## Migration Plan

1. Land the delta spec and validate the change.
2. Archive the change so the main spec receives the `MODIFIED` and `ADDED` blocks.
3. Run `openspec validate graph-query-language --type spec --strict` and then
   `openspec validate --specs --strict`.
4. If strict validation fails, keep the change unarchived, correct the delta, and retry.

There is no runtime migration or rollback because no code, data, or public behavior changes.

## Open Questions

None.
