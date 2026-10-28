# Design

## Context

See `proposal.md` for motivation. The current frontend has four set operators in `SetOperation`
(`UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT`). The parser explicitly rejects `ALL` after
`INTERSECT` and `EXCEPT`, and the executor combines materialized `ProjectedRow` values with a
canonical `ValueKey` tuple. `CompoundPlan.operators` renders each operator with its `.value`, so
explain output and prepared-query metadata follow the enum without a separate quantifier field.

The relevant behavior contract is the `graph-query-language` delta spec.

## Goals / Non-Goals

**Goals:**

- Add `INTERSECT ALL`, `EXCEPT ALL`, and explicit `DISTINCT` with one local change to the query
  frontend.
- Reuse the existing canonical row equality, left-associativity, and compound ordering rules.
- Keep the surface consistent with the existing `UNION` / `UNION ALL` matrix and corpus split.

**Non-Goals:**

- New set operators, different row equality, or changes to column, ordering, pagination,
  read-only, transaction, or budget rules.
- Streaming set combination. The engine already materializes compound rows.
- A new exception type, a new reserved word, or a change to the public Python API.

## Decisions

### Multiset counting in `_combine_rows`

Compute one `collections.Counter` over the right operand's canonical row keys, then iterate the
left rows in order:

- `INTERSECT ALL`: append while the right count is positive, decrementing it.
- `EXCEPT ALL`: skip while the right count is positive, decrementing it; append otherwise.

The bare forms keep their current semantics using the same counter for membership and
`_distinct` for output. We reuse the existing `ValueKey` tuple, so `36` and `36.0` count as the
same row.

Alternative considered: sorting both sides and merging. It changes output order, costs more code,
and offers no benefit because the rows are already materialized. Alternative considered: SQL
`INTERSECT ALL` / `EXCEPT ALL`. SQLite does not provide those operators, so using SQL would split
the execution path for no gain.

### Output order

The dialect leaves row order unspecified without `ORDER BY`. The implementation preserves left
first-seen order for deterministic tests and for continuity with the current bare forms. The
reference documents that only a compound `ORDER BY` guarantees order.

### Explicit `DISTINCT` as a synthetic alias

The parser consumes `DISTINCT` after `UNION`, `INTERSECT`, or `EXCEPT` and returns the bare
operator. It is a spelling, not a new execution path, and it belongs in the existing synthetic
alias tier.

Alternative considered: keep rejecting it, as SQLite does. Rejected because the grammar slot is
already present, the project accepts pure re-spellings elsewhere, and leaving it out would create
another out-of-profile row that fails the profile criterion.

### Enum values and plan output

Add `INTERSECT_ALL = "INTERSECT ALL"` and `EXCEPT_ALL = "EXCEPT ALL"` to `SetOperation`.
`CompoundPlan.operators` already renders `operator.value`, so explain output carries the long
form without special cases. Alternative considered: a separate `quantifier` field on
`CompoundStatement`; rejected as extra state that every consumer must reassemble.

### Left-associative chains

Each operator applies its own quantifier left to right:
`A INTERSECT ALL B EXCEPT ALL C` means `(A INTERSECT ALL B) EXCEPT ALL C`. Multiset intersection
is associative, but bag difference is not, so the left-to-right order is part of the contract and
gets a scenario.

### One quantifier per operator

`ALL` and `DISTINCT` are alternatives, not a sequence. `INTERSECT ALL DISTINCT` remains a syntax
error, as does `INTERSECT DISTINCT ALL`. This follows from the grammar and needs no new error
type.

### Profile granularity

Add separate matrix rows for `INTERSECT ALL` and `EXCEPT ALL`, with corpus feature ids
`intersect-all` and `except-all`, mirroring the existing `UNION` / `UNION ALL` split. Alternative
considered: fold the forms into the bare rows; rejected because the matrix already separates
`UNION ALL` and the corpus convention follows the matrix.

## Risks / Trade-offs

- Count semantics can diverge from the bare forms when duplicates exist → dedicated corpus cases
  for smaller, larger, and empty counts.
- Numeric canonical equality can surprise users → a scenario and a corpus case for `36` / `36.0`.
- Output order is implementation detail → document it as unspecified without `ORDER BY`; assert
  first-seen order only in the implementation test, not in the contract.
- `UNION DISTINCT` adds a second spelling for the same meaning → document it as the explicit
  default and keep the bare form in examples.
- Profile and reference drift → the same change updates matrix rows, inventory, grammar,
  reference prose, and changelog.

## Migration Plan

Additive. Existing bare and `UNION ALL` queries behave exactly as before. `INTERSECT ALL` and
`EXCEPT ALL` previously raised a semantic error and now execute; `UNION DISTINCT` previously
raised a syntax error and now executes. No data, schema, snapshot, or public API migration.

## Open Questions

None.
