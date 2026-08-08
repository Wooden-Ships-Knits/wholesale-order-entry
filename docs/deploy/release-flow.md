# Release flow — laptop → dev → production

> Lost in the flow? [`README.md`](README.md) has the whole picture in two diagrams.

How a change gets from your editor to `order-form.woodenships-wholesale.com`.

> For the loop *before* this one — running both stacks on your own laptop, which
> rebuild a given change needs, and why an edit sometimes doesn't show up at all
> — see [`local-workflow.md`](local-workflow.md).

```
  laptop                GitHub                    GCP VM (34.101.92.203)
┌──────────┐   push   ┌──────────────┐   pull   ┌───────────────────────────┐
│ feature  │ ───────► │ feature      │ ───────► │ dev   :8083  ← reviewers  │
│ branch   │          │ branch  ─PR─►│          │ prod  :8082  ← customers  │
└──────────┘          │ main         │ ───────► │                           │
                      └──────────────┘          └───────────────────────────┘
```

| | Production | Development |
|---|---|---|
| URL | `order-form.woodenships-wholesale.com` | `dev-order-form.woodenships-wholesale.com` |
| Access | public | HTTP basic auth (`reviewer`) |
| Local port | `0.0.0.0:8082` | `127.0.0.1:8083` (never public) |
| Compose project | `wholesale-order-entry` | `wholesale-dev` |
| Env file | `.env` | `.env.dev` |
| Branch it should run | `main` | `feat/dev-environment` (integration) |
| Email | real reps and buyers | test inboxes only |
| Database | real | its own, separate |

## 1. Work on a branch

Never commit to `main` directly — it is what production runs.

```bash
git checkout main && git pull
git checkout -b feat/<something>
# …work…
git push -u origin feat/<something>
```

Run the backend tests before pushing:

```bash
cd backend && ../venv/bin/python -m pytest -q
```

See [CI](#ci--what-exists-and-what-does-not) for the caveat about the current
baseline.

## 2. Deploy that branch to dev

> Step-by-step version of this section, including the PR and migrations:
> [`deploy-to-dev.md`](deploy-to-dev.md).

On the VM:

```bash
cd ~/wholesale-order-entry
git fetch origin
git checkout <your-branch>
git pull

docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build
curl -s http://127.0.0.1:8083/api/health; echo
```

`"env":"development"` confirms the safety switches loaded. If it says
`production`, stop — `.env.dev` did not apply and the site can email real reps.

**Every dev command needs both `-f docker-compose.dev.yml` and
`--env-file .env.dev`.** Without them you are operating on production.

### Which rebuild do I need?

| Changed | Command |
|---|---|
| Backend Python | `… up -d --build backend` |
| Frontend code | `… up -d --build nginx` |
| `.env` / `.env.dev` values read by the backend | `… up -d backend` (no rebuild) |
| `frontend/.env` (e.g. the Maps key) | `… up -d --build nginx` — it is compiled into the bundle at build time, so editing the file alone changes nothing |

## 3. Review on dev

Send reviewers the URL and the basic-auth credentials. They should see a red
**DEVELOPMENT** bar on every page; if it is missing, the environment is not
protected and nothing should be tested on it.

Worth checking before you hand it over:

- [ ] The DEVELOPMENT bar is present
- [ ] A test order's email arrives at the **test** inboxes with `[DEV → …]` in
      the subject
- [ ] Address autocomplete works (the Maps browser key is referrer-restricted —
      the dev domain must be in its allowlist)
- [ ] Production still loads and has **no** bar

## 4. Merge

Two merges, not one — see [`README.md`](README.md#1-dev-means-two-different-things):

1. **`feat/<your-branch>` → `feat/dev-environment`** — done before the dev
   deploy in §2, since the dev site serves the integration branch.
2. **`feat/dev-environment` → `main`** — only after your manager has approved it
   on the dev site. This is the release gate.

Merge both on GitHub, not locally — the PR is the record of what changed and why.

## 5. Deploy to production

```bash
cd ~/wholesale-order-entry
git checkout main            # ← the step that is easy to forget
git pull
docker compose up -d --build
curl -s https://order-form.woodenships-wholesale.com/api/health; echo
```

`"env":"production"` and **no** DEVELOPMENT bar on the site.

Then re-run the dev stack from `main` too, so dev is not left on a stale branch:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build
```

## The one real footgun

**Both stacks are built from the same working copy.** The VM has a single
checkout at `~/wholesale-order-entry`, so when it sits on a feature branch for
dev testing, a plain `docker compose up -d --build` — with no `-f` — rebuilds
**production** from that branch.

Nothing warns you. The containers restart, the site keeps working, and
production is quietly running unreviewed code.

Two ways to live with it:

**a) Discipline (current).** Before any production rebuild, run
`git branch --show-current` and confirm it says `main`. Step 5 above starts with
`git checkout main` for exactly this reason.

**b) Separate checkouts (recommended).** Give dev its own directory so the two
can never share a branch:

```bash
git clone https://github.com/Wooden-Ships-Knits/wholesale-order-entry.git \
  ~/wholesale-order-entry-dev
cd ~/wholesale-order-entry-dev
cp ~/wholesale-order-entry/.env.dev .            # secrets stay off git
cp ~/wholesale-order-entry/frontend/.env frontend/
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build
```

`~/wholesale-order-entry` then stays on `main` permanently and serves only
production. The compose project names differ, so the containers, volumes and
ports do not collide.

## Rolling production back

Images are rebuilt from source, so a rollback is a checkout plus a rebuild:

```bash
cd ~/wholesale-order-entry
git log --oneline -10                # find the last good commit
git checkout <good-sha>
docker compose up -d --build
```

Then fix forward on a branch and merge properly; do not leave production on a
detached HEAD longer than the incident.

**The database does not roll back.** If the bad release ran a migration, that
migration is still applied. Check `backend/app/db/migrations/` before assuming a
code rollback is enough.

## CI — what exists, and what does not

**There is no CI.** No GitHub Actions, no automated test run, no automated
deploy. Every step above is manual and every check is a human one.

Before adding CI, two things need fixing:

1. **`pytest` is not in `backend/requirements.txt`** and is not in the image —
   the suite only runs from a local venv.
2. **The suite is red on `main`:** 17 failed, 97 passed (checked 2026-08-06).
   The failures pre-date the current work — they look like tests for the removed
   "email me a copy" checkbox and the reworked send paths. A CI gate is
   meaningless until the baseline is green or those tests are deleted.

Once both are done, this is the minimum worth having — tests on every PR:

```yaml
# .github/workflows/tests.yml
name: tests
on: [pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r backend/requirements.txt pytest
      - run: cd backend && python -m pytest -q
```

Automated **deployment** is deliberately not proposed. Deploys need a human to
check the DEVELOPMENT bar, the test-inbox emails and the Maps key on the target
domain — none of which a workflow can judge, and the cost of getting production
wrong here is emails to real customers.
