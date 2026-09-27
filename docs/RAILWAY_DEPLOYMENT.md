# Deploying to Railway

How production is built and run. The checks in front of it, and the one-time
settings that make Railway wait for them, are in [`CI_CD.md`](CI_CD.md).

## What Railway runs

One service, built from the repository's [`Dockerfile`](../Dockerfile)
(`railway.toml`: `builder = "DOCKERFILE"`).

- **The image.** `python:3.11-slim-bookworm`, dependencies from
  `requirements.lock`: exact versions, every file checked against its hash,
  wheels only, nothing resolved at build time. A release on PyPI therefore
  cannot change what a deploy installs (SQLAlchemy 2.1 once broke a fresh
  build with no commit on our side). CI builds and smokes the same image
  before a merge can reach production. The app runs as a non-root user.
- **The command.** `python -m vechnost_bot.run_webhook` runs two child
  processes: the FastAPI app (Mini App, API, Tribute webhooks) under uvicorn
  on `$PORT`, and the bot on long polling. If either dies, the other is
  stopped and the service exits non-zero, so the restart policy
  (`ON_FAILURE`, 10 retries) brings the pair back together. On SIGTERM (a
  redeploy, a stop) both are asked to finish: uvicorn drains its requests
  and the bot confirms the updates it has handled.
- **The healthcheck.** Railway moves traffic to a new deploy only once
  `/health` answers (up to 120 s), and keeps the previous one serving until
  then, so a build that cannot start never replaces a working one. `/health`
  reports the deployed commit (`RAILWAY_GIT_COMMIT_SHA`) and touches nothing
  else, on purpose: a database blip must not block a deploy. `/health/deep`
  is the thorough one - the database answers `SELECT 1` and the bot wrote
  its heartbeat in the last five minutes - and answers 503 otherwise;
  `scripts/smoke_production.py --deep` checks it.
- **The database.** PostgreSQL. Tables are created at startup, and new
  columns are added by idempotent startup steps, so a deploy needs no manual
  migration. `alembic/` is kept in step with the models
  (`tests/test_postgres.py` checks that both build the same schema).

## Variables

Set them in the service's *Variables* tab. [`env.example`](../env.example)
lists every setting with an explanation; these are the ones production
needs:

| Variable | What it is |
|---|---|
| `ENVIRONMENT` | `production`. With it the service refuses to start on a development default and says which variables to fix: a PostgreSQL `DATABASE_URL` with `+asyncpg`, an explicit `ENABLE_PAYMENT`, `TRIBUTE_API_KEY` when payments are on, an `https://` `WEBAPP_URL` when one is set. It also names the environment in Sentry. Unset, it is `development`, which checks nothing. |
| `TELEGRAM_BOT_TOKEN` | The bot's token from @BotFather. Required. |
| `DATABASE_URL` | PostgreSQL with the async driver: `postgresql+asyncpg://…`. Railway's own variable is spelled `postgresql://`; add `+asyncpg`. Without this variable the app falls back to a SQLite file inside the container, which is lost on every deploy; with `ENVIRONMENT=production` it refuses to start instead. |
| `ENABLE_PAYMENT` | `true` to enforce the paywall. Unset means `false`, everything free, so production has to say which. |
| `TRIBUTE_API_KEY` | Signs Tribute's webhooks; required when payments are on. |
| `TRIBUTE_PAYMENT_URL` | The payment page the paywall opens. |
| `ADMIN_TOKEN` | Bearer token for `/admin/*`. |
| `WEBAPP_URL` | The public HTTPS address of the Mini App, e.g. `https://<service>.up.railway.app/app/`. |
| `BOT_USERNAME` | The bot's username, for invite links. |
| `WEBAPP_MAIN_APP` / `WEBAPP_SHORT_NAME` | How invite links are spelled; see `env.example`. |
| `SENTRY_DSN` | Optional error reporting. |

`PORT`, `RAILWAY_GIT_COMMIT_SHA` and the rest of Railway's own variables are
set by the platform.

## A deploy, and going back

A merge to `master` runs CI; with "Wait for CI" on, Railway builds only a
commit whose workflows all passed, then waits for `/health` before
switching traffic. To go back, redeploy the previous deployment from the
service's *Deployments* list, or revert the commit on `master`.

## Changing a dependency

Edit `pyproject.toml`, then regenerate both locks
([uv](https://docs.astral.sh/uv/) does it in seconds):

```bash
uv pip compile pyproject.toml --python-version 3.11 --python-platform x86_64-unknown-linux-gnu --generate-hashes -o requirements.lock
uv pip compile pyproject.toml --extra dev --extra e2e -c requirements.lock --python-version 3.11 --python-platform x86_64-unknown-linux-gnu --generate-hashes -o requirements-dev.lock
```

The development lock is constrained by the production one, so tests run on
exactly the versions production runs. `uv pip compile` keeps the pins
already in a lock and changes only what `pyproject.toml` asks it to; add
`--upgrade` to the first command to move everything to today's versions.
The nightly job "Today's PyPI, unpinned" (`ci.yml`) says when that would
break something.

## When something goes wrong

- **The build fails at `pip install --require-hashes`.** The lock no longer
  matches `pyproject.toml`, or a pinned file is gone from PyPI: regenerate
  the locks as above.
- **The healthcheck never passes.** The deploy log shows why the web
  process did not start; the previous deploy keeps serving meanwhile.
  `ENVIRONMENT=production, but the configuration is not one to start with`
  is followed by the list of variables to set.
  `Database ready, but these startup steps failed` names a startup step
  that needs attention.
- **The bot is silent but the Mini App works.** The service stops when
  either process dies, so look for `[!] The bot died` in the log and the
  traceback before it. A bot that is alive but stuck does not die:
  `/health/deep` shows how long ago it last beat (`bot_heartbeat_age_s`).
