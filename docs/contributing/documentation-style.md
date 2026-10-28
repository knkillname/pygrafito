# Documentation style

:::{admonition} tl;dr
:class: tldr

This page is the rulebook for `pygrafito`'s documentation: three voice zones, five callout types,
plain headings, emoji only in cards and badges, and a diagram before each graph example. Use it
when writing or reviewing a page.
:::

The documentation has two jobs. It teaches a reader how to use the library, and it proves exactly
what the library does. Those jobs need different voices, so the site is split into zones instead of
picking one tone for every page.

## Voice zones

| Zone | Pages | Voice |
| --- | --- | --- |
| Warm | Landing page, quickstart, guides | Second person, outcome first, short paragraphs, diagrams and callouts |
| Precise | Reference pages | Rules, edge cases, canonical spellings; summaries and semantic diagrams only |
| Generated | API pages | Autodoc listings; no summary, emoji, or callouts |

A warm page may link to the reference for exact behavior. A reference page may use a diagram when
it encodes semantics, but it never adopts the guide voice. If you are unsure which zone a page
belongs to, look at where it sits in the navigation.

## Callouts

Use exactly five callout types. Each one has a fixed title and one job; do not invent a new title
such as "Note:" or "Heads up!". The `tl;dr` at the top of this page is the first example.

| Type | Purpose | Markup |
| --- | --- | --- |
| `tl;dr` | Page outcome in at most three sentences | `:::{admonition} tl;dr` + `:class: tldr` |
| `Tip` | Optional shortcut or nicer way | `:::{tip}` |
| `Warning` | Data loss, wrong result, or footgun | `:::{warning}` |
| `Remember` | The one rule to carry away | `:::{admonition} Remember` + `:class: important` |
| `In detail` | Optional technical depth; safe to skip | `:::{admonition} In detail` + `:class: detail` |

:::{tip}
Open an in-memory graph while you explore an idea. Call `Graph.open(":memory:")`, try the
statement, and close the handle when you are done. Nothing touches the filesystem.
:::

:::{warning}
A `DETACH DELETE` removes the node and every incident relationship. Use plain `DELETE` when the
statement should fail instead of removing an edge you did not mean to touch.
:::

:::{admonition} Remember
:class: important

One `Graph` handle belongs to one thread. Open it in the thread that will use it, and use the
context manager so the connection closes deterministically.
:::

:::{admonition} In detail
:class: detail

SQLite stores `true` as `1` and `1.0` as a separate JSON type. Property predicates therefore pair
`json_type(...)` with `json_extract(...)`; comparing values alone would conflate them. This is
worth knowing when you read an access plan or write a raw SQL view.
:::

A callout replaces prose; it does not repeat a paragraph. Do not nest one callout inside another.
When a page needs both optional depth and a warning, put them in separate blocks.

## Emoji and badges

Emoji are seasoning, not structure. Use them only in card titles and badges; never in headings,
body prose, callout titles, or diagrams. Headings stay plain because the documentation derives
anchors from heading text, and an emoji makes the anchor start with a stray hyphen.

Within one card grid or badge collection, be all-or-nothing: every card gets an emoji or none does,
and every card gets the same badge set or none does. A half-decorated grid reads as an accident.

Badges are limited to the guide landing cards: one reading-time badge and one level badge per card.
Do not add page-level badges or badges in the reference.

## Diagrams

Show the graph before you show the code that builds it. Every example that introduces a graph
shape gets a diagram of that shape immediately before the first snippet. Later snippets that vary
only a filter or a property reuse the diagram by reference.

```{mermaid}
:alt: Kevin Flynn has an ALLIES_WITH relationship to Quorra.

flowchart LR
  K["Kevin Flynn<br/><code>Program, User</code><br/><code>cycles=36</code>"]
  Q["Quorra<br/><code>Program, ISO</code><br/><code>cycles=37</code>"]
  K -->|"<code>ALLIES_WITH</code><br/><code>since_cycle=2020</code>"| Q
  accTitle: Kevin Flynn allies with Quorra
  accDescr: A directed relationship from Kevin Flynn to Quorra, with both nodes and the relationship properties shown.
```

The rules:

- Use the `{mermaid}` directive fence, not a bare ` ```mermaid ` fence, so the diagram can carry
  `:alt:` and a caption later.
- Every diagram has `:alt:`, `accTitle:`, and `accDescr:`. The description names the nodes and the
  relationships, not the colours.
- Use only `flowchart` and `stateDiagram-v2`.
- Use the same node names, labels, property names, and relationship types as the code. A diagram
  that disagrees with its snippet is a bug.
- Keep entity names in the sans-serif face. Wrap labels, relationship types, property keys, values,
  and syntax in `<code>`; they render in the monospaced face. The diagrams use Inter for prose and
  JetBrains Mono for code, both under the SIL Open Font License.
- Do not rely on colour alone to carry meaning, and do not put emoji inside a diagram.
- A diagram must replace prose or disambiguate a shape the code alone makes hard to see. If it is
  decoration, cut it. One diagram per distinct shape, never two in a row.

## Example inventory

The inventory records the diagram-or-prose decision for every example group in the warm zone. It
is the source of truth for page edits; when a page gains a new example, add a row here first.
Reference pages are excluded because their diagrams encode semantics rather than introduce
examples.

| Page | Example or section | Shape | Decision | Reuse |
| --- | --- | --- | --- | --- |
| `index.md` | Quickstart example | Kevin Flynn → Quorra | Diagram: shows the four stored concepts | Reused by the quickstart sections |
| `getting-started/quickstart.md` | Seven-step path | Install → open → add → query → traverse → reopen | Diagram: orients the page | None |
| `getting-started/quickstart.md` | Kevin/Quorra relationship | Kevin Flynn → Quorra | Diagram: first graph shape | Reused by the relationship and query sections |
| `getting-started/quickstart.md` | `find_nodes` filter | Three Program/ISO nodes, no edges | Prose-only: the three nodes are fully visible in the snippet | None |
| `getting-started/quickstart.md` | Traverse chain | Kevin Flynn → Quorra → Sam Flynn | Prose-only: the chain is fully visible in the snippet and its output | None |
| `guides/examples.md` | Datasets | Grid, cast, and places | Diagram: shows how the datasets link | None |
| `guides/examples.md` | Shell tours, analysis, algorithms | Command lists and tables | Prose-only: the commands are already scannable | None |
| `guides/querying.md` | Run a statement | Yori → Dumont → Ram | Diagram: first query shape | None |
| `guides/querying.md` | Match nodes and relationships | Alan Bradley → Tron and Dumont | Diagram: fan-out shape | Reused by the optional-match section |
| `guides/querying.md` | Optional match | Dumont with no outgoing `ALLIES_WITH` | Reuse the fan-out diagram | None |
| `guides/querying.md` | Aggregation | Yori → Dumont and Yori → Ram | Diagram: fan-out shape | None |
| `guides/querying.md` | Write, path modes, match modes, path search, grouped paths | Cycles and diamonds | Prose-only: the text and tables explain the shape; a diagram would duplicate the grammar | None |
| `guides/indexes.md` | Planner lookup | Query → planner → index seek or scan | Diagram: explains the access plan | Reused by the explain section |
| `guides/indexes.md` | Relationship index, explain, remove | Single relationships | Prose-only: one edge is visible in the snippet | None |
| `guides/constraints.md` | Duplicate designation | Two `Program` nodes with the same value | Diagram: shows the rejected write | None |
| `guides/constraints.md` | Type-sensitive values | Four scalar values | Prose-only: the list is the explanation | None |
| `guides/importing.md` | Import pipeline | Rows → batch → statement → graph | Diagram: one pipeline covers rows, CSV, and JSONL | Reused by the batching section |
| `guides/importing.md` | Relationship import and summary | Single rows | Prose-only: the statement shows the mapping | None |
| `guides/interop.md` | Export and restore | Graph → JSONL → Graph | Diagram: the round trip | None |
| `guides/interop.md` | SQL views | Tables and predicates | Prose-only: the query is the explanation | None |
| `guides/shell.md` | Session flow | Start → statement → output → dot command → exit | Diagram: orients the page | None |
| `guides/shell.md` | Formats, transactions, maintenance | Dot commands | Prose-only: the commands are already scannable | None |
| `guides/embedding.md` | Connection and transaction lifecycle | Open → begin → commit or rollback → close | Diagram: state and ordering | Reused by the thread, lock, and read-only sections |
| `guides/embedding.md` | Thread affinity, locks, backup, recovery | Rules and snippets | Prose-only: the rules are the explanation | None |
| `guides/production-checklist.md` | All sections | Checklist | Prose-only: the checklist is already scannable | None |

## Before and after

Before:

```{code-block} text
Graph.open accepts a filesystem path or :memory:. A missing file is created unless
create=False is passed, and readonly=True opens an existing file without write access. The
context manager closes the handle deterministically.
```

After:

```{code-block} markdown
:::{admonition} tl;dr
:class: tldr

Open a graph with Graph.open, keep the handle in one thread, and close it with the context manager.
:::

:::{admonition} In detail
:class: detail

A missing file is created unless create=False; readonly=True opens an existing file without write
access.
:::
```

The rewrite leads with the task, moves the edge cases into an optional-detail callout, and removes
the repeated "the context manager" sentence.

## Checklist

- [ ] The page sits in the right voice zone.
- [ ] A `tl;dr` appears immediately after the H1, in at most three sentences.
- [ ] Every callout is one of the five types, has its fixed title, and is not nested.
- [ ] No heading contains an emoji.
- [ ] Every card in a grid has an emoji, or none does.
- [ ] Every distinct graph shape has one diagram, and it precedes the first snippet.
- [ ] Every diagram has `:alt:`, `accTitle:`, and `accDescr:`.
- [ ] Diagram names match the code exactly.
- [ ] `hatch run docs:build` passes with no warnings.
- [ ] The structural checks in `hatch test tests/test_docs_style.py` pass.

## Go deeper

- [Five-minute quickstart](../getting-started/quickstart.md) shows the pattern in a full page.
- [Query your graph](../guides/querying.md) shows the graph-before-code convention in a long guide.
- [AGENTS.md](https://github.com/knkillname/pygrafito/blob/main/AGENTS.md) holds the non-negotiables
  that every apply run follows.
