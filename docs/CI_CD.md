# CI/CD

Three workflows, one rule: what runs on a push to `master` is the gate
between a merge and production, because Railway deploys `master` only once
every workflow on the commit has passed.

```
pull request ──► CI ───────────── lint · types · tests · the production image, built and smoked
             └─► Two-user E2E ─── PostgreSQL (in-process + live + races) · fuzz · browsers
merge to master ──► the same two ──► all green? ──► Railway deploys ──► /health answers?
                                                                         │ yes: traffic moves
                                                                         └► Production smoke
nightly ──► both again, the long fuzz, the suite on today's PyPI ──► an issue if anything failed
every 3 h ──► Production smoke (read-only)
```

## The workflows

| Workflow | Runs on | Jobs | What a red job means |
|---|---|---|---|
| `ci.yml` | PR, push to master, nightly, manual | `lint` (ruff; the typed domain layer; the rest of the package against `.mypy-baseline`; advisory: `ruff format`, vulture, deptry, and pip-audit on both locks, which fails only at night), `test` (the whole suite with Redis and coverage, red below the floor; on a PR, the coverage of the changed lines in the job summary), `install-smoke` (the `Dockerfile` Railway builds: every module imported inside the image, the web process served from it and smoked), `upstream` (nightly only: the suite on today's PyPI, unpinned) | Code, types or a dependency are broken, or coverage fell below the floor. A red `upstream` with every other job green is a release upstream that the lock keeps away from production (this is how the SQLAlchemy 2.1 break is now caught). |
| `e2e.yml` | PR, push to master, nightly, manual | `postgres` (PostgreSQL-only tests, then the two-user suite in-process and over real HTTP against a live server, with the race tests and the production smoke), `fuzz` (three users doing anything; 120×80 on a PR, 400×100 at night), `browser` (two Chromium phones through a room, the test and the board) | Something two people do together is broken. The log has the two-user transcript, the fuzzer's shrunk reproduction, or screenshots and traces in the job's artifacts. |
| `production-smoke.yml` | a successful deployment, every 3 hours, manual | `smoke`: `scripts/smoke_production.py` against `PRODUCTION_URL` | Production is down, is not the commit that was deployed, lost a content API, or answers anonymous callers where it should refuse them. |

The two-user harness is described in [`tests/e2e/README.md`](../tests/e2e/README.md).

## One-time setup

1. **Railway: wait for CI.** In the Railway service, *Settings → Source*,
   turn on **Wait for CI**. Railway then holds each deploy of `master` in
   *Waiting* until every GitHub workflow on the commit has finished, and
   skips it if one failed. (The toggle appears once the repository has a
   workflow that runs on `push`, which `ci.yml` and `e2e.yml` both do.)
2. **Railway: health check.** Already in `railway.toml`
   (`healthcheckPath = "/health"`): a new deploy receives traffic only once
   it answers, and the previous deploy keeps serving until then. A build
   that cannot start no longer replaces a working one with a restart loop.
3. **GitHub: the production URL.** *Settings → Secrets and variables →
   Actions → Variables → New repository variable*: `PRODUCTION_URL` =
   the public base URL of the web process (e.g.
   `https://your-app.up.railway.app`). Without it the smoke workflow skips
   itself. No secret is needed: the smoke only reads. The smoke runs only
   for a deployment whose GitHub environment ends in `production`, so a PR
   or staging environment never sends it waiting for a commit production
   does not have; if Railway reports yours under another name, set
   `PRODUCTION_ENVIRONMENT` to that exact name as well.
4. **GitHub: protect `master`** (recommended). *Settings → Branches → Add
   rule* for `master`: require a pull request, and require these checks to
   pass. A check is named after its job's `name:` where it has one, so the
   list is `lint`, `test`, `Fresh install, the way Railway builds it`,
   `Two users on PostgreSQL`, `Three people doing anything` and
   `Two phones in Chromium`. Then a red PR cannot be merged at all, and
   "Wait for CI" is the second lock rather than the only one. Leave
   `Today's PyPI, unpinned` out: it runs only at night, and an upstream
   release is not a reason to block a merge.

## Why the smoke does not run on push

"Wait for CI" waits for *every* workflow on the commit. A smoke test that
runs on push waits for the deploy; the deploy waits for the smoke test.
Neither moves until the smoke times out and fails, and a failed workflow
makes Railway skip the deploy. So the smoke runs on `deployment_status`
(Railway reports deployments to GitHub), on a schedule, and by hand — never
on push. When it runs for a deployment it first waits, up to ten minutes,
for `/health` to report the deployed commit (`RAILWAY_GIT_COMMIT_SHA`), so
it never tests the old process by mistake.

## Two ratchets

Both only move one way, and both say what to do when they stop a pull
request.

- **Coverage.** `test` fails below `--cov-fail-under` in `ci.yml`: the total
  it measured, rounded down (88 % on 2026-09-27, measured 88.6 %). Raise the
  number when a change raises the total; a change that would lower it adds
  the missing test instead. `[tool.coverage]` in `pyproject.toml` follows
  greenlets, threads and subprocesses, without which the API modules and
  `run_webhook.py` read far lower than they are.
- **Types.** `scripts/typecheck.sh` holds the domain layer to the strict
  settings. Everything else is held to `.mypy-baseline`, the errors mypy
  reported when the ratchet was set: `scripts/mypy_ratchet.py` fails on an
  error that is not listed, and on a listed one that has been fixed, so the
  file only shrinks (`python scripts/mypy_ratchet.py --update`, committed
  with the fix).

`pip-audit` is deliberately not a ratchet. An advisory is published against
a pinned version without any commit of ours, and a blocking audit would hold
every merge and, through "Wait for CI", every deploy until upstream ships a
fix. It is advisory on pull requests and pushes and fails the nightly run,
which turns a new advisory into the `ci-nightly` issue.

The actions the workflows use are on their Node 24 majors, and Dependabot
(`.github/dependabot.yml`) proposes updates to them once a week.

## Dependencies are locked

Every job except `upstream` installs `requirements-dev.lock` (development)
or, in the image, `requirements.lock` (production): exact versions, every
file checked against its hash, and `pip check` fails a job whose
`pyproject.toml` asks for something the lock does not satisfy. How to change
a dependency and regenerate the locks: [`RAILWAY_DEPLOYMENT.md`](RAILWAY_DEPLOYMENT.md).

## Running it yourself

```bash
pip install --require-hashes --no-deps -r requirements-dev.lock && pip install --no-deps -e .
pytest --cov                                        # what `test` runs
ruff check . && ./scripts/typecheck.sh && python scripts/mypy_ratchet.py   # what `lint` gates on
pytest tests/e2e -n0                                # the two-user suite, in-process
E2E_BROWSER=1 pytest tests/e2e/browser -n0          # two phones (needs .[e2e] + Chromium)
python scripts/smoke_production.py https://your-app.up.railway.app
python scripts/smoke_production.py https://your-app.up.railway.app --deep   # + database and bot heartbeat
```

PostgreSQL locally: start a server, then

```bash
POSTGRES_TEST_URL=postgresql+asyncpg://postgres@localhost:5432/postgres pytest tests/test_postgres.py -n0
E2E_DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/vechnost_e2e pytest tests/e2e -n0
```

## When the nightly run fails

Each workflow opens an issue with a link to the run, or comments on the
open one: `ci-nightly` for `ci.yml`, `e2e-nightly` for `e2e.yml`. GitHub
itself mails a failed scheduled run only to whoever last edited its cron
line. A nightly failure with no new commit is either an upstream release
- `upstream` is red and its `upstream-freeze` artifact, set against
`requirements.lock`, shows what moved; production is unaffected until the
lock is regenerated - or a bug the long fuzz reached for the first time, in
which case the job log ends with the shortest sequence of steps that
reproduces it.
