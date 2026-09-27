# CI/CD

Three workflows, one rule: what runs on a push to `master` is the gate
between a merge and production, because Railway deploys `master` only once
every workflow on the commit has passed.

```
pull request ──► CI ───────────── lint · types · tests · fresh install · docker
             └─► Two-user E2E ─── PostgreSQL (in-process + live + races) · fuzz · browsers
merge to master ──► the same two ──► all green? ──► Railway deploys ──► /health answers?
                                                                         │ yes: traffic moves
                                                                         └► Production smoke
nightly ──► both again on today's PyPI, the long fuzz ──► an issue if anything failed
every 3 h ──► Production smoke (read-only)
```

## The workflows

| Workflow | Runs on | Jobs | What a red job means |
|---|---|---|---|
| `ci.yml` | PR, push to master, nightly, manual | `lint` (ruff, typed domain layer, mypy and pip-audit advisory), `test` (the whole suite with Redis, ~20 s), `install-smoke` (a clean `pip install .` the way Railway builds it, every module imported, the web process served and smoked), `docker` (the image builds, imports every module, serves `/health` and `/app/`) | Code, types or a dependency are broken. A nightly red with no commit behind it is an upstream release (this is how the SQLAlchemy 2.1 break would have been caught within a day). |
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
   itself. No secret is needed: the smoke only reads.
4. **GitHub: protect `master`** (recommended). *Settings → Branches → Add
   rule* for `master`: require a pull request, and require the checks
   `lint`, `test`, `install-smoke`, `Two users on PostgreSQL`,
   `Three people doing anything` and `Two phones in Chromium` to pass. Then
   a red PR cannot be merged at all, and "Wait for CI" is the second lock
   rather than the only one.

## Why the smoke does not run on push

"Wait for CI" waits for *every* workflow on the commit. A smoke test that
runs on push waits for the deploy; the deploy waits for the smoke test.
Neither moves until the smoke times out and fails, and a failed workflow
makes Railway skip the deploy. So the smoke runs on `deployment_status`
(Railway reports deployments to GitHub), on a schedule, and by hand — never
on push. When it runs for a deployment it first waits, up to ten minutes,
for `/health` to report the deployed commit (`RAILWAY_GIT_COMMIT_SHA`), so
it never tests the old process by mistake.

## Running it yourself

```bash
pytest                                              # what `test` runs
ruff check . && ./scripts/typecheck.sh              # what `lint` gates on
pytest tests/e2e -n0                                # the two-user suite, in-process
E2E_BROWSER=1 pytest tests/e2e/browser -n0          # two phones (needs .[e2e] + Chromium)
python scripts/smoke_production.py https://your-app.up.railway.app
```

PostgreSQL locally: start a server, then

```bash
POSTGRES_TEST_URL=postgresql+asyncpg://postgres@localhost:5432/postgres pytest tests/test_postgres.py -n0
E2E_DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/vechnost_e2e pytest tests/e2e -n0
```

## When the nightly run fails

`e2e.yml` opens an issue labelled `e2e-nightly` (or comments on the open
one) with a link to the run. A nightly failure with no new commit is either
an upstream release — compare the `runtime-freeze` artifact of `ci.yml`
with the last green night — or a bug the long fuzz reached for the first
time, in which case the job log ends with the shortest sequence of steps
that reproduces it.
