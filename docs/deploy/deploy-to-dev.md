# Deploy to dev — push, PR, and get it reviewed

> Lost in the flow? [`README.md`](README.md) has the whole picture in two diagrams.

Continues from [`local-workflow.md`](local-workflow.md), which ends when your
change works in Docker on your laptop. This is the next chapter: getting it in
front of your manager for approval, before it can go anywhere near production.

---

## First, the thing that confuses everyone

**"dev" is two things, and they are deliberately paired.**

| "dev" | What | Where |
|---|---|---|
| the **branch** | `feat/dev-environment` — collects approved feature PRs | GitHub |
| the **environment** | a second set of containers, port `8083` | the VM |

There is no branch named literally `dev`; the integration branch is called
`feat/dev-environment`. Its `feat/` prefix makes it look temporary, but it is
long-lived, it is **the base of your PR**, and it is **what the dev environment
runs**.

### Why the extra hop exists

`main` is what production runs, so nothing reaches it unapproved. The integration
branch is the holding area where work waits for sign-off:

```
feat/your-branch ──PR──► feat/dev-environment ──deploy──► dev site :8083
                                                              │
                                                       manager reviews
                                                              │
                                                          approved
                                                              │
                          feat/dev-environment ──PR──► main ──► production
```

Two merges, two different moments:

1. **Your PR → `feat/dev-environment`** — merged once *you* are happy with it.
   Nothing is live yet.
2. **`feat/dev-environment` → `main`** — merged only after your **manager has
   approved it on the dev site**. This is the gate.

So the order matters: **merge your PR first, then deploy.** The dev site serves
the integration branch, so your change is not visible there until it has been
merged into it.

Confirm the convention any time:

```bash
git log --oneline --merges -6 origin/feat/dev-environment   # feature PRs land here
git log --oneline --merges -3 origin/main                   # this branch lands there
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

- **Base:** `feat/dev-environment`  ·  **Compare:** `feat/<your-branch>`
- In the description, say what to click on the dev site to see the change — your
  manager should not have to guess.

> ⚠️ **GitHub defaults the base to `main`.** You have to change it in the
> dropdown every time. Getting it wrong aims your single feature straight at
> production's branch, skipping the review gate entirely.

## Step 3 — merge your PR into the integration branch

Merge it on GitHub once the diff is right. Nothing is live yet — this only moves
your work into the branch the dev site is built from.

```bash
# on your laptop, so local doesn't drift
git checkout feat/dev-environment
git pull
```

## Step 4 — get onto the VM

```bash
ssh <vm>
cd ~/wholesale-order-entry
```

> **Confirm this line for your setup.** The repo docs establish the VM
> (`34.101.92.203`) and the checkout path `~/wholesale-order-entry`, but not how
> you personally log in. If you use the Google Cloud SDK it will be
> `gcloud compute ssh <instance> --zone <zone>`. Ask for it to be filled in here
> once, so nobody has to rediscover it.

## Step 5 — check which branch the VM is on ⚠️

**Do this before anything else.** The VM has a **single checkout** shared by both
stacks, so the branch it sits on is also the branch production would be rebuilt
from.

```bash
git branch --show-current
git status --short              # must be clean; the VM is not a place to edit
```

If there are uncommitted changes on the VM, someone edited files directly on the
server. Find out why before you overwrite them.

## Step 6 — check out the integration branch

Not your feature branch — the dev site serves `feat/dev-environment`, which now
contains your work from Step 3.

```bash
git fetch origin
git checkout feat/dev-environment
git pull
```

`git fetch` first, or `checkout` will not see commits pushed minutes ago.

Confirm your commit is actually there before rebuilding:

```bash
git log --oneline -3
```

## Step 7 — rebuild the dev stack

Both flags are mandatory. Without them you rebuild **production** from an
unreleased branch, silently.

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

## Step 8 — apply migrations, if there are any

Dev has its **own database** (`pgdata_dev` volume), so a schema change on the
integration branch has never been applied there. Check:

```bash
git diff --name-only main...HEAD -- backend/app/db/migrations/
```

Anything listed → apply them:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev \
  exec backend alembic upgrade head

# confirm it landed
docker compose -f docker-compose.dev.yml --env-file .env.dev \
  exec backend alembic current
```

Migrations are baked into the image, so Step 7's rebuild has to come **first** —
`alembic` cannot see a migration that is not in the running image.

> **Two migrations with the same number = two heads**, and the backend refuses to
> start (`Multiple head revisions are present`). The integration branch already
> carries a fix for exactly that (`0017_merge_heads.py`, merging the two
> `0016`s). If you hit it, `alembic heads` shows them and a merge revision is the
> fix.

## Step 9 — verify before telling your manager

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

Check it yourself before handing it over. Your manager finding it broken costs a
review round; you finding it costs two minutes.

If the change isn't visible, work through
[the checklist in local-workflow.md](local-workflow.md#the-buttonchange-still-isnt-there-after-a-rebuild)
— the causes are identical on the VM.

## Step 10 — hand it to your manager

Send the dev URL, the basic-auth credentials, and **what to click**. Point at the
PR for the diff.

**Revisions requested?** Go back to your laptop, start a new feature branch (or
continue the same one), and repeat from Step 1. Each round is another small PR
into `feat/dev-environment`, then a rebuild of dev.

**Approved?** → Step 11.

## Step 11 — ship the batch to production

A separate decision, often days later, once everything in the batch is approved.
Open a second PR:

- **Base:** `main`  ·  **Compare:** `feat/dev-environment`

Merge it on GitHub, then deploy production and put dev back on `main` so the
next cycle starts clean:

```bash
cd ~/wholesale-order-entry
git checkout main            # ← the step that is easy to forget
git pull

docker compose up -d --build                                                 # production
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build   # dev, back on main
```

Full production procedure, including rollback:
[`release-flow.md`](release-flow.md#5-deploy-to-production).

Then, on your laptop:

```bash
git checkout main && git pull
```

---

## The one that will bite you

**One checkout, two stacks.** While the VM sits on `feat/dev-environment` for
review, a plain `docker compose up -d --build` — no `-f`, no `--env-file` —
rebuilds **production** from that branch. That is precisely the unapproved code
the review gate exists to keep out.

Nothing warns you. Containers restart, the site keeps working, and production is
quietly serving work your manager has not signed off.

Habit that prevents it: **`git branch --show-current` before every production
rebuild.** Step 11 starts with `git checkout main` for this reason.

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

### My change isn't on the dev site

Most likely your PR has not been merged into `feat/dev-environment` yet — the dev
site serves that branch, not your feature branch. Check on the VM:

```bash
git log --oneline -5        # is your commit in this branch?
```

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
| [`README.md`](README.md) | the full picture, with diagrams |
| [`local-workflow.md`](local-workflow.md) | the laptop loop, before this |
| [`release-flow.md`](release-flow.md) | the whole path including production |
| [`dev-on-vm.md`](dev-on-vm.md) | first-time dev setup: DNS, cert, vhost, password |
| [`../dev-environment.md`](../dev-environment.md) | what makes dev safe to point at real data |
