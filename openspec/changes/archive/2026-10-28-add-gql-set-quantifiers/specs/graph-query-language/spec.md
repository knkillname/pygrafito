# Spec Delta

## MODIFIED Requirements

### Requirement: Set operations

The dialect SHALL support compound queries built from two or more read-only linear statements with
`UNION`, `UNION ALL`, `INTERSECT`, `INTERSECT ALL`, `EXCEPT`, and `EXCEPT ALL`, and SHALL accept
an explicit `DISTINCT` quantifier on `UNION`, `INTERSECT`, and `EXCEPT`. Operators SHALL be
left-associative and SHALL combine the final `RETURN` tables of their operands. A compound query
SHALL NOT contain a write, `FINISH`, or `RETURN NO BINDINGS`.

#### Scenario: UNION ALL preserves rows

- **WHEN** a caller combines two program queries with `UNION ALL`
- **THEN** every row from both operands appears, including duplicates

#### Scenario: UNION removes duplicates

- **WHEN** a caller combines two queries with `UNION`
- **THEN** each distinct row appears once

#### Scenario: INTERSECT keeps common rows

- **WHEN** a caller combines two queries with `INTERSECT`
- **THEN** only rows present in both operands are returned

#### Scenario: EXCEPT removes the second operand

- **WHEN** a caller combines two queries with `EXCEPT`
- **THEN** rows present only in the first operand are returned

#### Scenario: Operators are left-associative

- **WHEN** a caller writes three operands without grouping
- **THEN** the left pair is combined first

#### Scenario: Write operand is rejected

- **WHEN** a caller combines a `CREATE` statement with a read query
- **THEN** the system raises a semantic query error and changes nothing

#### Scenario: Result-less forms are rejected

- **WHEN** a caller uses `FINISH` or `RETURN NO BINDINGS` as a set operand
- **THEN** the system raises a query error before execution

## ADDED Requirements

### Requirement: Set quantifiers

A set operator SHALL accept an optional `ALL` or `DISTINCT` quantifier. The bare operator and
`DISTINCT` SHALL use set semantics and emit each distinct row once. `INTERSECT ALL` SHALL emit
`min(left_count, right_count)` copies of each row; `EXCEPT ALL` SHALL emit
`max(left_count - right_count, 0)` copies. Duplicate counts SHALL use the dialect's canonical row
equality.

#### Scenario: Explicit DISTINCT is the default

- **WHEN** a caller combines two queries with `UNION DISTINCT`
- **THEN** the result is the same as `UNION`, with each distinct row appearing once

#### Scenario: INTERSECT ALL keeps the smaller count

- **WHEN** the left operand has three copies of a row and the right operand has two
- **THEN** `INTERSECT ALL` returns two copies

#### Scenario: EXCEPT ALL subtracts counts

- **WHEN** the left operand has three copies of a row and the right operand has two
- **THEN** `EXCEPT ALL` returns one copy

#### Scenario: EXCEPT ALL keeps unmatched duplicates

- **WHEN** the right operand has no copy of a row
- **THEN** `EXCEPT ALL` returns every copy from the left operand

#### Scenario: Canonical equality counts duplicates

- **WHEN** one operand returns the integer 36 and another returns the float 36.0
- **THEN** `INTERSECT ALL` and `EXCEPT ALL` treat them as the same row

#### Scenario: Quantifiers apply per operator

- **WHEN** a compound mixes `UNION ALL` and `INTERSECT ALL`
- **THEN** each operator applies its own quantifier left to right
