# Proposal

## Why

`pygrafito` is pre-1.0 and is moving to ISO/IEC 39075 (GQL) as its only query
language. GQL's element model is not the current Cypher-shaped model: an edge carries a
label set, may be undirected, and an element has stable identity. Adopting the query
language without the model would leave a GQL-looking surface over a non-GQL store and
force a second storage rewrite later. This change adopts the element model first, so the
query-language rewrite can target a settled foundation.

## What Changes

- **BREAKING** Relationships carry zero or more labels instead of exactly one non-empty
  relationship type. Node labels are unchanged.
- **BREAKING** Relationships are either directed or undirected. The stored endpoints of
  an undirected edge have no source/destination meaning.
- **BREAKING** Element ids are monotonic and are never reused after deletion. This
  replaces the current id-reuse rule.
- **BREAKING** `Relationship.type` is replaced by `Relationship.labels` and
  `Relationship.directed`. `Graph.add_relationship` and
  `Graph.find_relationships` accept label sets and a direction flag, and the
  transaction API gains the same shape.
- **BREAKING** The JSONL snapshot format becomes version 2: relationship records carry a
  `labels` array and a `directed` boolean instead of a `type` string. Version 1
  snapshots are refused with an error that names the supported version.
- The schema version becomes 2. Version 1 databases are refused with an
  unsupported-runtime error; no upgrade path is provided before 1.0.
- The relationship structural index is a label index. Property indexes remain
  key-scoped and work for edges regardless of their labels or direction.
- Relationship uniqueness constraints scope by label. An edge carrying the scope label
  is subject to the constraint, even when it carries other labels too. Relationship
  labels can be added and removed, and both operations are enforced immediately.
- Traversal follows undirected edges in either direction, and label filters replace
  type filters. The traversal API keeps its existing direction vocabulary with defined
  semantics for undirected edges.
- The read-only views become version 2: `graph_relationships` exposes a JSON `labels`
  array and a `directed` flag instead of `type`.
- The shell introspection commands report edge labels and direction. `.reltypes`
  remains the command name but reports labels.
- The current, Cypher-flavored query dialect remains available during this change as a
  transitional subset: `:TYPE` matches an edge carrying that label, `type(r)` returns
  the first sorted label, `labels(r)` returns every label, and the three pattern
  directions map onto the new edge model. Replacing the dialect with GQL is a separate
  change.
- Documentation and the changelog are updated for the data model, API, interop format,
  indexes, constraints, traversal, shell output, and the breaking-change note.

Out of scope: the GQL grammar and parser rewrite, temporal values, closed graph types,
the catalog, in-language transactions, path modes and path search, and the
`dialect="cypher"` compatibility layer. Migration and backwards compatibility are also
out of scope: 0.8 is pre-1.0 and newly published, so a version 1 database or snapshot is
refused rather than converted. Import statements keep creating single-label directed edges
until the GQL query core lands; the Python API and snapshot restore can already create the
full element model.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `property-graph`: relationships gain label sets and a directed flag, element ids
  become stable, the persisted layout moves to schema version 2 without an upgrade path,
  and the public relationship API and lookup shape change.
- `graph-indexes`: the structural relationship type index becomes a label index that
  still answers label filters without a bound endpoint.
- `graph-constraints`: relationship uniqueness constraints scope by label, and
  relationship label acquisition and removal are enforced immediately.
- `graph-traversal`: direction and label filtering, undirected edge traversal, path
  shape, snapshots, and bounded search are updated for the new edge model.
- `graph-interop`: the snapshot format becomes version 2 only, and the read-only views
  become version 2 with `labels` and `directed`.
- `graph-query-language`: the transitional dialect maps relationship types to label
  filters, exposes relationship labels, and defines the three pattern directions over
  directed and undirected edges.
- `graph-shell`: introspection and rendering report edge labels and direction.

## Impact

- Storage: `src/pygrafito/storage/schema.py`, `relationships.py`, `indexes.py`,
  `constraints.py`, `views.py`, and the version check.
- Engine: `src/pygrafito/model.py`, `engine/graph.py`, `engine/transaction.py`,
  `engine/traversal.py`, `engine/interop.py`, `engine/importing.py`, and the query
  pipeline where it reads or writes relationship types and direction.
- CLI: `src/pygrafito/cli/commands.py`, `session.py`, and `formatting.py` for
  introspection and rendering.
- Tests: relationship, index, constraint, traversal, interop, shell, import, and
  documentation-example tests; new version 1 refusal and undirected-edge fixtures.
- Documentation: data-model, querying, indexing, constraints, interop, embedding,
  performance, query-language, CLI, and API pages, plus `README.md` and
  `CHANGELOG.md`.
