# syntax=docker/dockerfile:1

# The image production runs. Railway builds it (railway.toml: builder =
# "DOCKERFILE") and CI builds and smokes the same file before a merge can
# reach it (ci.yml, "Fresh install, the way Railway builds it").
#
# Dependencies come from requirements.lock: exact versions, every file
# checked against its hash, wheels only. Nothing is resolved at build time,
# so a release on PyPI cannot change what a deploy installs - SQLAlchemy 2.1
# once broke a fresh install with no commit on our side. To change a
# dependency, edit pyproject.toml and regenerate the lock (CLAUDE.md).

FROM python:3.11-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS deps
COPY requirements.lock ./
RUN python -m venv /venv \
 && /venv/bin/pip install --require-hashes --no-deps --only-binary=:all: -r requirements.lock

FROM base AS production
COPY --from=deps /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH=/app
# The code finds data/, assets/ and webapp/ next to the package
# (vechnost_bot/paths.py), so the image keeps the checkout's layout rather
# than installing the package.
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY vechnost_bot/ ./vechnost_bot/
COPY data/ ./data/
COPY assets/ ./assets/
COPY webapp/ ./webapp/
RUN useradd --create-home --uid 10001 app
USER app

# Railway sets PORT. run_webhook serves the web process on it and runs the
# bot beside it, and stops both cleanly on SIGTERM.
EXPOSE 8000
CMD ["python", "-m", "vechnost_bot.run_webhook"]
