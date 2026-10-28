# Proposal

## Why

`pygrafito` has a precise, comprehensive documentation site: 27 pages, a 1,473-line
query-language reference, and runnable TRON examples. But the site reads like a specification
throughout. A reader arriving from PyPI has to reconstruct graph shapes from code, gets no summary
to orient them, and sees no consistent visual language for tips, warnings, or optional depth. The
library is friendly to embed; the docs are not friendly to learn from.

This change adds a warm onboarding voice without weakening the reference.

## What Changes

- Establish a three-zone voice: warm landing/quickstart/guides, precise reference, and generated
  API pages left unchanged.
- Add a `tl;dr` block to every reader-facing page except `api/*.md`.
- Adopt exactly five callout types, each with one job: `tl;dr` for the page summary, `Tip` for an
  optional shortcut, `Warning` for a data-loss or wrong-result risk, `Remember` for the one rule to
  carry away, and `In detail` for optional technical depth. Titles are fixed, styles are consistent,
  and callouts never nest.
- Apply emoji at level 3: card titles and badges only, never headings or prose, and all-or-nothing
  within a grid or collection.
- Treat graph examples as diagrams: a diagram of the graph precedes the first snippet for each
  distinct shape, using the same TRON names and relationship types as the code.
- Render Mermaid diagrams to SVG at build time with `mmdc`; no client-side JavaScript or CDN, and a
  broken diagram fails `sphinx-build -W`.
- Publish a documentation style guide with live examples, and encode the non-negotiables in
  `AGENTS.md`.
- Add structural documentation tests for `tl;dr`, the callout vocabulary, and diagram accessibility
  metadata.
- Update the documentation toolchain and CI to install and cache a pinned Mermaid CLI.

Out of scope: dark-mode-aware diagrams, Mermaid in `README.md`, changes to the reference's technical
content, and any new query or library feature.

## Capabilities

### New Capabilities

- `documentation-style`: the durable voice, callout, emoji, and diagram rules that every
  reader-facing page follows.

### Modified Capabilities

- None. `graph-examples` and `gql-profile` keep their existing documentation requirements; this
  change adds a presentation layer without changing what those capabilities require.

## Impact

- `docs/`: reader-facing pages gain `tl;dr`, callouts, and diagrams; new
  `docs/contributing/documentation-style.md`; new toctree caption.
- `docs/conf.py`, `docs/_static/custom.css`, `docs/puppeteer-config.json`: Mermaid SVG rendering,
  callout styling, and `<object>` sizing.
- `pyproject.toml`: `sphinxcontrib-mermaid` joins the `docs` extra.
- `AGENTS.md`: voice rules and the Node/Mermaid CLI prerequisite for documentation builds.
- `.github/workflows/ci.yml`, `.github/workflows/docs.yml`: Node setup and Mermaid CLI cache; the
  documentation build gates deployment.
- `tests/`: structural documentation-style tests.
- `CHANGELOG.md`: a user-facing note.

No runtime dependency, public API, CLI, or data-format change.
