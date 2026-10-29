# Testing

:::{admonition} tl;dr
:class: tldr

Run `hatch test` for the normal suite. Enable the versioned pre-push hook with `git config
core.hooksPath .githooks` to repeat the CI checks, including the pinned SQLite runtime, before
every push. Run the same checks manually with `scripts/verify`.
:::

## Run the suite

The test environment is managed by Hatch:

```console
hatch check --fix
hatch test
```

`hatch check --fix` runs Ruff, formats the code, and runs Pyrefly. `hatch test` runs pytest with
the configuration in `pyproject.toml`, including the 80% coverage gate. Pass a path or node id to
run a subset:

```console
hatch test tests/test_codec.py::TestJsonPaths
```

Use `:memory:` databases for unit tests and `tmp_path` for tests that reopen a file. Graph-building
tests use TRON names, as described in `AGENTS.md`.

## Run the pre-push check

Enable the versioned hook once per clone:

```console
git config core.hooksPath .githooks
```

The hook calls `scripts/verify`, which runs:

1. `hatch check`
2. `hatch test -i py=3.13,3.14`
3. `docker compose run --rm test-sqlite`

The hook also runs `hatch run docs:build` when the pushed range changes `docs/**` or `README.md`.
A new branch or tag builds the documentation conservatively.

The hook refuses to run when tracked files differ from `HEAD` or when the pushed ref is not
`HEAD`. Commit or stash local changes, and check out the branch you are pushing. When Docker or
Compose is unavailable, the push stops; use `PREGRAFITO_SKIP_SQLITE=1 git push` to skip the
container deliberately. `git push --no-verify` remains the full bypass.

Run the same checks manually:

```console
scripts/verify
scripts/verify --skip-sqlite
scripts/verify --docs
```

`scripts/verify` and the Git hook are POSIX shell programs. On Windows, run them through Git Bash
or WSL. If no POSIX shell is available, the developer-tooling tests skip with an explicit platform
reason; `hatch check` and `hatch test` still run natively.

To stop using the hook, run `git config --unset core.hooksPath`.

## Reproduce the CI SQLite runtime

CI does not use the SQLite bundled with a locally installed Python. Its Python interpreter links to
the system SQLite from the Ubuntu runner image. A newer local SQLite can therefore accept syntax
that an older CI build rejects, so a green local run is not proof that CI is green.

The Docker test environment pins the SQLite release that CI currently uses:

```console
docker compose run --rm test-sqlite
```

The image builds SQLite from the official amalgamation file, installs the package from the mounted
working tree, and runs pytest with the same `pyproject.toml` configuration. The build fails if the
runtime reports a version other than the pinned one.

### Keep the pin current

The test job prints the CI runtime under **Show SQLite version** and in the job summary. It also
warns when that value differs from the Docker pin. When the value changes, update both build
arguments in `docker/Dockerfile`:

- `SQLITE_VERSION` is the version reported by CI.
- `SQLITE_URL` points at the matching amalgamation archive on `sqlite.org`.

Rebuild without the cache to confirm the new pin:

```console
docker compose build --no-cache test-sqlite
```
