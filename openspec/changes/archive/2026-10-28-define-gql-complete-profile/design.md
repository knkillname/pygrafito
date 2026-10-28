# Design: define the profile-complete GQL 1.0 scope

## Context

The current profile has 50 matrix rows: 39 supported, 4 deferred, and 7 out of profile. The 105
corpus cases cover all supported rows. The existing tests enforce "supported row has a case" and
"case names a matrix row", but they do not prove that the matrix and prose describe every
construct the query language recognizes.

The profile is therefore a strong status board for the current release, but not yet an exhaustive
1.0 contract. See `proposal.md` for why that gap matters now.

## Goals / Non-Goals

**Goals:**

- Make the published profile an exhaustive 1.0 target contract.
- Separate the status of in-scope work from post-1.0 direction.
- Freeze the 1.0 language scope and out-of-profile boundary.
- Define a release gate that can be checked later without changing its meaning.
- Keep the profile page readable as a status board and as a reference.

**Non-Goals:**

- Implement any parser, evaluator, planner, storage, CLI, or public API change.
- Add corpus cases for constructs that are still gated.
- Decide implementation syntax or execution semantics owned by the expression, subquery,
  set-operation, path-semantics, and path-engine changes.
- Decide hardening details such as the Python support floor, streaming result contract, and
  migration mechanism; the release gate requires those decisions to exist by 1.0.

## Decisions

### Feature-level matrix plus exhaustive inventory

The profile will keep a feature-level conformance matrix and add two companion tables:

| Table | Purpose |
| --- | --- |
| Conformance matrix | One row per feature family, with tier, status, current behavior, deviation, and corpus case |
| Construct inventory | Every canonical spelling, alias, compatibility form, extension, and out-of-profile construct, mapped to its matrix row or rejected form |
| Rejected forms | Invalid combinations and unsupported operations that are not separate features, with the error contract and test owner |

The matrix stays readable. The inventory guarantees that a spelling cannot hide inside a prose
deviation or an unsupported-construct list. Feature ids remain stable unless a feature is actually
split; the release gate is about coverage, not row count.

Alternative considered: one matrix row per micro-construct. This produces a very long table and
forces corpus feature ids to track grammar details rather than user-visible behavior. The hybrid
keeps the status board useful and the inventory exhaustive.

### Four statuses with `gated` reserved for 1.0 scope

The profile will use:

| Status | Meaning |
| --- | --- |
| `supported` | Implemented in the current release and covered by at least one corpus case |
| `gated` | In the 1.0 target profile, not implemented yet, with a named follow-up change |
| `deferred` | Post-1.0 language direction, not in the 1.0 profile |
| `out of profile` | Rejected non-goal |

The four existing path rows move from `deferred` to `gated`. New expression, subquery,
set-operation, and path rows also start as `gated`. At the 1.0 gate, every row is `supported` or
`out of profile`.

Alternative considered: keep the path rows as `deferred` because they are not implemented. That
would make the status board contradict the scope: the same features would be both 1.0 gates and
"not in the profile". The status needs to describe target membership separately from
implementation state.

### Target scope is broad on language, narrow on platform

The 1.0 language target includes:

- the expression surface, including `CASE`, maps, list operations, `||` with `+` compatibility,
  path functions, the extended scalar functions, and `WITH *`;
- read-only `EXISTS { ... }` and `COUNT { ... }`;
- all four set operations;
- match modes, grouped quantified paths, path search, open-ended quantifiers, and unbounded
  traversal;
- the existing supported surface and extensions.

The target excludes Cypher-only convenience syntax and non-language capabilities. They are
`out of profile`, not `deferred`, so the profile does not imply a future 1.x commitment.

Alternative considered: promote the Cypher compatibility surface or full-text search into 1.0.
Both widen the implementation and documentation surface without improving the GQL profile's
internal consistency. They remain post-1.0 candidates.

### The profile page separates current behavior from target status

The page will keep one status board, but it will state the distinction explicitly:

```text
supported       = works in the current release
gated           = target for 1.0, not yet executable
deferred        = post-1.0, not part of the 1.0 promise
out of profile  = rejected
```

The query-language reference continues to describe the executable dialect. Its gated and
unsupported sections will link to the profile target instead of duplicating the 1.0 scope. This
keeps the reference honest for 0.9 and avoids two competing target lists.

### The 1.0 release gate is a profile contract

The release gate will require:

1. no `gated` or `deferred` rows;
2. at least one corpus case for every `supported` row;
3. an explicit rejection test for every out-of-profile row and rejected form;
4. agreement between matrix, inventory, prose, grammar summary, query reference, and tours;
5. `hatch check --fix`, `hatch test`, and `hatch run docs:build` passing, with coverage at least
   80%;
6. the hardening checklist complete;
7. package smoke tests passing, with `py.typed` and `LICENSE.txt` packaged;
8. a 1.0 changelog section, migration notes, and the out-of-profile list;
9. version `1.0.0` set with `hatch version`.

This change documents the gate. The later `complete-gql-profile` change owns the automated
consistency checks that enforce it; implementation changes own their feature cases.

### Freeze policy

The 1.0 profile is frozen at release. A post-1.0 construct may be added in a minor release only
when it does not change existing semantics. A change that alters a supported construct's meaning
requires a major version and migration guidance.

### Specifications and documentation

Only the `gql-profile` capability changes. The `graph-query-language` specification continues to
describe current behavior; adding future constructs there would make the spec claim behavior the
engine does not have.

The apply tasks will:

- rewrite `docs/reference/gql-profile.md` with the matrix, inventory, rejected forms, status
  legend, release gate, and freeze policy;
- update `docs/reference/query-language.md` gated and unsupported sections to cross-reference the
  profile;
- add a short changelog entry for the profile contract;
- update the `gql-profile` spec through the delta in this change.

## Risks / Trade-offs

- **Profile bloat** -> Feature-level matrix, inventory, and rejected-forms tables keep each table
  focused. New rows require a reason and a follow-up owner.
- **Profile and code drift** -> Each gated row names its follow-up change; the release gate requires
  matrix/inventory/reference agreement; `complete-gql-profile` adds enforcement.
- **Gated rows go stale** -> Every gated row names a change. A gated row without an owner is a
  profile defect.
- **Target/current confusion** -> The status legend and the query-reference split make the
  distinction explicit.
- **Scope creep** -> Cypher-only and non-language capabilities are `out of profile`, not
  `deferred`; promoting one requires a separate proposal.
- **No automated gate yet** -> This change cannot prove the future gate passes. The gate becomes
  executable in `complete-gql-profile`; until then it is a review contract.

## Migration Plan

This is a documentation and specification change. There is no runtime migration.

1. Publish the exhaustive profile and update the `gql-profile` spec.
2. Keep current behavior and corpus untouched.
3. Use the gated rows to drive the expression, subquery, set-operation, path-semantics,
   path-engine, and profile-completion changes.
4. At 1.0, run the gate and update the status board from `gated` to `supported`.
5. Rollback is a documentation/spec revert; no data or API rollback is involved.
