# graph-examples Specification

## Purpose

Defines the runnable example layer: curated franchise datasets and their provenance, deterministic
build and native snapshot export, the audience-facing example lanes and front door, GQL tour
tiering and migration, benchmark fixture reuse, and documentation and test synchronization.

## Requirements

### Requirement: Curated sample dataset

The project SHALL provide a curated sample graph covering the 1981 TRON draft, the released
TRON: Legacy script, and the TRON: Ares script. It SHALL contain named users, programs,
organizations, places, vehicles, and objects, film provenance, and cross-film lineage, and SHALL
NOT contain screenplay dialogue, action text, or screenplay files.

#### Scenario: Three sources are represented

- **WHEN** a reader inspects the sample dataset
- **THEN** entities identify at least one of the three sources and at least one entity identifies more than one

#### Scenario: Provenance is queryable

- **WHEN** a query returns a sample entity
- **THEN** its source list is available as a typed list property

#### Scenario: No screenplay text is shipped

- **WHEN** the repository and built package are searched
- **THEN** no screenplay file, dialogue line, or action paragraph from a source script is present

### Requirement: Declarative dataset source

The dataset source SHALL be a declarative JSON document keyed by stable string handles. Nodes SHALL
carry labels and typed properties; relationships SHALL carry endpoints, a label set, a directed
flag, and typed properties. The builder SHALL validate the whole document before creating any
element and SHALL reject duplicate handles and unknown endpoints.

#### Scenario: Duplicate handle is rejected

- **WHEN** two nodes declare the same handle
- **THEN** the build fails before creating any element and names the duplicate handle

#### Scenario: Unknown endpoint is rejected

- **WHEN** a relationship names an endpoint that no node declares
- **THEN** the build fails before creating any element and names the missing handle

#### Scenario: Full element model is preserved

- **WHEN** the source declares a multi-label node and an undirected relationship with several labels
- **THEN** the built graph stores every label and the undirected flag

### Requirement: Deterministic build and native snapshot

The build entry point SHALL create a graph from a named dataset and SHALL emit either a database
file or a version 2 JSONL snapshot. Building the same dataset revision SHALL produce a
byte-identical snapshot across runs and processes.

#### Scenario: Repeated builds are identical

- **WHEN** the same dataset revision is built twice in separate processes
- **THEN** the emitted snapshots are byte-identical

#### Scenario: Snapshot restores

- **WHEN** the emitted snapshot is restored into an empty graph
- **THEN** node and relationship labels, directions, and properties match the built graph

#### Scenario: Database output opens

- **WHEN** the build writes a database file
- **THEN** a shell session opens it and reports the expected element counts

### Requirement: Audience lanes and front door

The example layer SHALL expose `python -m examples` as a single entry point that lists the catalog
when no action is given and builds a named dataset when asked. The tree SHALL provide shell tours,
analysis recipes, and algorithm demonstrations, and every example SHALL run without required
arguments against an in-memory graph.

#### Scenario: Catalog is listed

- **WHEN** a reader runs the entry point with no action
- **THEN** it lists the datasets, lanes, and runnable commands

#### Scenario: Dataset builds from the front door

- **WHEN** a reader asks the entry point to build a named dataset
- **THEN** the requested database or snapshot is produced

#### Scenario: Examples run without arguments

- **WHEN** a reader runs any analysis or algorithm example with no arguments
- **THEN** it completes against an in-memory graph and prints its result

### Requirement: GQL tour classification and migration

Every `.gql` tour SHALL execute against the built sample dataset in the current release and SHALL
declare its GQL profile tier and the profile section it relies on. A tour that relies on a gated
construct SHALL name the follow-up change that implements it. A tour SHALL NOT present an alias or
extension as canonical GQL and SHALL NOT introduce a query construct absent from the profile.

#### Scenario: Tier is declared

- **WHEN** a reader opens a tour
- **THEN** its tier and profile section are stated in the tour catalog

#### Scenario: Gated construct names its change

- **WHEN** a tour relies on a gated construct
- **THEN** the catalog names the follow-up change that implements it

#### Scenario: Supported-only tour names no migrating change

- **WHEN** a tour relies only on supported constructs
- **THEN** the catalog does not claim a pending migration for it

#### Scenario: Tour executes

- **WHEN** the tour runs against the built dataset in the current release
- **THEN** every statement succeeds

#### Scenario: Extension is not claimed as GQL

- **WHEN** a tour uses `MERGE`, `WITH`, implicit grouping, or `type()`
- **THEN** the catalog labels it as a pygrafito extension

#### Scenario: No new construct is introduced

- **WHEN** the example layer needs a query construct that the profile does not list
- **THEN** the construct is left out and a separate profile change is required

### Requirement: Shared synthetic scale fixture

The example layer SHALL provide a seeded synthetic generator that produces a themed graph at
caller-specified node and relationship counts, using the curated dataset vocabulary. The same seed
and counts SHALL produce the same graph, and the benchmark harness SHALL consume the same
generator.

#### Scenario: Generator is deterministic

- **WHEN** the same seed and counts are used twice
- **THEN** both graphs have identical elements and properties

#### Scenario: Benchmark reuses the fixture

- **WHEN** the benchmark harness seeds its dataset
- **THEN** it uses the same generator rather than a second implementation

#### Scenario: Requested counts are honored

- **WHEN** a caller requests a node and relationship count
- **THEN** the generated graph reports those counts

### Requirement: Validation and documentation synchronization

The example layer SHALL be covered by automated tests that build every dataset, execute every tour,
and invoke every lane entry point. The documentation SHALL include a sample-graph page with runnable
commands and a catalog link, and the documentation build SHALL pass with warnings treated as errors.

#### Scenario: Tests exercise the examples

- **WHEN** the test suite runs
- **THEN** every dataset build, tour, and lane entry point is executed

#### Scenario: Documentation is discoverable

- **WHEN** a reader opens the documentation
- **THEN** a sample-graph page is listed and links to the example catalog

#### Scenario: Documentation build is clean

- **WHEN** the documentation builds with warnings treated as errors
- **THEN** the build succeeds

### Requirement: Local-only extraction

The extractor SHALL read a caller-supplied screenplay or transcript path and SHALL emit aggregates
only. The repository and built package SHALL NOT include the source files, dialogue, or action
text, and the extractor SHALL be testable without any real script.

#### Scenario: No source file is committed

- **WHEN** the repository contents are inspected
- **THEN** no screenplay or transcript source file is present

#### Scenario: Output is aggregate

- **WHEN** the extractor processes a source file
- **THEN** its output contains counts, names, and structural metadata but no dialogue or action text

#### Scenario: Extractor is tested without a script

- **WHEN** the extractor's tests run
- **THEN** they use a small invented fixture rather than a real screenplay
