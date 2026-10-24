# Tasks

Specs are skipped for this change (`skip_specs: true`): it changes documentation and developer
workflow only, with no runtime behaviour or public API deltas.

## 1. Sphinx scaffold and build tooling

- [x] 1.1 Add `[project.optional-dependencies].docs` and a `[tool.hatch.envs.docs]` environment
      with `build` and `serve` scripts; verify `hatch run docs:python -c "import sphinx,
      myst_parser, furo"` succeeds.
- [x] 1.2 Add `docs/conf.py` with MyST, autodoc, Napoleon, viewcode, intersphinx, githubpages,
      copybutton, and sphinx-design; add a minimal `docs/index.md` with a toctree; verify
      `hatch run docs:build` finishes without warnings.
- [x] 1.3 Configure Furo, `html_baseurl`, edit-this-page links, heading anchors, and `-W
      --keep-going`; verify the build writes `docs/_build/html/index.html` and `.nojekyll`, and
      that the search index and theme assets are present.

## 2. Onboarding path

- [x] 2.1 Write the `docs/index.md` landing page: pitch, installation, one complete TRON-themed
      example, and link cards for quickstart, guides, reference, and API; verify the example runs
      as written and the page builds with `-W`.
- [x] 2.2 Write `docs/getting-started/quickstart.md`: open an in-memory graph, add nodes, labels,
      and properties, add a relationship, run a query, traverse, then persist and reopen; verify
      every Python fence is a complete program that runs as written.
- [x] 2.3 Add `tests/test_docs_examples.py` that executes Python fences in `docs/index.md` and
      `docs/getting-started/quickstart.md`, and parses Python fences in `docs/reference/` and
      `docs/api/` when those pages exist; verify `hatch test tests/test_docs_examples.py` passes.

## 3. Reference pages

- [x] 3.1 Move `docs/query-language.md` to `docs/reference/query-language.md`, rework its opening
      for reference use, and add it to the toctree; verify `hatch run docs:build` and that the docs
      example test parses its Python fences.
- [x] 3.2 Move `docs/cli.md` to `docs/reference/cli.md`, keep every option, dot command, output
      rule, and exit code, and add it to the toctree; verify the build and parsed examples.
- [x] 3.3 Move `docs/interop.md` to `docs/reference/snapshot-format.md`, retaining the record
      grammar, value rules, strictness, restore guarantees, and SQL view schema; verify the build
      and parsed examples.
- [x] 3.4 Move `docs/indexes.md` to `docs/reference/index-behavior.md`, retaining the predicate
      table, planner rules, persistence, constraint interaction, and key handling; verify the build
      and parsed examples.
- [x] 3.5 Move `docs/embedding.md` to `docs/reference/embedding-contract.md`, retaining journal
      modes, thread affinity, lock waits, snapshots, foreign-file rules, and error remedies; verify
      the build and parsed examples.
- [x] 3.6 Move `docs/performance.md` to `docs/reference/performance.md`, keeping the method,
      measurements, interpretation, and limits; verify the build.
- [x] 3.7 Update cross-links among reference pages to their new paths and heading anchors; verify
      `hatch run docs:build` reports no unresolved references.

## 4. Task-first guides

- [x] 4.1 Write `docs/guides/querying.md`: run a statement, match nodes and relationships, filter,
      write, parameterize, and prepare a query, linking to the query-language reference and the
      query API; verify its Python fences execute and the build passes.
- [x] 4.2 Write `docs/guides/shell.md`: start an interactive session, run one-off statements and
      scripts, pipe input, choose an output format, and use import/export commands, linking to the
      CLI reference; verify its examples execute and the build passes.
- [x] 4.3 Write `docs/guides/interop.md`: export a snapshot, restore it, and read the SQL views,
      linking to the snapshot-format reference; verify its examples execute and the build passes.
- [x] 4.4 Write `docs/guides/indexes.md`: declare an index, confirm it in a plan, understand its
      key scope and cost, and drop it, linking to index behavior; verify its examples execute and
      the build passes.
- [x] 4.5 Write `docs/guides/embedding.md`: open and close a handle, respect thread affinity, set a
      busy timeout, and back up a database, linking to the embedding contract; verify its examples
      execute and the build passes.
- [x] 4.6 Rewrite `docs/guides/constraints.md` as a single task-first page: declare, observe
      type-sensitive enforcement, diagnose a violation, drop, and understand persistence; verify
      its examples execute and the build passes.
- [x] 4.7 Rewrite `docs/guides/importing.md` as a single task-first page: import in-memory rows and
      CSV/JSONL files, choose batching and atomicity, and read failure summaries; verify its
      examples execute and the build passes.

## 5. Public API reference

- [x] 5.1 Add the `autodoc-process-signature` hook for `Graph`, `Transaction`, and
      `PreparedQuery`, configure `autodoc_type_aliases` and `nitpick_ignore` for non-public
      aliases, and write `docs/api/index.md`; verify the build and that the page lists the public
      surface.
- [x] 5.2 Write `docs/api/graph.md` for `Graph` and `Transaction`, grouped by lifecycle, reads,
      writes, traversal, queries, indexes, constraints, import/export, and maintenance; verify the
      rendered page contains the public methods and no `(database)`, `(connection`, or `(executor`
      constructor signatures.
- [x] 5.3 Write `docs/api/model.md` for `Node`, `Relationship`, `Path`, `TraversalStep`,
      `Direction`, and `ElementKind`, including manual enum tables; verify the rendered page
      documents every listed name.
- [x] 5.4 Write `docs/api/query.md` for `PreparedQuery`, `QueryResult`, `Row`, `MutationSummary`,
      and `ImportSummary`; verify the rendered page documents every listed name.
- [x] 5.5 Write `docs/api/admin.md` for `Index`, `Constraint`, and `InteropSummary`; verify the
      rendered page documents every listed name.
- [x] 5.6 Write `docs/api/errors.md` for the `PygrafitoError` hierarchy and the public attributes
      of `ConstraintViolationError` and `QueryError`; verify the hierarchy and attribute tables
      render.
- [x] 5.7 Replace the internal `BUSY_TIMEOUT_MS` cross-reference in the `Graph.open` docstring with
      the literal 5000-millisecond contract; verify the API build reports no unresolved reference.

## 6. README, package metadata, and changelog

- [x] 6.1 Compact `README.md` to badges, pitch, installation, one tested quickstart, a short
      feature list, and documentation links; verify `hatch test tests/test_readme.py` passes.
- [x] 6.2 Update the `Documentation` URL in `pyproject.toml` and the docs command and path in
      `AGENTS.md`; verify no repository reference still points at a removed `docs/*.md` path.
- [x] 6.3 Add an `Unreleased` entry covering the Sphinx site, guide/reference split, API reference,
      docs build command, and compact README; verify the entry follows the Keep a Changelog
      categories used in the file.

## 7. GitHub Pages, integration, and verification

- [ ] 7.1 Add `.github/workflows/docs.yml` to build on pull requests and deploy `main` with
      `actions/configure-pages`, `actions/upload-pages-artifact`, and `actions/deploy-pages`; verify
      a pull-request run passes and the uploaded artifact contains `index.html` and `.nojekyll`.
- [ ] 7.2 Set the repository's Pages source to GitHub Actions and deploy from `main`; verify
      `https://knkillname.github.io/pygrafito/` serves the landing page.
- [x] 7.3 Run `hatch check --fix`, `hatch test`, and `hatch run docs:build`; verify all pass, the
      Sphinx build has no warnings, and coverage remains at least 80%.
- [x] 7.4 Run `openspec validate add-sphinx-documentation --strict` and
      `openspec validate --specs --strict`; verify both pass.
- [ ] 7.5 Spot-check the published site: landing to quickstart to guide to reference to API, search,
      code copy buttons, dark mode, and edit-this-page links; verify every navigation target
      resolves.

## Workflow follow-up

- Archive the change after review and after the documentation site is deployed.
- Verify the archived change and confirm the main specs still validate.
