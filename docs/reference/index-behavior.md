# Index behavior

:::{admonition} tl;dr
:class: tldr

How property indexes scope keys, which predicates become seeks, how the planner chooses, and what an
index costs. Use it to read an access plan; start with the indexes guide for the task.
:::

This page is the reference for property-index scope, accelerated predicates, planner behavior,
cost, persistence, and interaction with uniqueness constraints. For a task-first introduction,
start with [Speed up property filters](../guides/indexes.md).

A property index is an explicit, persistent acceleration structure over one property
key. Declaring an index never changes what a query returns; it only changes how much
work the engine does to find the rows.

## Declaring an index

Indexes are declared on a graph handle and are key-scoped:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_node("Program", designation="Tron", cycles=40)
    kevin = next(iter(graph.find_nodes("Program", designation="Kevin Flynn")))
    quorra = next(iter(graph.find_nodes("Program", designation="Quorra")))
    graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)

    cycles = graph.create_node_index("cycles")
    since = graph.create_relationship_index("since_cycle")
    print(cycles)  # Index(kind=<IndexKind.NODE: 'node'>, key='cycles')
    print([index.key for index in graph.indexes()])  # ['cycles', 'since_cycle']

    result = graph.query(
        "MATCH (n:Program) WHERE n.cycles >= 37 RETURN n.designation AS name ORDER BY name"
    )
    print([row["name"] for row in result])  # ['Quorra', 'Tron']

    graph.drop_index(since)
    print([index.key for index in graph.indexes()])  # ['cycles']
```

Declaring the same index twice is a no-op. Removing an index that was never declared
raises `NotFoundError`. Index changes are rejected with `TransactionError` while an
explicit transaction is open on the same graph handle.

## Key scope, not label scope

An index covers one property key across every node, or one key across every
relationship. It is not attached to a label. This matches the stored layout: a label is
a separate table row, so a label-scoped index would need a different property
representation.

The practical consequences:

- `create_node_index("cycles")` helps every query that filters on `cycles`, whatever
  label it also requires.
- Two labels that both carry `cycles` share the same index.
- A query whose label is far more selective than its property value may still be
  planned through the label index. The engine does not intersect indexes.

Label filtering itself is a structural concern, not a declared property index. Node
labels and relationship labels each have their own lookup index, so a relationship label
filter without a bound endpoint does not scan every relationship. A relationship property
index still covers every relationship that stores the key, whatever labels it carries and
whether it is directed or undirected.

## What an index accelerates

```{mermaid}
:alt: A seekable predicate uses the index; a non-seekable predicate scans candidates and filters rows.

flowchart TD
  P["Predicate"] --> S{"Seekable form?"}
  S -->|"<code>=, &gt;, &gt;=, &lt;, &lt;=, IN</code>"| I["Index seek"]
  S -->|"negation, null check, <code>STARTS WITH</code>, <code>ORDER BY</code>"| C["Candidate scan"]
  I --> F["Row filter"]
  C --> F
  accTitle: Seekable and non-seekable predicates
  accDescr: Equality, range, and IN predicates can use the index to seek matching rows. Negated filters, null checks, STARTS WITH, and a bare ORDER BY scan candidates and filter them.
```

| Predicate | Accelerated |
| --- | --- |
| `n.cycles = 36` | yes |
| `n.cycles > 36`, `>=`, `<`, `<=` | yes |
| `n.cycles IN [36, 37]` | yes |
| `n.cycles <> 36` | no (the negated scan stays a scan) |
| `n.cycles IS NULL` / `IS NOT NULL` | no |
| `n.designation STARTS WITH 'K'` | no |
| `ORDER BY n.cycles` | no |
| `n.ratio = 2.7710821668887726e-173` | may read candidates; results are unchanged |

The first three forms are the ones that turn a scan into a seek. The rest fall back to
reading the candidate rows, which is correct but not faster.

Real equality is exact: it compares the stored JSON number text, so a real value that
SQLite's JSON parser would round still matches only itself and not its neighbors. The
declared index stores the parsed `json_extract` value rather than the exact number text,
so a real equality filter can read candidate rows instead of seeking. Integer, boolean,
string, and list equality keep the seek shown above. Declaring or removing an index never
changes which real values match.

## Cost

Every declared index adds work to every write of that property key, and it occupies
space in the database file. Declare the keys your queries actually filter on, not every
key you store. An index on a key with a handful of distinct values across a large table
is usually not worth its maintenance cost.

Writes remain ACID: SQLite updates the index inside the same transaction as the row, so
a rolled-back write cannot leave a stale index entry.

## Persistence

Declared indexes live in the database file and are discovered automatically when the
graph is reopened. Declaring or removing an index does not change the schema version, so
a file that carries indexes remains usable by a build that does not create any: unknown
indexes are simply ignored.

## Indexes and uniqueness constraints

Uniqueness constraints use standard indexes and triggers too, but they are a separate
concept with their own API. `Graph.indexes()` reports only indexes declared through
`Graph.create_node_index` and `Graph.create_relationship_index`; the support index of a
node constraint and the support index of a relationship constraint are owned by the
constraint and are not listed. Declaring an ordinary index on a relationship key already
covered by a relationship constraint is redundant. See [Enforce unique values](../guides/constraints.md)
for declaration, enforcement, and violation reporting.

## Property key handling

Indexes and filters address a property key with an escaped JSON path when the key has a
portable path. Keys may contain dots, spaces, single quotes, double quotes, backslashes,
and Unicode; they are matched literally. Keys may not contain null characters, because a
JSON path is a C string in SQLite.

A key that contains a double quote or a control character has no portable JSON path
before SQLite 3.47: those builds cannot read an escaped quote or a literal control
character inside a quoted label. The engine matches such a key by scanning the stored
property object with `json_each` instead. A declared index on that key is still reported,
persists, and keeps results identical, but it does not accelerate lookups; filters on the
key scan candidate elements on every supported SQLite version. A uniqueness constraint on
such a key keeps its triggers and stays enforced; its support index is omitted. Ordinary
keys keep the indexed fast path.

## Reading a plan

`Graph.explain` compiles a statement and returns its access plan without running it, so
you can see whether a filter is using an index or scanning:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    graph.add_node("Program", designation="Quorra", cycles=37)

    statement = "MATCH (n:Program) WHERE n.cycles = 37 RETURN n"
    print(graph.explain(statement))
    # ('SCAN n0', 'SEARCH label_0 EXISTS USING PRIMARY KEY (node_id=? AND label=?)')

    graph.create_node_index("cycles")
    print(graph.explain(statement))
    # ('SEARCH n0 USING INDEX pygrafito_idx_node_..., ...')
```

The plan is read-only: explaining a write statement creates, changes, and deletes
nothing. A statement with no read stage returns an empty tuple because it has no
access path to explain; an `UNWIND` stage reports its own line. Pattern property
values that are computed from an input row are planned with a placeholder value,
so the plan is representative rather than row-specific.

## When an index is not used

Plan choice belongs to the query planner. After an index is declared the engine
refreshes planning statistics, and closing a file-backed graph runs SQLite's optimize
pass so the next connection plans with current information. If a query still scans, the
statement is probably not one of the accelerated forms above, or the planner judged the
label index cheaper.
