# Deploy to dev — push, PR, and run it on the VM

Continues from [`local-workflow.md`](local-workflow.md), which ends when your
change works in Docker on your laptop. This is the next chapter: getting that
branch onto the shared dev site so other people can review it.

---

## First, the thing that confuses everyone

**`dev` is an environment, not a branch.**

There is no `dev` branch in this repo — only `main` and `feat/*`:

```bash
git branch -r
#   origin/HEAD -> origin/main
#   origin/feat/dev-environment
#   origin/feat/fix-1
#   …
#   origin/main
```

So you never "merge into dev" or "PR into dev". What actually happens:

- **The PR always targets `main`.** That is the only long-lived branch.
- **Dev is a *deployment* of whatever branch you point it at.** You check your
  feature branch out on the VM and rebuild the dev containers from it.

Those two are independent. Opening the PR does not deploy anything, and
deploying to dev does not need a PR. Doing both is just the normal order:
open the PR so people can read the diff, deploy to dev so they can click it.

```
  laptop              GitHub                    GCP VM
┌──────────┐  push  ┌──────────────┐  pull   ┌──────────────────────────────┐
│ feat/xyz │ ─────► │ feat/xyz     │ ──────► │ dev  :8083  ← your branch    │
└──────────┘        │      │       │         │ prod :8082  ← main only      │
                    │      └─PR──► main ────►│                              │
                    └──────────────┘         └──────────────────────────────┘
```

---

## Step 1 — commit and push from your laptop

```bash
git branch --show-current          # confirm you are NOT on main
git status --short                 # review what you are about to commit

git add -A
git commit -m "feat: add Excel export to the admin order table"
git push -u origin feat/<your-branch>
```

Never commit to `main` directly — it is what production runs.

`-u` only matters the first time; afterwards `git push` alone is enough.

## Step 2 — open the Pull Request

The `gh` CLI is **not installed** on this machine, so use the web UI. After a
push, GitHub prints a link you can click straight from the terminal output:

```
remote: Create a pull request for 'feat/xyz' on GitHub by visiting:
remote:      https://github.com/Wooden-Ships-Knits/wholesale-order-entry/pull/new/feat/xyz
```

Otherwise go to
<https://github.com/Wooden-Ships-Knits/wholesale-order-entry> and press
**Compare & pull request**.

- **Base:** `main`  ·  **Compare:** `feat/<your-branch>`
- In the description, say what to click on dev to see the change — reviewers
  should not have to guess.

Leave it open. It gets merged in [Step 9](#step-9--after-approval), after review.

> Want `gh` so you can do this from the terminal?
> `brew install gh && gh auth login`, then `gh pr create --base main --fill`.

## Step 3 — get onto the VM

```bash
ssh <vm>
cd ~/wholesale-order-entry
```

> **Confirm this line for your setup.** The repo docs establish the VM
> (`34.101.92.203`) and the checkout path `~/wholesale-order-entry`, but not how
> you personally log in. If you use the Google Cloud SDK it will be
> `gcloud compute ssh <instance> --zone <zone>`. Ask for it to be filled in here
> once, so nobody has to rediscover it.

## Step 4 — check which branch the VM is on ⚠️

**Do this before anything else.** The VM has a **single checkout** shared by both
stacks, so the branch it sits on is also the branch production would be rebuilt
from.

```bash
git branch --show-current
git status --short              # must be clean; the VM is not a place to edit
```

If there are uncommitted changes on the VM, someone edited files directly on the
server. Find out why before you overwrite them.

## Step 5 — pull your branch

```bash
git fetch origin
git checkout feat/<your-branch>
git pull
```

`git fetch` first, or `checkout` will not see a branch you pushed minutes ago.

## Step 6 — rebuild the dev stack

Both flags are mandatory. Without them you rebuild **production** from your
unreviewed branch, silently.

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build
```

Rebuilding everything is the right default here — you have just changed branches,
so you rarely know that only the frontend moved. To check what actually changed:

```bash
git diff --name-only main...HEAD
```

Only `frontend/` paths → `… up -d --build nginx` is enough and much faster. See
the [rebuild table](local-workflow.md#which-rebuild-do-i-need).

## Step 7 — apply migrations, if your branch has any

Dev has its **own database** (`pgdata_dev` volume), so a schema change on your
branch has never been applied there. Check:

```bash
git diff --name-only main...HEAD -- backend/app/db/migrations/
```

Anything listed → apply them:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev \
  exec backend alembic upgrade head
```

```bash
# confirm it landed
docker compose -f docker-compose.dev.yml --env-file .env.dev \
  exec backend alembic current
```

Migrations are baked into the image, so Step 6's rebuild has to come **first** —
`alembic` cannot see a migration that is not in the running image.

> **Two migrations with the same number = two heads**, and the backend refuses to
> start (`Multiple head revisions are present`). This branch already carries a
> fix for exactly that (`0017_merge_heads.py`, merging the two `0016`s). If you
> hit it, `alembic heads` shows them and a merge revision is the fix.

## Step 8 — verify before telling anyone

```bash
curl -s http://127.0.0.1:8083/api/health; echo
```

```json
{"status":"ok","env":"development","dev":true,
 "mailRedirected":true,"salesforceReadonly":true}
```

**`"env":"production"` here means stop.** `.env.dev` did not load, and that
container can email real reps and write to the live Salesforce org.

Then, in a browser at
`https://dev.order-form.woodenships-wholesale.com` (basic auth: `reviewer`):

- [ ] The red **DEVELOPMENT** bar is on every page
- [ ] Your change is actually visible — hard refresh, `Cmd+Shift+R`
- [ ] Production (`order-form.woodenships-wholesale.com`) still loads, **no** bar
- [ ] Address autocomplete still works (the Maps key is referrer-restricted per
      domain)

If the change isn't visible, work through
[the checklist in local-workflow.md](local-workflow.md#the-buttonchange-still-isnt-there-after-a-rebuild)
— the causes are identical on the VM.

## Step 9 — after approval

Merge the PR **on GitHub**, not locally — the PR is the record of what changed
and why.

Then deploy production and put dev back on `main`, so the next person doesn't
inherit your branch:

```bash
cd ~/wholesale-order-entry
git checkout main            # ← the step that is easy to forget
git pull

docker compose up -d --build                                            # production
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build   # dev, back on main
```

Full production procedure, including rollback:
[`release-flow.md`](release-flow.md#5-deploy-to-production).

---

## The one that will bite you

**One checkout, two stacks.** While the VM sits on your feature branch for dev
review, a plain `docker compose up -d --build` — no `-f`, no `--env-file` —
rebuilds **production** from that branch.

Nothing warns you. Containers restart, the site keeps working, and production is
quietly serving unreviewed code.

Habit that prevents it: **`git branch --show-current` before every production
rebuild.** Step 9 starts with `git checkout main` for this reason.

The permanent fix is a second checkout so the two can never share a branch —
written up in
[release-flow.md](release-flow.md#the-one-real-footgun). Worth doing if more than
one person deploys.

---

## Troubleshooting

### 502 after the rebuild

nginx cached the backend's old container IP. Same cause and fix as locally:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev restart nginx
```

Details: [local-workflow.md](local-workflow.md#502-bad-gateway-after-a-restart-or-rebuild).

### `/api` calls blocked from the dev domain

`CORS_ORIGIN` in `.env.dev` still holds production's value. It must be:

```bash
CORS_ORIGIN=https://dev.order-form.woodenships-wholesale.com
```

Then `… up -d backend` — no `--build`, env vars are read at start.

### Address autocomplete dead on dev only

The Maps **browser** key is referrer-restricted and the dev domain is not in its
allowlist. Cloud Console → Credentials → that key → Website restrictions → add
`https://dev.order-form.woodenships-wholesale.com/*`.
See [dev-on-vm.md §7](dev-on-vm.md).

### `git checkout` refuses — local changes on the VM

Someone edited files on the server. Do not blindly discard; find out what they
were first:

```bash
git diff
```

### The dev site is asking for a password you don't have

Basic auth, user `reviewer`, set at first-time setup with `htpasswd`. Reset:

```bash
sudo htpasswd /etc/nginx/.htpasswd-dev reviewer
```

---

## Related

| Doc | What |
|---|---|
| [`local-workflow.md`](local-workflow.md) | the laptop loop, before this |
| [`release-flow.md`](release-flow.md) | the whole path including production |
| [`dev-on-vm.md`](dev-on-vm.md) | first-time dev setup: DNS, cert, vhost, password |
| [`../dev-environment.md`](../dev-environment.md) | what makes dev safe to point at real data |
