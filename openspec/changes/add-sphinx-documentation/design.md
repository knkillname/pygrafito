# Design

## Context

See `proposal.md` for motivation. The current documentation is a 749-line `README.md` plus eight
flat Markdown pages under `docs/`. There is no Sphinx configuration, no documentation dependency,
no API reference, and no published site. The package exposes its public surface through
`pygrafito.__all__`; docstrings are NumPy style and already contain some reStructuredText roles.
`tests/test_readme.py` executes every Python fence in the README. The repository is public on
GitHub (`knkillname/pygrafito`, branch `main`) and CI already uses Hatch and uv on Python 3.14.

The documentation must remain readable in the repository. This rules out a wholesale conversion to
reStructuredText even though the published site is the primary destination.

## Goals / Non-Goals

**Goals:**

- Make the published site the canonical reading path: landing page, five-minute quickstart,
  task-oriented guides, reference pages, and public API reference.
- Preserve every durable fact currently in `docs/*.md`; splitting moves material, it does not
  discard it.
- Give guides and reference pages distinct jobs so the same table or grammar is not maintained in
  two places.
- Build and deploy automatically, with Sphinx warnings treated as errors.
- Keep runtime dependencies at zero; documentation tooling is optional.
- Keep every example in the onboarding path executable by the test suite.

**Non-Goals:**

- Rewriting the runtime library, public API, storage format, query semantics, or CLI behavior.
- Documenting `engine`, `storage`, or `cli` internals.
- Versioned documentation, localized documentation, or a search service beyond Sphinx's built-in
  search.
- Redirects from old documentation URLs. No site has been published, so there are no external URLs
  to preserve.
- Adding a tutorial voice to every reference page. Reference pages stay reference-shaped.

## Decisions

### 1. Sphinx with MyST Markdown everywhere

Use Sphinx for the site and MyST-Parser for all source pages, including API pages. Existing
Markdown stays readable on GitHub and no page has to be converted to reStructuredText. Autodoc
directives work inside MyST colon fences.

**Alternative considered:** reStructuredText everywhere. Rejected because it is a large mechanical
conversion, makes repository reading worse, and provides no capability the site needs.

**Alternative considered:** Markdown guides plus reStructuredText API pages. Rejected because two
source languages add authoring friction for a small gain; MyST handles the autodoc directives.

### 2. Selective guide/reference split

Only pages that genuinely mix a task and a reference are split:

```text
query-language -> guides/querying.md + reference/query-language.md
cli            -> guides/shell.md + reference/cli.md
interop        -> guides/interop.md + reference/snapshot-format.md
indexes        -> guides/indexes.md + reference/index-behavior.md
embedding      -> guides/embedding.md + reference/embedding-contract.md
```

`constraints`, `import`, and `performance` remain single pages. They are short enough that a split
would create two thin pages and duplicate context. Constraints keeps its type-sensitivity and
storage details in the same guide because they explain how to diagnose a violation. Import is
already task-first. Performance is explanation and measurement, not a how-to.

**Alternative considered:** splitting every page for uniformity. Rejected as artificial for the
short pages.

**Alternative considered:** splitting only the three largest pages. Rejected because indexes and
embedding also have clear task/reference halves and would leave an inconsistent model.

### 3. Guide and reference ownership

Each guide follows one template:

```text
1. Promise: one sentence saying when to read the page
2. First example: complete, copy-pasteable, TRON-themed
3. Tasks: declare/check/remove or run/inspect/persist
4. Go deeper: links to reference anchors and API classes
```

Reference pages own exhaustive detail: grammar, predicate tables, record schemas, planner rules,
journal modes, and edge cases. Guides link to those anchors instead of copying tables. This is the
main defence against drift.

Every Python fence in `docs/index.md`, `docs/getting-started/quickstart.md`, and `docs/guides/*.md`
is a complete program: it opens its own graph and needs no hidden setup. This makes the "copy the
snippet" path reliable and lets the test suite execute the fences directly. Reference and API
pages may contain fragments because they illustrate a rule, not a workflow.

### 4. Public-only API reference generated from docstrings

The API pages document exactly the names in `pygrafito.__all__`, grouped as:

| Page | Contents |
| --- | --- |
| `api/index.md` | How to read the reference, version, public surface, value shapes |
| `api/graph.md` | `Graph`, `Transaction` |
| `api/model.md` | `Node`, `Relationship`, `Path`, `TraversalStep`, `Direction`, `ElementKind` |
| `api/query.md` | `PreparedQuery`, `QueryResult`, `Row`, `MutationSummary`, `ImportSummary` |
| `api/admin.md` | `Index`, `Constraint`, `InteropSummary` |
| `api/errors.md` | `PygrafitoError` hierarchy and public attributes |

Autodoc is configured with Napoleon for NumPy-style docstrings, `viewcode` for source links, and
`intersphinx` for Python types. Enum values are presented as small manual tables because autodoc
does not render enum members well.

**Internal constructor signatures.** `Graph`, `Transaction`, and `PreparedQuery` take internal
objects in `__init__`. A small `autodoc-process-signature` hook in `docs/conf.py` suppresses the
signature for those three classes, and each page says to construct them through `Graph.open` or
`Graph.transaction`. The same hook hides the class signatures of `Node` and `Relationship`, whose
data-class signatures expose non-public value aliases, and of `Direction` and `ElementKind`, whose
`(*values)` signature is not useful; their parameter tables remain in the class docstrings. This
is documentation-only behaviour; no public API changes. The hook lives in `conf.py` behind a small
class with a static method, plus the module-level `setup(app)` that Sphinx requires.

**Type aliases.** `Value`, `QueryValue`, and `FilePath` appear in signatures but are not public
names. `autodoc_type_aliases` renders them readably, and `nitpick_ignore` covers the references
that intentionally have no public target. They are described in prose rather than exported solely
for documentation.

**Known internal reference.** `Graph.open` points at
`pygrafito.storage.connection.Database.BUSY_TIMEOUT_MS` in its docstring. Replace that reference
with the literal contract ("5000 milliseconds") so the public API page has no dangling reference
and does not expose an internal class.

### 5. Site navigation and theme

Use Furo with built-in search, light/dark mode, and edit-this-page links. `sphinx-design` provides
cards on the landing page; `sphinx-copybutton` adds copy controls to code blocks. The root
`index.md` toctree uses captions for Start, Guides, Reference, and API. There are no section index
pages; the sidebar grouping is enough, avoiding thin landing pages.

`myst_heading_anchors = 3` makes heading anchors stable so guides can link to reference sections.
Cross-document links keep the `.md` extension in source and resolve to HTML during the build.

### 6. Build and dependency wiring

Documentation dependencies are optional:

```toml
[project.optional-dependencies]
docs = [
    "sphinx>=9.0",
    "myst-parser>=4.0",
    "furo>=2025.9",
    "sphinx-copybutton>=0.5",
    "sphinx-design>=0.6",
    "sphinx-autobuild>=2024.10",
]
```

A Hatch environment installs the project with that extra and provides the canonical commands:

```toml
[tool.hatch.envs.docs]
features = ["docs"]

[tool.hatch.envs.docs.scripts]
build = "sphinx-build -W --keep-going -b html docs docs/_build/html"
serve = "sphinx-autobuild docs docs/_build/html"
```

This keeps `hatch run docs:build` alongside `hatch check` and `hatch test` instead of introducing a
separate uv-only workflow. `docs/_build/` is already ignored.

Sphinx reads `release` from `importlib.metadata.version("pygrafito")`; the installed package is
available because the Hatch environment installs the project. No `sys.path` hack is needed.

### 7. GitHub Pages deployment

Add `.github/workflows/docs.yml`:

- On pull requests: build with `hatch run docs:build`; fail on warnings.
- On pushes to `main`: build, upload `docs/_build/html` with `actions/upload-pages-artifact`, and
  deploy with `actions/deploy-pages`.
- Permissions: `contents: read`, `pages: write`, `id-token: write`.
- Use the `github-pages` environment and a concurrency group to avoid overlapping deployments.
- Enable `sphinx.ext.githubpages` so the artifact contains `.nojekyll`.
- Set `html_baseurl = "https://knkillname.github.io/pygrafito/"`.

The existing `ci.yml` remains the code quality and test gate. The docs workflow owns the site
build, so a docs failure blocks deployment without duplicating the build in `ci.yml`.

**Alternative considered:** Read the Docs. Rejected because the user chose GitHub Pages; Pages also
keeps deployment inside the existing GitHub workflow model.

### 8. Example testing

Keep `tests/test_readme.py` unchanged in behaviour. Add `tests/test_docs_examples.py` with the same
execution pattern:

- Execute every `python` fence in `docs/index.md`, `docs/getting-started/quickstart.md`, and
  `docs/guides/*.md`.
- Parse every `python` fence in `docs/reference/*.md` and `docs/api/*.md` with `ast.parse`.
- Ignore `console`, `text`, `sql`, and `jsonl` fences.
- Run with a temporary working directory and captured stdout, as the README test does.

This guarantees the onboarding path and catches syntax errors in fragments without forcing every
reference snippet to become a standalone program.

### 9. Compact README and link migration

Reduce `README.md` to badges, a short pitch, installation, one tested quickstart, a compact feature
list, a documentation link table, and the license. The long feature tour is not lost: it becomes
the guides and reference pages. Use absolute GitHub Pages URLs for PyPI, because relative
repository links do not resolve on PyPI.

Update the `Documentation` URL in `pyproject.toml`, the docs path in `AGENTS.md`, and any
repository links to old `docs/*.md` paths. Leave historical `CHANGELOG.md` prose alone; it is not a
link table. Add an `Unreleased` entry covering the site, the split, the build command, and the
README change.

## Risks / Trade-offs

- **Content rewrite is the bulk of the work.** → Move the five reference pages first, preserving
  their facts, then write the guides against those anchors. Rewrite one page at a time and keep the
  reference as the source of truth.
- **Guide and reference can drift.** → The ownership rule says reference owns tables and grammar;
  guides link instead of reproducing. `-W` catches broken anchors, and review checks that new
  facts land in the reference first.
- **MyST link or anchor resolution can fail.** → Enable heading anchors, build with `-W`, and let
  CI fail on unresolved references. No `nitpicky` ignore for public names.
- **Autodoc can expose internal constructors or aliases.** → Suppress the three signatures and use
  `nitpick_ignore` only for the three non-public type aliases. Review the rendered API pages.
- **Sphinx or theme versions may lag Python 3.14.** → The docs CI job runs on Python 3.14 from the
  first commit; dependency lower bounds are adjusted there, not in the runtime package.
- **GitHub Pages permissions or environment setup can fail on first deploy.** → Use the standard
  configure/upload/deploy actions, declare the `github-pages` environment, and verify a manual
  workflow run before merging.
- **A compact README gives PyPI readers less detail.** → Keep a complete quickstart and a prominent
  link to the site; the README remains useful without the feature tour.
- **Old repository links can break.** → Search for `docs/` references in README, AGENTS, and
  pyproject and update them in the same task as the move.
- **`nitpicky` can produce noise from third-party annotations.** → Limit ignores to explicitly
  documented non-public aliases; fix any public-name warning instead of suppressing it.

## Migration Plan

1. Add the docs extra, Hatch docs environment, `docs/conf.py`, and a minimal `docs/index.md`; verify
   `hatch run docs:build` succeeds with `-W`.
2. Add the landing page and quickstart with complete examples; add the docs example test and make
   the onboarding path executable.
3. Move the five reference halves into `docs/reference/`, then write the five task-first guides
   against them. Convert constraints, import, and performance into their final guide/reference
   form.
4. Add the grouped API pages, the constructor-signature hook, type-alias handling, and the
   `Graph.open` docstring clarification.
5. Compact the README, update AGENTS and `pyproject.toml`, and add the changelog entry.
6. Add the GitHub Pages workflow, run a pull-request build, then deploy from `main`.
7. Run `hatch check --fix` and `hatch test`; confirm coverage remains at least 80%.

Rollback is a revert of the change. The library, its storage, and its published package behaviour
are untouched; unpublishing the Pages site is independent of the package.

## Open Questions

None. Theme, split scope, API scope, source format, and hosting are decided. Minor wording and
ordering choices within a page do not change the plan.
