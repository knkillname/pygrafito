# Design

## Context

See `proposal.md` for motivation. The repository has no hook infrastructure today: `.git/hooks`
contains only samples and `core.hooksPath` is unset. CI runs `hatch check`, the pytest matrix for
Python 3.13 and 3.14, a package smoke job, and a Sphinx docs build. A Docker environment already
reproduces the CI SQLite release; `docker compose run --rm test-sqlite` currently takes about 40
seconds after the image exists.

The supported platform is Linux with glibc, and the project already depends on Hatch, Git, Docker
Compose for the parity check, and Node only for documentation work.

## Goals / Non-Goals

**Goals:**

- Catch the lint, type, test, SQLite-version, and docs failures that currently surface only in CI.
- Keep the default push path honest: if the parity environment is missing, the push stops unless
  the developer explicitly opts out.
- Keep the hook versioned, readable, and independent of the developer's global Git configuration
  beyond the one-time `core.hooksPath` setting.
- Let a contributor run the same verification without pushing.

**Non-Goals:**

- Replacing CI or the package/wheel smoke job.
- Validating OpenSpec artifacts as part of every push.
- Supporting Windows hooks.
- Testing an arbitrary ref from a temporary worktree.
- Changing runtime code, dependencies, or stored formats.

## Decisions

### Native `.githooks` instead of `pre-commit`

A versioned `.githooks/pre-push` plus `git config core.hooksPath .githooks` adds no dependency and
keeps the conditional Git logic in one shell script. `pre-commit` would add another tool and a YAML
configuration surface for a single hook. The trade-off is that the setup is a documented one-time
command per clone rather than a Python-managed installation.

### Split Git concerns from verification commands

`.githooks/pre-push` owns ref parsing, clean-tree checks, docs detection, and stage messages.
`scripts/verify` owns the repeatable check sequence and accepts flags:

```text
scripts/verify [--skip-sqlite] [--docs]
```

The hook calls this script, and contributors can run it directly. This avoids duplicating the
commands between the hook, the docs, and manual use. A Hatch script was considered, but calling
`hatch check` and `hatch test` from inside a Hatch script adds a nested invocation and makes the
`--skip-sqlite` flag awkward.

### Require a clean tracked tree and HEAD match

The hook aborts when `git diff --quiet` or `git diff --cached --quiet` fails, or when a pushed
non-delete ref does not equal `git rev-parse HEAD`. This prevents the common false green where the
working tree passes but the pushed commit does not. A temporary worktree at the pushed SHA would be
more faithful but adds worktree management, separate Hatch environments, and slower setup. Pushing
a branch that is not checked out requires checking it out first or using `--no-verify`.

Untracked files are ignored: they are often local scratch or tool output and do not represent the
commit.

### Make SQLite parity mandatory with an explicit escape

The hook checks that Docker, Compose, and the daemon are available, then runs the pinned container.
A missing environment aborts with a message naming `PREGRAFITO_SKIP_SQLITE=1 git push`. A warning
and silent skip was rejected because the SQLite check is the main reason this hook exists. A
per-clone git-config switch was considered but adds state and a second configuration mechanism;
the environment variable is explicit per push.

### Build docs only for docs-relevant pushes

The hook builds docs when the pushed range changes a path under `docs/` or changes `README.md`.
For a new branch or tag there is no reliable remote range, so it builds conservatively. Always
building would put Node and the Mermaid toolchain on every code push. Treating `src/**` as
docs-relevant was rejected because the API pages use autodoc; that would make almost every push
require Node. The CI docs job remains the backstop for autodoc-only failures.

### Cover both Python environments

`scripts/verify` runs `hatch test -i py=3.13,3.14` and then the Docker suite. The Docker suite covers
Python 3.13 with the CI SQLite release; the local matrix covers both supported Python versions. This
is slower than a single `hatch test`, but it matches the CI contract instead of the current
interpreter.

### Keep checks read-only

The hook runs `hatch check`, never `hatch check --fix`. It does not stash, commit, or modify files.
A failing check leaves the tree untouched and tells the developer what to fix. `git push
--no-verify` remains the complete bypass.

## Risks / Trade-offs

- **[Docker becomes a default requirement]** -> Abort with a clear message and the
  `PREGRAFITO_SKIP_SQLITE=1` escape; document both in the testing guide.
- **[Push latency grows to roughly 70 seconds]** -> Print one labeled line per stage with elapsed
  time; keep `--no-verify` available for emergencies.
- **[Pushing another branch or a dirty tree is blocked]** -> Document the clean-tree and HEAD rules;
  contributors can check out the branch or bypass deliberately.
- **[Docs built for a remote range that is wrong or stale]** -> If the range cannot be computed,
  build docs conservatively rather than skipping.
- **[Autodoc breakage from `src/**` is not caught locally]** -> CI docs job remains the backstop;
  extend the trigger later if this proves noisy.
- **[Hooks are bypassable and per-clone]** -> Treat the hook as a convenience gate; CI and branch
  protection remain authoritative.
- **[Shell logic is not covered by pytest]** -> Keep the Git-specific script small, separate the
  repeatable checks into `scripts/verify`, and add a manual verification checklist plus a
  temporary-repository smoke test where practical.

## Migration Plan

1. Add `.githooks/pre-push`, `scripts/verify`, tests, and documentation.
2. Contributors enable the hook once with `git config core.hooksPath .githooks`.
3. To roll back, run `git config --unset core.hooksPath` and remove or ignore the files.
4. No database, package, or API migration is involved.

## Open Questions

- Should a later change extend the hook to the package/wheel smoke job and `src/**` docs triggers?
  Both are deliberately deferred; CI remains the backstop for now.
