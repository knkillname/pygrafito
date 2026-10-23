# Design

## Context

See `proposal.md` for motivation. The repository is an empty hatch scaffold: `src/pygrafito/__init__.py` contains only a license header, there is no runtime code, no development tooling configured, and no prior specs. The local toolchain is Python 3.14 with SQLite 3.53, where JSON1 and FTS5 are available. The package currently declares `requires-python = ">=3.8"`, which conflicts with the requested 3.14-only style.

Hard constraints from the project:

- standard library only at runtime;
- strict type hints and numpydoc docstrings on every public method;
- no module-level functions; all helpers live in classes;
- import modules or classes only, never functions or constants;
- no `__future__` imports, no cyclic imports;
- `hatch check --fix` and `hatch test` as the quality gates, coverage at least 80%.

## Goals / Non-Goals

**Goals:**

- A single-file or in-memory property graph with ACID behavior.
- Precise property-graph semantics: labels, typed directed relationships, strict values, detach-delete, and relationship-unique trails.
- A layered design where the Python API is the engine's native surface and a future declarative query-language front-end can compile onto the same operations.
- Predictable behavior under SQLite's dynamic typing and JSON storage.

**Non-Goals:**

- A textual declarative graph-query language parser or execution engine, a network protocol or server mode, clustering, or multi-process access.
- Declared property indexes and uniqueness constraints.
- Path counting, all-shortest-paths, SCC condensation, or weighted shortest paths.
- Async or thread-safe operation.

## Decisions

### D1: SQLite schema with JSON properties

Three tables hold the graph. Properties are canonical JSON text, not EAV rows and not JSONB.

```sql
PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE nodes (
    id    INTEGER PRIMARY KEY,
    props TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(props))
);

CREATE TABLE node_labels (
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    label   TEXT NOT NULL,
    PRIMARY KEY (node_id, label)
) WITHOUT ROWID;
CREATE INDEX node_labels_by_label ON node_labels (label, node_id);

CREATE TABLE relationships (
    id       INTEGER PRIMARY KEY,
    src      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE RESTRICT,
    dst      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE RESTRICT,
    rel_type TEXT NOT NULL,
    props    TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(props))
);
CREATE INDEX rel_by_src ON relationships (src, rel_type, dst);
CREATE INDEX rel_by_dst ON relationships (dst, rel_type, src);
```

Rationale:

- **JSON text over EAV.** A node is read as one row, and JSON1 provides filtering without a property table. EAV would multiply rows per property and complicate whole-node reads.
- **JSON text over JSONB.** JSONB (3.45+) is smaller and faster to parse, but text is inspectable, portable, and sufficient at this scale.
- **No property index tables in the MVP.** A label lookup plus `json_extract` filtering is adequate for the target size. SQLite expression indexes remain a later option.
- `CHECK (json_valid(props))` is a cheap backstop for external corruption.
- `ON DELETE RESTRICT` on relationships prevents orphaned edges; detach-delete removes edges explicitly before the node. `node_labels` cascades.
- `PRAGMA user_version` provides a migration hook without a metadata table.

### D2: Strict `PropertyCodec`

A single class owns value validation, JSON encoding/decoding, and JSON path construction.

```
type Scalar = bool | int | float | str
type Value = Scalar | list[Scalar]
```

Validation order and rules:

1. `bool` before `int`, because `bool` is an `int` subclass in Python.
2. `int` must satisfy `-2**63 <= n <= 2**63 - 1`.
3. `float` must be finite (`math.isfinite`).
4. `str` is accepted as-is.
5. `list` must contain only scalars of one kind; an empty list is accepted.
6. `dict`, nested lists, `None` as a stored value, and any other type are rejected.
7. A property assignment of `None` means removal, handled before encoding.

Encoding uses `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. Canonical separators make stored list text deterministic, so equality on lists is reliable.

SQLite's JSON functions collapse booleans and numbers at the SQL layer: `json_extract` returns `true` as integer `1`, and `1 = 1.0`. Equality and range predicates therefore pair the value with its JSON type:

```sql
json_type(props, '$."age"') = 'integer'
AND json_extract(props, '$."age"') = ?
```

`json_type` reports `'true'`/`'false'` for booleans, `'integer'`, `'real'`, `'text'`, and `'array'`, and returns `NULL` for a missing key. That preserves the distinction between booleans, integers, floats, strings, and lists. JSON paths are always quoted and escaped (`$."key"`), never built as `'$.' || key`, so dotted and spaced keys are safe.

### D3: Immutable snapshots with explicit writes

`Node`, `Relationship`, `Path`, and `TraversalStep` are frozen, slotted dataclasses (`import dataclasses`, not `from dataclasses import ...`). `Node` implements `collections.abc.Mapping` so callers can write `node["name"]`, and exposes labels as a `frozenset`. The property mapping is wrapped in `types.MappingProxyType` so the snapshot cannot be mutated even though the frozen dataclass only protects attributes.

Writes happen only through `Graph` and `Transaction`. Reads return snapshots.

Alternatives considered:

- **Attached mutable nodes** (`node["age"] = 37` persists): ergonomic but hides transaction boundaries, makes reads hit SQLite, and fights the functional guideline.
- **Immutable update returning a new snapshot:** pure, but confuses Python identity with database identity and makes bulk writes awkward.

### D4: One connection, explicit transactions

`Graph` owns exactly one `sqlite3.Connection` with `check_same_thread=True`, `isolation_level=None`, `PRAGMA foreign_keys=ON`, and `busy_timeout`. File databases use WAL; `:memory:` is supported.

`Transaction` is a context manager:

```
BEGIN IMMEDIATE
  ... writes ...
COMMIT            on success
ROLLBACK          on exception
```

`Graph` convenience writes open one short-lived `Transaction` per call, so a single write is atomic. Bulk writes use `with graph.transaction() as tx:` and pay one commit. `Transaction` implements the write operations; `Graph` delegates to it, avoiding duplicated write logic. Reads go through repositories.

Alternative considered: thread-local connections. Deferred because SQLite still serializes writers and the embedded single-user model does not justify the extra lifecycle.

### D5: Layering and import direction

```
src/pygrafito/
  __init__.py            public re-exports
  model.py               Node, Relationship, Path, Direction, TraversalStep,
                         Value/Scalar aliases, error hierarchy
  storage/
    connection.py        sqlite3 wrapper, pragmas, version check
    schema.py            DDL, user_version, schema bootstrap
    codec.py             PropertyCodec
    nodes.py             NodeRepository
    relationships.py     RelationshipRepository
  engine/
    graph.py             Graph facade, Graph.open
    transaction.py       Transaction unit of work
    traversal.py         TraversalQuery, evaluators, adjacency snapshot
```

Imports point one way only:

```
model  <-  storage  <-  engine  <-  __init__
```

`model` knows nothing about SQLite. `storage` knows nothing about the facade. `engine` may import both. No module imports a module that imports it back.

Module-level functions are avoided. Constants become class attributes (for example `Schema.VERSION`). Dependency injection is constructor-based (`NodeRepository(connection, codec)`), which avoids global state and makes tests independent.

### D6: Demand-driven traversal

The traversal layer separates the semantic question from the evaluation strategy.

```
PathQuery: start, end?, direction, types, min_depth, max_depth, demand
```

Evaluators:

- **Reachability (`traverse`)** — layered BFS with a global visited set. Yields each reachable node once with its shortest depth. This is exact under relationship-unique trail semantics for existence and distance: any shortest walk is a simple path, hence a trail, and any walk can be reduced to a trail without increasing length.
- **Shortest path (`shortest_path`)** — bidirectional BFS from both endpoints, reconstructing one path. `start == end` returns a zero-length path. A `max_depth` bound stops the search early.
- **Path enumeration (`paths`)** — iterative DFS over an adjacency snapshot with a per-path set of used relationship ids. Nodes may repeat; relationships may not. Backward BFS computes `distance_to_target` once per query and prunes branches where `distance_to_target[node] > remaining_depth`. Results are generated lazily and capped by an optional `limit`.
- **Deferred: `count_paths`** — the Held-Karp style DP over `(node, used_relationship_mask)` is designed but not part of the MVP. A naive `(node, depth)` DP is rejected because it counts walks, not trails.

Parallel relationships are distinct because paths carry relationship ids, not endpoint pairs. Self-loops are ordinary relationships.

Snapshot consistency: when iteration starts, the evaluator materializes the adjacency needed for the traversal (or a versioned cache) from the current committed state. Later writes through the same handle do not change the in-progress result. Holding a read transaction across a Python generator would be more memory-efficient but complicates commit timing; the MVP prefers the materialized snapshot.

### D7: Equality lookups only in the MVP

`find_nodes(*labels, **properties)` and `find_relationships(rel_type=None, **properties)` implement exact-match filtering. The generated SQL joins `node_labels` when labels are present and adds one type-guarded `json_extract` predicate per property.

A composable condition tree with range, prefix, membership, and boolean operators was considered. It is the right long-term bridge to a declarative query language's filtering clause, and JSON1 makes it cheap to compile, but it is not required to validate the MVP. Deferring it keeps the first version small without closing the door: the repository API can accept a predicate tree later without changing the schema.

`**properties` accepts arbitrary string keys when callers pass an unpacked mapping, so dotted keys are supported even though direct keyword syntax requires identifiers.

### D8: Identity and deletion

- `INTEGER PRIMARY KEY` ids; SQLite may reuse an id after deletion. The guarantee is uniqueness among live elements, not permanence as an external key.
- Labels, relationship types, and property keys must be non-empty strings.
- `delete(relationship)` removes the edge.
- `delete(node, detach=False)` checks for incident relationships; if any exist it raises `ConnectedNodeError`. With `detach=True`, incident edges are deleted first, then the node.

### D9: Error hierarchy

```
PygrafitoError
  ValidationError
  NotFoundError
  ConnectedNodeError
  TransactionError
  UnsupportedSqliteError
```

`PropertyCodec` raises `ValidationError` for bad values; repositories raise `NotFoundError`; `Transaction` wraps commit/rollback failures as `TransactionError`; `Graph.open` raises `UnsupportedSqliteError` when JSON1 is unavailable. SQLite exceptions are not leaked unchanged except where they are genuinely diagnostic.

### D10: Python 3.14 packaging and tooling

- `requires-python = ">=3.14"`; classifiers trimmed accordingly.
- `[tool.ruff]` with `target-version = "py314"`, line length 100, and a strict rule set.
- `[tool.mypy]` with `strict = true`, `python_version = "3.14"`.
- `[tool.pytest.ini_options]` with coverage enabled, `fail_under = 80`, branch coverage, and `:memory:`-friendly defaults.
- Hatch's built-in commands are the gates: `hatch check --fix` runs Ruff lint/format and mypy, and `hatch test` runs pytest with coverage. No custom wrapper scripts are needed.
- Ruff and mypy configuration live in `[tool.ruff]` and `[tool.mypy]`; coverage configuration lives in `[tool.coverage.*]` plus pytest options. `hatch-test` supplies pytest and coverage in its environment; any extra test dependency is declared under `[tool.hatch.envs.hatch-test]`.
- Development dependencies (`pytest`, `pytest-cov`, `ruff`, `mypy`) stay out of runtime `dependencies`.

Tests use `:memory:` SQLite for speed and `tmp_path` for reopen/persistence cases. Traversal tests use small named fixtures: a diamond, a directed cycle, parallel edges, and a self-loop.

### D11: Public API surface

```python
class Graph:
    @classmethod
    def open(cls, path: str | pathlib.Path, *, create: bool = True) -> Self: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def transaction(self) -> Transaction: ...

    def add_node(self, *labels: str, **properties: Value) -> Node: ...
    def add_relationship(self, start: Node | int, rel_type: str,
                         end: Node | int, **properties: Value) -> Relationship: ...
    def set_properties(self, element: Node | Relationship,
                       **properties: Value) -> Node | Relationship: ...
    def remove_properties(self, element: Node | Relationship,
                          *keys: str) -> Node | Relationship: ...
    def add_labels(self, node: Node | int, *labels: str) -> Node: ...
    def remove_labels(self, node: Node | int, *labels: str) -> Node: ...
    def delete(self, element: Node | Relationship, *, detach: bool = False) -> None: ...

    def node(self, node_id: int) -> Node: ...
    def relationship(self, relationship_id: int) -> Relationship: ...
    def find_nodes(self, *labels: str, **properties: Value) -> Iterator[Node]: ...
    def find_relationships(self, rel_type: str | None = None,
                           **properties: Value) -> Iterator[Relationship]: ...

    def traverse(self, start: Node | int, *, max_depth: int,
                 direction: Direction = Direction.OUTGOING,
                 types: Iterable[str] | None = None) -> Iterator[TraversalStep]: ...
    def shortest_path(self, start: Node | int, end: Node | int, *,
                      direction: Direction = Direction.OUTGOING,
                      types: Iterable[str] | None = None,
                      max_depth: int | None = None) -> Path | None: ...
    def paths(self, start: Node | int, end: Node | int, *,
              min_depth: int = 1, max_depth: int,
              direction: Direction = Direction.OUTGOING,
              types: Iterable[str] | None = None,
              limit: int | None = None) -> Iterator[Path]: ...
```

`Transaction` exposes the same write methods plus reads. `TraversalStep` is a frozen `(node, depth)` pair. `Path` carries ordered `nodes`, ordered `relationships`, `length`, `start`, and `end`.

`traverse` deliberately has no `min_depth`: a distinct-endpoint result with a minimum-depth filter would require trail enumeration to answer correctly, so that use case belongs to `paths` once multiplicity matters.

## Risks / Trade-offs

- **SQLite JSON type conflation** (`true == 1`, `1 == 1.0`) → every predicate pairs `json_type` with `json_extract`; the codec test matrix covers booleans, integers, and floats explicitly.
- **Single connection is not thread-safe** → `check_same_thread=True` turns misuse into an error; the limitation is documented and reflected in the spec.
- **Path enumeration is exponential** → `max_depth` is mandatory, `limit` is available, backward-distance pruning cuts dead branches, and results are lazy.
- **Snapshots cost memory** → adjacency is materialized per traversal; acceptable for the embedded target. A versioned cache can replace it later.
- **No property indexes** → property lookups scan the label-filtered candidate set. Acceptable for the MVP; SQLite expression indexes can be added without schema changes.
- **Id reuse after deletion** → documented behavior; callers should not treat ids as permanent external keys.
- **SQLite version variance** → open-time JSON1 check and a clear `UnsupportedSqliteError`; Python 3.14 narrows the range of bundled SQLite versions.
- **Strict style rules** (no module functions, module-only imports) → may feel verbose, but the layer boundaries stay explicit and testable.

## Migration Plan

Greenfield. There is no existing data or public API to migrate. `pyproject.toml` changes from Python 3.8 to 3.14 and gains the check/test tooling. The database schema starts at `PRAGMA user_version = 1`; future schema changes increment it. Rollback for development is simply deleting the database file.
