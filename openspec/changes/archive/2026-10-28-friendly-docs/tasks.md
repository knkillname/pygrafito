# Tasks

## 1. Documentation foundation

- [x] 1.1 Add `sphinxcontrib-mermaid` to the `docs` extra, register the extension in `docs/conf.py` with `mermaid_output_format = "svg"`, a pinned `mermaid_cmd`, the `neutral` theme with an explicit light background and font stack, and add `docs/puppeteer-config.json`; create `docs/contributing/documentation-style.md` with a purpose table and a rendered example for each of the five callouts (`tl;dr`, `Tip`, `Warning`, `Remember`, `In detail`), a sample diagram, the emoji and badge rules, the diagram conventions, a before/after rewrite, and a checklist, and add it to a new "Contributing" toctree caption. Verify `hatch run docs:build` passes, `docs/_build/html/_images/mermaid-*.svg` exists, the style guide page is reachable from the navigation, all five callout titles render distinctly, and the built page contains an `<object>` embedding the SVG with no Mermaid `<script>` tag.
- [x] 1.2 Add `.tldr` and `.detail` styles plus the `article object[type="image/svg+xml"]` sizing rule to `docs/_static/custom.css`, reusing furo's CSS custom properties. Verify the style guide renders all five callouts with distinct titles and colours, and the sample SVG is centred, block-displayed, and never wider than the content column.
- [x] 1.3 Add a "Documentation voice" section to `AGENTS.md` stating the three voice zones, the five callout types, the emoji and badge rule, the graph-before-code rule, the structural-test requirement, and the Node/Mermaid CLI prerequisite for `hatch run docs:build`, linking to the published style guide. Verify the section names the pinned CLI and does not duplicate the full guide.
- [x] 1.4 Add an `## [Unreleased]` entry to `CHANGELOG.md` describing the friendlier documentation and the new documentation build prerequisite in end-user terms, without internal names or paths. Verify the entry uses a Keep a Changelog category and states the migration step for contributors who build the docs.
- [x] 1.5 Add `actions/setup-node` and a cache for `~/.npm` and `~/.cache/puppeteer` (keyed by the pinned CLI version) to the docs jobs in `.github/workflows/ci.yml` and `.github/workflows/docs.yml`. Verify both workflow files parse as YAML and each docs job installs or resolves the pinned Mermaid CLI before `hatch run docs:build`.
- [x] 1.6 Audit every example group in the landing page, the quickstart, and the nine guides and record a diagram inventory in `docs/contributing/documentation-style.md`: page, example or section, graph shape, whether a diagram replaces prose or disambiguates the shape, and which later snippets reuse it. Mark examples that should stay prose-only. Verify every example group has an explicit decision, the inventory covers every page listed in `design.md`, and each entry names its reuse target; the reference pages are excluded because their diagrams encode semantics rather than introduce examples.

## 2. Landing page and quickstart

Use the diagram inventory from 1.6 as the source of truth for which examples get a diagram; entries marked prose-only stay prose.

- [x] 2.1 Add the `tl;dr` opener and a graph-model diagram to `docs/index.md`, and give every card in the landing grid an emoji (all four or none). Verify `hatch run docs:build` passes, the first block after the H1 is the `tl;dr`, all four cards carry an emoji, the diagram has `accTitle`, `accDescr`, and `:alt:`, and no heading contains an emoji.
- [x] 2.2 Add the `tl;dr` opener, a reader-path diagram, a Kevin/Quorra graph diagram before the first node-and-relationship snippet, and the appropriate `Tip`, `Warning`, `Remember`, and `In detail` callouts to `docs/getting-started/quickstart.md`; keep later snippets on the same graph shape reusing the diagram by reference. Verify `hatch run docs:build` passes, `hatch test tests/test_docs_examples.py` passes, the diagram names match the snippet names, and the page still leads from install to reopen without gaps.

## 3. Guides

Use the diagram inventory from 1.6 as the source of truth for which examples get a diagram; entries marked prose-only stay prose.

- [x] 3.1 Add `tl;dr`, callouts, and dataset diagrams to `docs/guides/examples.md` for the grid, cast, and places datasets and how they link. Verify `hatch run docs:build` passes, every diagram names TRON datasets and relationship types exactly as the commands use them, and the page keeps its runnable command blocks intact.
- [x] 3.2 Add `tl;dr`, callouts, and graph-shape diagrams to `docs/guides/querying.md` for matching, optional matching, and aggregation, reusing one diagram per distinct shape. Verify `hatch run docs:build` passes, `hatch test tests/test_docs_examples.py` passes, and no later snippet gets a duplicate diagram for the same shape.
- [x] 3.3 Add `tl;dr`, callouts, and diagrams to `docs/guides/indexes.md`, `docs/guides/constraints.md`, and `docs/guides/importing.md` for lookup selection, a uniqueness violation, and the JSONL import pipeline. Verify `hatch run docs:build` passes, `hatch test tests/test_docs_examples.py` passes, and each diagram has a title, description, and `:alt:`.
- [x] 3.4 Add `tl;dr`, callouts, and diagrams to `docs/guides/interop.md`, `docs/guides/shell.md`, and `docs/guides/embedding.md` for the export/import round trip, one shell session, and the connection and transaction lifecycle. Verify `hatch run docs:build` passes, `hatch test tests/test_docs_examples.py` passes, and the lifecycle diagram does not rely on colour alone.
- [x] 3.5 Add `tl;dr` and the appropriate callouts to `docs/guides/production-checklist.md`; add a diagram only if it replaces prose. Verify `hatch run docs:build` passes and the page opens with the summary.

## 4. Reference pages

- [x] 4.1 Add `tl;dr` and semantic diagrams to `docs/reference/query-language.md` and `docs/reference/gql-profile.md` for path versus walk versus trail, variable-length expansion, and the five profile tiers; keep the grammar, canonical spellings, and conformance matrix unchanged. Verify `hatch run docs:build` passes, existing heading anchors are unchanged, and no emoji appears in a heading or in the conformance matrix.
- [x] 4.2 Add `tl;dr` and selective diagrams to `docs/reference/cli.md`, `docs/reference/snapshot-format.md`, `docs/reference/index-behavior.md`, and `docs/reference/embedding-contract.md` for the file layout, planner choice, and any semantic flow that replaces prose. Verify `hatch run docs:build` passes, each page opens with the summary, and diagrams are omitted where prose is clearer.
- [x] 4.3 Add `tl;dr` and the appropriate callouts to `docs/reference/performance.md`, `docs/reference/platform-support.md`, `docs/reference/api-stability.md`, and `docs/reference/known-limitations.md`; keep the precise reference voice and add no decorative diagram. Verify `hatch run docs:build` passes, every page opens with the summary, and no guide-style asides were introduced.

## 5. Integration verification

- [x] 5.1 Add `tests/test_docs_style.py` enforcing the cross-page contract: `tl;dr` on every non-API Markdown page, only the five callout types, all-or-nothing emoji in card grids, and `accTitle`/`accDescr` on every diagram. Verify `hatch test tests/test_docs_style.py` passes and fails when a page is temporarily stripped of its `tl;dr`.
- [x] 5.2 Run `hatch run docs:build`, `hatch check --fix`, and `hatch test`; verify all three pass, the coverage gate stays at or above 80%, and the docs build reports no warnings.
- [x] 5.3 Do a visual and link pass over the built site: every diagram renders, none overflows the content column, internal links resolve, dark mode shows legible light diagram cards, and the style guide demonstrates all five callouts. Verify by inspecting the built HTML for broken `<object>` targets and recording any follow-up in the change notes.

## 6. Diagram typography

- [x] 6.1 Bundle Inter and JetBrains Mono (latin WOFF2) with their SIL Open Font License texts under `docs/_static/fonts/`, add `@font-face` and the site font stacks to `docs/_static/custom.css`, and set the diagram base font to Inter with a `themeCSS` rule for code. Verify the fonts are copied to the built site and the stylesheet references them.
- [x] 6.2 Wrap entity names in the sans-serif face and code tokens (labels, relationship types, property keys, values, and syntax) in `<code>` across every diagram, and inject the `@font-face` rules into each rendered SVG because Mermaid strips them from `themeCSS`. Verify every SVG contains the font-face URLs, every code target exists, and the diagrams still build and render.
- [x] 6.3 Document the typography rule in `docs/contributing/documentation-style.md` and `AGENTS.md`. Verify the structural documentation test still passes and the docs build reports no warnings.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived spec and the new documentation style guide agree.
