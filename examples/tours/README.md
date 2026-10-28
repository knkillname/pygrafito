# Shell tours

Each `.gql` file is a short narrative that runs against the built `grid` database:

```console
python -m examples build grid --output grid.db
pygrafito grid.db -f examples/tours/01-match.gql
```

The files use the canonical GQL spellings where the current release supports them. The target
spellings, aliases, and extensions are defined in the
[GQL profile](../../docs/reference/gql-profile.md). The catalog below records the tier of every
construct the tour relies on and, when a tour still relies on a gated construct, the follow-up
change that implements it.

| Tour | Constructs | Tier | Profile section | Migrated by |
| --- | --- | --- | --- | --- |
| `01-match.gql` | `MATCH`, `OPTIONAL MATCH`, `MATCH ... WHERE`, `RETURN`, `ORDER BY`, `LIMIT`, `type()` | canonical GQL; `type()` is a pygrafito extension | Canonical surface; Extensions | `adopt-gql-query-frontend` (migrated) |
| `02-write.gql` | `INSERT`, `MERGE`, `SET`, `DETACH DELETE`, `labels()`, `type()` | `INSERT` and `SET` are canonical GQL; `MERGE`, `labels()`, and `type()` are pygrafito extensions | Data modification; Extensions | `adopt-gql-query-frontend` (migrated) |
| `03-compose.gql` | `FOR`, `WITH ORDINALITY`, `LET`, `GROUP BY`, `NEXT`, `YIELD`, `FINISH`, `UNWIND`, `MERGE` | canonical GQL composition; `UNWIND`, `WITH`, and `MERGE` are pygrafito extensions | Canonical surface; Synthetic aliases; Extensions | `add-gql-composition` (implemented) |
| `04-paths.gql` | `{n,m}`, `MATCH TRAIL`, `<->`, `~>`, path variables, `type()` | canonical GQL; `type()` is a pygrafito extension | Canonical surface; Path modes; Edge directions | implemented |

The tours use the composition surface now that `LET`, `NEXT`, `YIELD`, `GROUP BY`, `FINISH`, and
`WITH ORDINALITY` are implemented. They still avoid open-ended quantifiers and the expression
vocabulary. They use `//` and `--` comments, the single-dash arrows are canonical, and the path
tour uses the closed `{n,m}` quantifier and explicit path modes. A test enforces the remaining
deferred set.

`03-compose.gql` binds its `UNWIND` rows with `.param`, because the current release does not accept
map literals as list elements. That is a limitation of the current dialect, not of the profile.
