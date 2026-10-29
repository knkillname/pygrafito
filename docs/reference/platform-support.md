# Platform support

:::{admonition} tl;dr
:class: tldr

Linux with glibc is the supported 1.x platform, and Python 3.13 and 3.14 are supported. macOS and
Windows are nightly portability signals, not supported platforms yet.
:::

This page states what a 1.x user can rely on. The contract is deliberately narrow: Linux is the
supported platform for the 1.x series, and the other operating systems are tested nightly without
blocking a release.

## Supported Python

| Python | Status |
| --- | --- |
| 3.13 | Supported |
| 3.14 | Supported |
| 3.12 and older | Not supported |

The package declares `requires-python >= 3.13` and imports only the Python standard library at
runtime. Install it with:

```console
pip install pygrafito
```

## Supported operating systems

Linux with glibc and SQLite 3.38 or newer is the supported 1.x platform. The continuous integration
gate runs the full suite on Linux for Python 3.13 and 3.14, and a failure blocks a release.

macOS and Windows run the same suite nightly for Python 3.13 and 3.14. That run is a portability
signal: a failure is reported, but it does not block a release. Those platforms are not claimed as
supported until the nightly signal is green. musl-based Linux distributions are not claimed.

The package is pure Python. Installation does not require a compiler, a system SQLite development
package, or a platform-specific wheel.

Developer tooling is the exception: `scripts/verify` and the Git pre-push hook are POSIX shell
programs. Run them through Git Bash on Windows, or run `hatch check` and `hatch test` directly.
The test suite skips only those developer-tooling tests when no POSIX shell is available.

## Google Colab

Google Colab currently runs Python 3.13, which is supported. Install the package in a notebook cell
with `!pip install pygrafito`. The runtime filesystem is ephemeral, so keep a database under
`/content` while the notebook runs, or mount Google Drive when it must survive a runtime restart.

## Property-test profiles

The test suite uses Hypothesis for adversarial input, codec, predicate, import, and snapshot
properties. The default **gate** profile runs 50 deterministic examples per property with the
example database disabled. The **nightly** profile runs 500 examples; set
`HYPOTHESIS_PROFILE=nightly` to use it locally, and the nightly workflow sets it automatically.
Both profiles disable the wall-clock deadline and the `too_slow` health check so a slow fuzz case
reports a property failure rather than a timing failure.

## Nightly schedule

The nightly workflow runs at 03:00 UTC and can also be started manually. GitHub disables scheduled
workflows after 60 days without repository activity; a new commit or a manual run re-enables it.
GitHub's scheduled-workflow failure notification is the first alert. The job summary records the
platform and Python version that failed.
