# Tasks: release 0.9.0

## 1. Preflight and version

- [x] 1.1 Run `openspec validate release-0-9 --strict` and confirm the planning artifacts validate
  before changing release files.
- [x] 1.2 Confirm `openspec list --json` shows no other active change, `git status` is clean except
  for this change directory, and the current branch and commit are the intended release point;
  record the commit SHA and the release date. Verify with `git status --short`, `git branch
  --show-current`, and `git rev-parse HEAD`.
- [x] 1.3 Confirm `hatch version` reports `0.8.0` and `pyproject.toml` still reads the version
  dynamically from `src/pygrafito/__about__.py`; verify with `hatch version` and
  `grep -n 'dynamic\|hatch.version' pyproject.toml`.
- [x] 1.4 Run `hatch version 0.9.0`; verify `hatch version` reports `0.9.0` and
  `src/pygrafito/__about__.py` contains `__version__ = "0.9.0"`. Do not edit the version file or
  `pyproject.toml` by hand.

## 2. Changelog style and release notes

- [x] 2.1 Add the changelog style rule to `AGENTS.md` under Versioning and changelog: entries are
  short, friendly, and outcome-focused for end users; omit internal class or function names, SQL
  details, test names, file paths, and implementation mechanics; mark breaking changes plainly
  and state the migration step. Verify the rule appears in the Versioning and changelog section.
- [x] 2.2 Move every entry currently under `## [Unreleased]` into a new
  `## [0.9.0] - <release date>` section, using the date the release is cut (2026-10-27 at planning
  time), and leave an empty `## [Unreleased]` section at the top. Rewrite each entry as one or two
  short, friendly sentences that say what changed and what users can now do. Verify the top two
  headings and that the old Unreleased content is no longer above the new release section.
- [x] 2.3 Preserve every user-visible feature, change, removal, and `**BREAKING**` item while
  rewriting, and keep the migration action for 0.8 data explicit. Remove internal class or
  function names, SQL details, test names, file paths, and implementation mechanics. Verify with
  `git diff CHANGELOG.md` and a focused read of the 0.9.0 section.
- [x] 2.4 Add a short 0.9.0 release summary above the changelog categories stating that this is a
  pre-1.0 release with the composition surface, path modes, query budget, and version 2 element
  model; that the GQL profile is not yet complete and deferred features remain documented in
  `docs/reference/gql-profile.md`; and that 0.8 databases and snapshots must be exported with 0.8
  before upgrading. Verify the summary names every breaking change and links the profile.
- [x] 2.5 Audit the finished 0.9.0 section as an end user: entries are concise and friendly, the
  categories are `Added`, `Changed`, and `Removed` where needed, no empty category is added, and
  the Keep a Changelog headings and order are correct. Verify with a focused read and
  `git diff CHANGELOG.md`.

## 3. Documentation

- [x] 3.1 Update the stale version banners in `docs/guides/shell.md` (`0.8.0` and `0.6.0`) and
  `docs/reference/cli.md` (`0.6.0`) to `0.9.0`. Verify with `grep -R -E "pygrafito 0[.][68][.]"
  docs --include='*.md'` that no source documentation page still shows an older banner; do not edit
  generated files under `docs/_build/`.
- [x] 3.2 Verify the release-specific documentation remains accurate: the GQL profile's current
  status still says path semantics, the query budget, and composition are implemented and the
  expression vocabulary is the remaining gap; the embedding and snapshot references still tell
  0.8 users to export with 0.8; the shell and CLI examples show 0.9.0. Verify with a focused read
  and the docs build.
- [x] 3.3 Run `hatch run docs:build` and fix every warning. Verify the command exits successfully
  with warnings treated as errors and that the generated site reports the 0.9.0 package version.

## 4. Full validation and distribution artifacts

- [x] 4.1 Run `hatch check --fix`; verify Ruff and Pyrefly pass and that the formatter changed no
  unexpected files. Verify with `git diff --check` and `git status --short`.
- [x] 4.2 Run `hatch test`; verify the full suite passes and coverage remains at least 80%.
- [x] 4.3 Run `uv build`; verify the distribution filenames include `0.9.0`, then run `uvx twine
  check dist/*` and verify it accepts every artifact.
- [x] 4.4 Install the built wheel in a clean environment, assert
  `importlib.metadata.version("pygrafito") == "0.9.0"`, open an in-memory graph, and run the
  installed `pygrafito --help` and `python -m pygrafito --help` commands. Verify the wheel contains
  `py.typed` and `LICENSE.txt`, and that the installed package metadata reports `0.9.0`.
- [x] 4.5 Verify the release contract that the tag will use: `v$(hatch version)` equals `v0.9.0`,
  the built wheel version is `0.9.0`, and the changelog heading is `## [0.9.0]`. Verify with
  `hatch version`, the wheel metadata, and `grep -nF '## [0.9.0]' CHANGELOG.md`.

## 5. Release commit and tag

- [ ] 5.1 Review `git status` and `git diff`; ensure the release commit contains only the version,
  changelog, documentation, `AGENTS.md`, and this OpenSpec change, with no build output or local
  artifacts. Commit the release changes as `chore: release 0.9.0` and verify the commit with `git
  show --stat HEAD`.
- [ ] 5.2 Create an annotated `v0.9.0` tag on the release commit. Verify `git tag -n v0.9.0` shows
  the annotation and `git rev-parse v0.9.0^{}` matches `git rev-parse HEAD`. Do not push the tag
  in this task.
- [ ] 5.3 After explicit maintainer approval, push the release branch and the `v0.9.0` tag. Verify
  the tag-triggered release workflow starts and its check, test, tag/version, build, twine, and
  publish steps succeed; confirm PyPI serves `pygrafito 0.9.0`.

## Workflow follow-up

- Archive the change after the release is published and the project's review requirements are
  satisfied.
- Verify the archived change and tick the `release-0.9` item in `tmp/planning.md` only after the
  proposal, implementation, and archive cycle is complete. No main-spec sync is required because
  this change declares `skip_specs`.
- If a published 0.9.0 artifact is broken, do not re-tag the same version; publish a fixed 0.9.1
  and yank only if necessary.
