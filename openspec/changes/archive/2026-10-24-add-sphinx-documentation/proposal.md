# Proposal

## Why

`pygrafito` has careful reference material but no on-ramp. The 749-line README is the only
tutorial, the eight `docs/*.md` pages open with reference prose, and there is no site navigation
or generated API reference. A developer evaluating the library must read far more than a few
minutes' worth before getting a graph working, and the public API has no browsable documentation.
The current Markdown also only reads well on GitHub; it is not a documentation site.

## What Changes

- Add a Sphinx site under `docs/`, using MyST Markdown and the Furo theme, and publish it to
  GitHub Pages.
- Add a landing page and a tested five-minute quickstart with runnable, TRON-themed examples.
- Rewrite the guides with one task-first template: promise, first example, tasks, link to the
  deeper reference.
- Split the five dual-purpose pages into a guide and a reference page: query language, CLI,
  interop, indexes, and embedding.
- Keep constraints, import, and performance as single-purpose pages where splitting would
  fragment a coherent topic.
- Add a public API reference generated from docstrings, grouped into Graph/Transaction, data
  model, query results, administration, and errors. Internal modules stay undocumented.
- Compact `README.md` to a GitHub/PyPI landing with one tested example and links to the site and
  API; the long feature tour moves into the guides and reference.
- Add optional `docs` dependencies, a Hatch docs environment, and a GitHub Pages workflow that
  treats Sphinx warnings as errors.
- Add tests that execute Python examples in the landing page, quickstart, and guides, and
  syntax-check examples in reference and API pages.
- Update the `Documentation` URL in `pyproject.toml`, the docs commands and paths in
  `AGENTS.md`, and add a `CHANGELOG.md` entry.
- No runtime behavior, public API signature, storage format, or query semantics change.
  **BREAKING**: none.

## Capabilities

### New Capabilities

None. This is a documentation and developer-workflow change. No runtime capability or observable
behavior changes, so `.openspec.yaml` sets `skip_specs: true` instead of inventing requirements
that do not describe product behavior.

### Modified Capabilities

None. Existing capability specs remain authoritative and unchanged.

## Impact

- **Documentation**: `docs/` is restructured and gains Sphinx configuration, navigation, guides,
  reference pages, and API pages. Old `docs/*.md` paths move, so README and AGENTS links are
  updated. No documentation site has been published, so no redirects are required.
- **Tooling**: new optional `docs` dependency group, `hatch run docs:build` and
  `hatch run docs:serve`, and a new `.github/workflows/docs.yml` for build checks and GitHub Pages
  deployment.
- **Tests**: `tests/test_readme.py` continues to execute the compact README; a new documentation
  example test covers the site. CI builds the site with `sphinx-build -W --keep-going`.
- **Package metadata**: the `Documentation` URL becomes
  `https://knkillname.github.io/pygrafito/`. Runtime dependencies remain empty.
- **Source**: only docstring clarifications that remove an internal cross-reference and document
  public attributes in the API reference; no code behavior changes.
