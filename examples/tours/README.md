# Shell tours

Each `.gql` file is a short narrative that runs against the built `grid` database:

```console
python -m examples build grid --output grid.db
pygrafito grid.db -f examples/tours/01-match.gql
```

The files use the current transitional dialect. The target spellings, aliases, and extensions are
defined in the [GQL profile](../../docs/reference/gql-profile.md). The catalog below records the
tier of every construct the tour relies on and the follow-up change that will migrate it.

| Tour | Constructs | Tier | Profile section | Migrated by |
| --- | --- | --- | --- | --- |
| `01-match.gql` | `MATCH`, `OPTIONAL MATCH`, `MATCH ... WHERE`, `RETURN`, `ORDER BY`, `LIMIT`, `type()` | canonical GQL; `type()` is a pygrafito extension | Canonical surface; Extensions | `adopt-gql-query-frontend` for `FILTER` alternatives |
| `02-write.gql` | `CREATE`, `MERGE`, `SET`, `DETACH DELETE`, `labels()`, `type()` | `CREATE` is a synthetic alias for `INSERT`; `MERGE`, `labels()`, and `type()` are pygrafito extensions | Data modification; Extensions | `adopt-gql-query-frontend` for `INSERT` |
| `03-compose.gql` | `UNWIND`, `WITH`, implicit grouping, `MERGE` | `UNWIND` is a synthetic alias for `FOR`; `WITH`, implicit grouping, and `MERGE` are pygrafito extensions | Synthetic aliases; Extensions | `add-gql-composition` |
| `04-paths.gql` | `*n..m`, `-->`, `--`, label alternatives, path variables | legacy quantifier compatibility (`TRAIL`); double-dash directions are synthetic aliases | Legacy quantifier; Edge directions | `add-gql-path-semantics` |

The tours do not use target-only syntax: no `INSERT`, `FILTER`, `FOR`, `LET`, `NEXT`, `GROUP BY`,
`~`, or `{n,m}`, and no single-dash anonymous `->` (anonymous edges use `-->`). They use `//`
comments only, because `--` is not a comment in the current release. A test enforces both rules.

`03-compose.gql` binds its `UNWIND` rows with `.param`, because the current release does not accept
map literals as list elements. That is a limitation of the transitional dialect, not of the target
profile.
