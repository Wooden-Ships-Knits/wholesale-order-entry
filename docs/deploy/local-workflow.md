# Local workflow — testing your edits with Docker

> Lost in the flow? [`README.md`](README.md) has the whole picture in two diagrams.

The laptop half of the release flow. [`release-flow.md`](release-flow.md)
covers the VM (branch → dev → production); this covers the loop before that, on
your own machine.

- **Just want the command?** → [Cheat sheet](#cheat-sheet)
- **New to this?** → [Tutorial](#tutorial--test-an-edit-end-to-end)
- **Edited a file and nothing changed?** → [The one rule](#the-one-rule)

---

## Cheat sheet

Everything runs against the **dev** stack on `:8083`. Both flags are mandatory —
see [the footgun](#the-two-mistakes-everyone-makes).

```bash
# changed frontend/src/**
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build nginx

# changed backend/app/**  (then restart nginx, or you get a 502)
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build backend
docker compose -f docker-compose.dev.yml --env-file .env.dev restart nginx

# changed .env.dev only — no --build
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d backend

# watch backend logs
docker compose -f docker-compose.dev.yml --env-file .env.dev logs -f backend

# what's running / stop it
docker compose -f docker-compose.dev.yml --env-file .env.dev ps
docker compose -f docker-compose.dev.yml --env-file .env.dev down

# which environment am I on?  "dev":true = the dev stack
curl -s http://127.0.0.1:8083/api/health
```

Yes, they are long. That is deliberate: the two flags are what separate dev from
production, so they stay visible in every command rather than hidden behind an
alias you might forget to define in a new terminal.

---

## Tutorial — test an edit end to end

A full pass, using a real frontend change as the example. Roughly 2 minutes.

### Step 0 — check Docker is running

```bash
docker ps
```

If that errors with `failed to connect to the docker API`, open Docker Desktop,
wait for the whale icon to stop animating, and try again.

### Step 1 — bring the dev stack up

```bash
cd ~/Automation/wholesale-order-entry
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d
```

Confirm all three containers are up, and that `db` says `(healthy)`:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev ps
```

```
NAME                      STATUS
wholesale-dev-backend-1   Up 4 minutes
wholesale-dev-db-1        Up 5 minutes (healthy)
wholesale-dev-nginx-1     Up 10 seconds
```

If `backend` says `Restarting`, its database isn't up — see
[Everything is down after a laptop reboot](#everything-is-down-after-a-laptop-reboot).

### Step 2 — confirm you are on dev, not production

**Do this before every test session.** It is the one check that stops a test
order from emailing a real customer.

```bash
curl -s http://127.0.0.1:8083/api/health; echo
```

```json
{"status":"ok","env":"development","dev":true,
 "mailRedirected":true,"salesforceReadonly":true}
```

All three switches must be `true`. If `"env"` says `production`, stop — `.env.dev`
did not apply, and that container can email real reps and write to Salesforce.

You should also see a dark red **DEVELOPMENT** bar across the top of every page
in the browser. No bar = not protected = don't test on it.

### Step 3 — make your edit

Edit normally, in your editor. For this example, something in
`frontend/src/admin/`.

Nothing happens yet. The running container is still serving the previous build —
that is expected, and it is [the one rule](#the-one-rule).

### Step 4 — rebuild the part you changed

Frontend:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build nginx
```

Expect **~30–60 seconds** when source changed (`npm run build` re-runs), or
**~7 seconds** when nothing did (Docker reuses cached layers). If it finishes
instantly and you expected a real build, you probably edited a file that isn't
copied into the image.

Backend instead? Use `--build backend`, then `restart nginx`. See the
[full table](#which-rebuild-do-i-need) for the other cases.

### Step 5 — verify the change is actually in the container

Don't skip to the browser — this separates "my code is wrong" from "my code
isn't there", which are very different problems.

```bash
docker exec wholesale-dev-nginx-1 \
  sh -c "grep -l 'Export to Excel' /usr/share/nginx/html/assets/*.js"
```

Swap `Export to Excel` for a distinctive string from your own change. A path
printed = it's in. Silence = the image predates your edit, so the rebuild didn't
take; re-read Step 4.

### Step 6 — open it in the browser

```
http://127.0.0.1:8083/admin
```

**Hard refresh: `Cmd+Shift+R`.** A normal reload can serve a cached `index.html`
pointing at the old bundle.

Still not there? → [The button/change still isn't there](#the-buttonchange-still-isnt-there-after-a-rebuild).

### Step 7 — check the backend logs if something misbehaves

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev logs --tail 50 backend
```

Leave `-f` on the end to follow live while you click through the UI.

### Step 8 — when it works, ship it

Local testing is done. The next chapter — push, PR, and running it on the shared
dev site — is [`deploy-to-dev.md`](deploy-to-dev.md):

```bash
git add -A
git commit -m "feat: <what you did>"
git push -u origin <your-branch>
# then open a PR into main
```

Production (`:8082`) does **not** have your change yet, and won't until it is
merged and production is rebuilt. Testing on dev never touches it.

---

## The two mistakes everyone makes

**1. Dropping a flag.** Every dev command needs **both**
`-f docker-compose.dev.yml` and `--env-file .env.dev`. Drop either and Compose
falls back to `docker-compose.yml` + `.env` — you have just rebuilt
**production**. Nothing warns you: containers restart, the site keeps working,
and production is quietly running your untested code.

**2. Confusing the ports.** `:8083` is dev and safe. `:8082` is production, with
a real database, real outbound email, and a Salesforce org that accepts writes.
They look identical apart from the red DEVELOPMENT bar.

---

## The one rule

**Containers serve a build, not your source tree.**

`frontend/Dockerfile` runs `npm run build` *while the image is being built* and
copies the resulting `dist/` into nginx:

```dockerfile
FROM node:20-alpine AS build
RUN npm run build              # ← the bundle is made HERE, at image build time
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

Nothing is mounted. The running container has a *photograph* of your source from
the moment the image was built. Editing `frontend/src/...` afterwards changes the
file on disk and nothing else — the container keeps serving the old photograph
until you take a new one.

The backend works the same way: `backend/` is copied into the image, and that
includes `app/db/migrations/`, which is why a new migration needs a rebuilt image
before `alembic upgrade` can even see it.

So: **edit → rebuild → the change exists.** There is no watch mode inside the
containers.

### How to check, instead of guessing

Ask the container what it is actually serving:

```bash
# Is my change in the bundle nginx is serving?
docker exec wholesale-dev-nginx-1 \
  sh -c "grep -l 'Export to Excel' /usr/share/nginx/html/assets/*.js"
```

The `sh -c` is required, not stylistic: without it your own shell expands
`*.js` against the **host** filesystem, finds nothing, and fails with
`no matches found` before Docker is ever involved.

A hit means the image has your change and the problem is browser cache
(`Cmd+Shift+R`). No hit means the image predates your change — rebuild.

The image's own build time settles it:

```bash
docker image inspect wholesale-dev-nginx --format '{{.Created}}'
```

If that timestamp is older than your edit, the container cannot possibly have it.

---

## Which rebuild do I need?

Every dev command needs **both** `-f docker-compose.dev.yml` and
`--env-file .env.dev`. Without them you are operating on production.

| You changed | Command (dev stack) |
|---|---|
| `frontend/src/**` | `docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build nginx` |
| `frontend/.env` (Maps key) | same as above — it is compiled into the bundle at build time, so editing the file alone changes nothing |
| `frontend/package.json` | same as above — the image runs its own `npm install` |
| `backend/app/**` | `… up -d --build backend` |
| A new Alembic migration | `… up -d --build backend`, then `docker compose -f docker-compose.dev.yml --env-file .env.dev exec backend alembic upgrade head` |
| `.env.dev` values | `… up -d backend` — **no** `--build`; env vars are read at container start, not baked in |
| `docker-compose.dev.yml` | `… up -d` |

For production, drop both flags: `docker compose up -d --build nginx`.

> **`--build nginx` rebuilds the backend too.** `nginx` has `depends_on:
> backend`, so Compose brings up and rebuilds its dependency as well. Harmless —
> data lives in the `pgdata_dev` volume — and it has a useful side effect, see
> [502 after a rebuild](#502-bad-gateway-after-a-restart-or-rebuild).

---

## Three ways to run the frontend

| | URL | Sees your edits | Talks to | Use it for |
|---|---|---|---|---|
| Vite dev server | `:5173` | **instantly** (HMR) | see the warning below | writing frontend code |
| Dev stack | `:8083` | after `--build nginx` | dev backend, safe | testing the real thing before a PR |
| Prod stack | `:8082` | after `--build nginx` | **real** everything | what customers use |

### ⚠️ The Vite dev server proxies to production

`frontend/vite.config.js:18` sends `/api` to `http://localhost:8082` — which is
the **production** stack on your laptop:

```js
proxy: { '/api': 'http://localhost:8082' }
```

So `npm run dev` gives you a hot-reloading UI wired to the **real database, real
outbound email, and a Salesforce org that accepts writes**. Submitting a test
order there is a real order. Accepting one in `/admin` writes to the live org.

It is fine for pure UI work. Before touching submit, Accept, or anything that
sends email, point it at the dev stack instead:

```bash
# temporary, for one session — no file to remember to revert
npm run dev -- --port 5199
# then edit vite.config.js: '/api': 'http://localhost:8083'
```

Or skip the dev server and test on `:8083`, which is protected by
`SALESFORCE_READONLY` and `MAIL_REDIRECT_TO` by design. See
[`../dev-environment.md`](../dev-environment.md).

**Confirm which backend you are on before trusting a test:**

```bash
curl -s http://localhost:5173/api/health   # through the dev server's proxy
```

`"dev":true` is safe. `"dev":false` means you are on production — stop.

---

## Verify a deploy actually took

Three checks, in order. Skipping the first is how "it didn't work" turns into an
hour of debugging the wrong thing.

```bash
# 1. Is the backend up and is it the environment you think?
curl -s http://127.0.0.1:8083/api/health; echo
#    → {"status":"ok","env":"development","dev":true,
#       "mailRedirected":true,"salesforceReadonly":true}

# 2. Is your change in the served bundle?  (sh -c so the glob runs in the container)
docker exec wholesale-dev-nginx-1 \
  sh -c "grep -l 'something you added' /usr/share/nginx/html/assets/*.js"

# 3. Did anything crash on start?
docker compose -f docker-compose.dev.yml --env-file .env.dev logs --tail 30
```

On check 1, `"env":"production"` from port 8083 means `.env.dev` did not apply —
stop immediately, that container can email real reps.

---

## Troubleshooting

### 502 Bad Gateway after a restart or rebuild

**Cause.** `frontend/nginx.conf:15` is `proxy_pass http://backend:8080`. nginx
resolves that hostname **once, at config load**, and caches the IP for the life
of the process. Restart the backend without restarting nginx and it gets a new
container IP, while nginx keeps dialling the dead one.

**Confirm it** — the name resolves fine, but the cached IP doesn't answer:

```bash
docker exec wholesale-dev-nginx-1 wget -qO- http://backend:8080/api/health
#   → {"status":"ok",...}          ← DNS is fine, so it is a stale cache

docker logs wholesale-dev-nginx-1 --tail 3
#   → connect() failed (111: Connection refused) ... upstream: "http://172.28.0.3:8080"
docker inspect wholesale-dev-backend-1 \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
#   → 172.28.0.4                    ← different IP, that's the bug
```

**Fix.**

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev restart nginx
```

**When it happens.** Any time the backend restarts and nginx doesn't: a
`--build backend`, a crash-loop that recovers, or a Docker Desktop restart that
brings containers up in a different order. It does *not* happen after
`up -d --build nginx`, because that recreates both, with nginx starting last.

**Permanent fix, if it gets annoying.** Force per-request resolution using
Docker's internal DNS — nginx only re-resolves when the upstream is a variable:

```nginx
resolver 127.0.0.11 valid=10s;
set $backend_upstream http://backend:8080;
proxy_pass $backend_upstream;
```

Not applied today; the restart is a one-liner and the failure is loud.

### Everything is down after a laptop reboot

Docker Desktop restores containers that were *running* when the daemon stopped,
and honours each service's restart policy. The policies are **not** uniform:

| Service | Policy | Comes back on its own? |
|---|---|---|
| `db` | `no` | **No** — if it was stopped, it stays stopped |
| `backend` | `unless-stopped` | Yes |
| `nginx` | `unless-stopped` | Yes |

That asymmetry produces a specific failure: `backend` restarts, `db` doesn't, and
the backend crash-loops on `failed to resolve host 'db'` forever. `docker ps`
shows `Restarting (1)` over and over.

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d db backend
docker compose -f docker-compose.dev.yml --env-file .env.dev restart nginx
```

To make `db` come back by itself, add `restart: unless-stopped` to the `db`
service in both compose files. Deliberately not done yet — decide before
changing it.

### The button/change still isn't there after a rebuild

In order of likelihood:

1. **Browser cache** — `Cmd+Shift+R`. The bundle filename is content-hashed, so
   this is rarer than it feels, but `index.html` itself can be cached.
2. **Wrong port** — `:8083` is dev, `:8082` is production. A frontend change
   rebuilt into dev is genuinely absent from production until you rebuild that
   too.
3. **Wrong branch** — on the VM both stacks are built from one checkout. Run
   `git branch --show-current`. See
   [the footgun in release-flow.md](release-flow.md#the-one-real-footgun).
4. **Build failed but the old container kept running** — check the tail of the
   build output for an error; Compose leaves the previous container in place.

### `docker compose ps` says the daemon isn't running

```
failed to connect to the docker API at unix:///Users/<you>/.docker/run/docker.sock
```

Docker Desktop is not started. Open it, wait for the whale icon to settle, then
re-run. Nothing is lost — containers and volumes survive a daemon restart.

---

## What is *not* automated

**There is no CI.** No GitHub Actions, no automated tests, no automated deploy —
every step above and in [`release-flow.md`](release-flow.md) is run by a human.
See [that doc's CI section](release-flow.md#ci--what-exists-and-what-does-not)
for the two things that need fixing before a CI gate would be meaningful.

Practically, this means **nothing checks your work but you.** Before opening a
PR:

```bash
cd backend && ../venv/bin/python -m pytest -q     # note: suite is not green on main
cd frontend && npm run build                      # catches import/syntax errors
```

`npm run build` is the cheapest real check the frontend has — it fails on a bad
import or syntax error, which is most of what breaks a bundle.

---

## Related

| Doc | What |
|---|---|
| [`release-flow.md`](release-flow.md) | branch → dev → production, on the VM |
| [`../dev-environment.md`](../dev-environment.md) | what makes dev safe (the switches) |
| [`dev-on-vm.md`](dev-on-vm.md) | putting dev online for reviewers |
| [`../SETUP.md`](../SETUP.md) | first-time setup, database access |
