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
| `03-compose.gql` | `FOR`, `WITH ORDINALITY`, `LET`, map literals, `CASE`, `GROUP BY`, `NEXT`, `YIELD`, `FINISH`, `UNWIND`, `MERGE` | canonical GQL composition and expression surface; `UNWIND`, `WITH`, and `MERGE` are pygrafito extensions | Canonical surface; Synthetic aliases; Extensions | `add-gql-composition`, `add-gql-query-surface` (implemented) |
| `04-paths.gql` | `{n,m}`, open `+`, grouped `{n}`, `MATCH TRAIL`, `MATCH DIFFERENT EDGES`, `ANY SHORTEST`, `SHORTEST k`, `<->`, `~>`, path variables, `type()` | canonical GQL; `type()` is a pygrafito extension | Canonical surface; Path modes; Match modes; Path search; Grouped paths; Edge directions | implemented |

The tours use the composition and expression surface now that `LET`, `NEXT`, `YIELD`, `GROUP BY`,
`FINISH`, `WITH ORDINALITY`, map literals, and `CASE` are implemented. Open-ended quantifiers, match
modes, path search, and grouped path patterns are supported. They use `//` and `--` comments, the
single-dash arrows are canonical, and the path tour uses canonical quantifiers, explicit path
modes, search prefixes, and a grouped path.

`03-compose.gql` also binds `UNWIND` rows with `.param` to exercise parameter binding; this is a
tour choice, not a language limitation.
