# Testing

:::{admonition} tl;dr
:class: tldr

Run `hatch test` for the normal suite. Run `docker compose run --rm test-sqlite` to repeat it on
the same SQLite release as CI. The container builds that release from source and fails if the
runtime reports a different version.
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
