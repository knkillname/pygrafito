# Explore the sample graphs

`pygrafito` ships a runnable example layer in the repository's `examples/` tree: three linked
datasets, shell tours, analysis recipes, and algorithm demonstrations. The examples are developer
artifacts, not part of the installed package, so every command below runs from a repository
checkout.

```console
python -m examples
```

That lists the datasets, lanes, and commands. If the project is not installed in the active
environment, use `hatch run python -m examples` instead. The rest of this page follows the same
order.

## Datasets

| Name | What it contains |
| --- | --- |
| `grid` | Curated franchise graph across the 1981 TRON draft, TRON: Legacy, and TRON: Ares, with film provenance, lineage, places, vehicles, and objects |
| `cast` | Weighted character co-occurrence and dialogue-turn aggregates, each edge carrying a `basis` property |
| `places` | Place containment plus scene-to-scene transitions from the 1981 screenplay |
| `all` | The three datasets merged by shared handles |
| `synthetic` | A seeded scale graph shared with the benchmark harness |

Build a database or a version 2 JSONL snapshot:

```console
python -m examples build grid --output grid.db
python -m examples build all --output all.jsonl --format jsonl
python -m examples build synthetic --nodes 5000 --relationships 15000
```

A database build applies the dataset's indexes and uniqueness constraints. A snapshot carries
elements only; see [Snapshot format](../reference/snapshot-format.md). The committed
`examples/data/grid.jsonl` is the snapshot of `grid`, and the test suite keeps it identical to a
fresh build.

Open the database in the shell:

```console
pygrafito grid.db
```

## Shell tours

The `.gql` tours are short narratives that run against the built database:

```console
pygrafito grid.db -f examples/tours/01-match.gql
pygrafito grid.db -f examples/tours/02-write.gql
pygrafito grid.db -f examples/tours/03-compose.gql
pygrafito grid.db -f examples/tours/04-paths.gql
```

The tours use the current transitional dialect. The target GQL spellings are documented in the
[GQL profile](../reference/gql-profile.md); each tour is catalogued with its tier and the follow-up
change that will migrate it in `examples/tours/README.md`. `MERGE`, `WITH`, implicit grouping, and
`type()` are pygrafito extensions, not canonical GQL.

| Tour | Focus | Migrated by |
| --- | --- | --- |
| `01-match.gql` | `MATCH`, `OPTIONAL MATCH`, filtering, and ordering | `adopt-gql-query-frontend` |
| `02-write.gql` | `CREATE` alias, `MERGE` extension, labels, and deletion | `adopt-gql-query-frontend` |
| `03-compose.gql` | `UNWIND` alias, `WITH`, and grouping | `add-gql-composition` |
| `04-paths.gql` | quantified compatibility syntax, directions, and path variables | `add-gql-path-semantics` |

## Analysis recipes

The analysis lane turns the datasets into tables, files, and SQL results:

```console
python -m examples.analysis.rank_by_degree
python -m examples.analysis.aggregate_by_source
python -m examples.analysis.import_csv
python -m examples.analysis.sql_views
python -m examples.analysis.export_report --output report
```

Every recipe runs with no required arguments and uses an in-memory graph by default. Use the flags
each recipe documents for depth, a caller-supplied file, or an output directory.

## Algorithm demonstrations

The algorithms lane shows traversal semantics and cost:

```console
python -m examples.algorithms.reachability
python -m examples.algorithms.trails_vs_walks
python -m examples.algorithms.shortest_path
python -m examples.algorithms.direction
python -m examples.algorithms.scaling --nodes 2000
```

`paths()` enumerates relationship-unique trails. The target GQL profile makes `WALK` the default
path mode for canonical patterns, gated by the query budget; the trails demonstration states that
difference rather than claiming the target behavior is available today. See the
[GQL profile](../reference/gql-profile.md#path-modes) and the
[graph API](../api/graph.md).

## Where the data comes from

The repository does not contain a screenplay or transcript. The source files live outside version
control, the extractor in `examples/extract/` is a local development tool, and its output is limited
to names, counts, weights, and structural metadata. No dialogue or action text is committed or
packaged. The `basis` property on derived edges records whether a weight came from a shared scene, a
transcript page, a dialogue window, a dialogue turn, or a scene transition.

### Local extraction

The extractor reads a source file you supply and emits aggregate JSON only:

```console
python -m examples.extract.screenplay path/to/screenplay.txt --format screenplay --kind cast
python -m examples.extract.screenplay path/to/transcript.txt --format transcript --kind cast
```

Use `--kind places` for scene transitions when the source has scene headings. The output contains
handles, weights, counts, and `basis` metadata, never dialogue or action text. The PDF adapter uses
`pdftotext` from poppler as a development-only tool; the package does not depend on it. Tests use an
invented fixture, so no real screenplay is required.

For the full catalog, provenance policy, and the rules for adding an example, see the
[example catalog](https://github.com/knkillname/pygrafito/blob/main/examples/README.md).
