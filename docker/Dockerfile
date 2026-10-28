# Test image pinned to the SQLite runtime used by the CI test job.
#
# CI gets SQLite from the Ubuntu runner image rather than from the Python
# distribution. Building the same SQLite release here keeps local results
# comparable with CI. When the "Show SQLite version" step in CI reports a
# different version, update SQLITE_URL and SQLITE_VERSION together.
FROM python:3.13.17-slim-bookworm

ARG SQLITE_VERSION=3.45.1
ARG SQLITE_URL=https://sqlite.org/2024/sqlite-amalgamation-3450100.zip

ENV LD_LIBRARY_PATH=/opt/sqlite/lib \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential curl git unzip \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir --parents /opt/sqlite/lib /tmp/sqlite \
    && curl --fail --silent --show-error --location "$SQLITE_URL" \
        --output /tmp/sqlite/amalgamation.zip \
    && unzip -q /tmp/sqlite/amalgamation.zip -d /tmp/sqlite \
    && gcc -shared -fPIC -O2 \
        -o /opt/sqlite/lib/libsqlite3.so.0 \
        /tmp/sqlite/sqlite-amalgamation-*/sqlite3.c \
        -lpthread -ldl -lm \
    && rm -rf /tmp/sqlite

RUN python -c "import sqlite3, sys; expected = '$SQLITE_VERSION'; actual = sqlite3.sqlite_version; assert actual == expected, f'expected SQLite {expected}, got {actual}'; print(f'SQLite {actual} on Python {sys.version.split()[0]}')"

RUN python -m pip install --no-cache-dir \
    hatchling \
    hypothesis \
    pytest \
    pytest-cov

WORKDIR /workspace

CMD ["sh", "-c", "python -m pip install --quiet --no-deps --no-build-isolation . && python -m pytest -p no:cacheprovider"]
