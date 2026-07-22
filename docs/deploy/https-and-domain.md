# HTTPS + Domain Setup (GCP VM)

How the wholesale order form is served over HTTPS on a custom domain, and how to
reproduce it. Current production URL: **`https://order-form.woodenships-wholesale.com`**.

> **This layer lives only on the VM, not in git.** The TLS cert and the
> host-nginx vhost are on the box under `/etc/letsencrypt` and
> `/etc/nginx/sites-*`. This doc is the record of how they were set up — the
> actual files are edited directly on the VM.

## The architecture

TLS terminates at a **host-level nginx** installed directly on the VM, in front
of the Docker stack. The app containers only speak plain HTTP.

```
browser ──HTTPS (443)──> host nginx (VM)            ← Let's Encrypt cert here
                           │  terminates TLS
                           │  proxy_pass → 127.0.0.1:8082
                           ▼
                     nginx container  (docker-compose "nginx", host :8082 → container :80)
                           │  serves the built SPA
                           │  /api/*  → backend container
                           ▼
                     backend container (FastAPI, :8080 internal)
```

Why a host nginx instead of TLS inside Docker: port 80/443 on this VM is already
owned by the host nginx (it fronts other sites too, e.g. the reports dashboard).
Each app gets its own vhost + domain proxying to its own local port. This app is
published on host **8082** (`docker-compose.yml`); the dashboard is on 8080.

The app itself needs **no changes** for HTTPS — `frontend/nginx.conf` already
forwards `X-Forwarded-Proto $scheme` end-to-end, so the backend correctly sees
`https` (this is what makes the `Secure` admin cookie work — see below).

## One-time setup

### 1. DNS (registrar: GoDaddy)

Add an A record pointing the (sub)domain at the VM's static IP:

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `order-form` | `<VM static IP>` | 600 |

GoDaddy appends the domain, giving `order-form.woodenships-wholesale.com`. Verify
before continuing:

```bash
dig +short order-form.woodenships-wholesale.com   # must return the VM IP
```

For an **apex** domain instead, use Name `@` (and a second record for `www`).

### 2. GCP firewall

Open **tcp:80 and tcp:443** to the VM. Port 80 is needed for the Let's Encrypt
HTTP-01 challenge and the 80→443 redirect; 443 for actual traffic. (The original
runbook only opened 8080/8082, so opening 80/443 is part of going HTTPS.)

```bash
gcloud compute firewall-rules list        # check what exists
```

### 3. Host-nginx vhost

`/etc/nginx/sites-available/order-form` (symlinked into `sites-enabled/`):

```nginx
server {
    listen 80;
    server_name order-form.woodenships-wholesale.com;

    # REQUIRED — must match the container nginx (frontend/nginx.conf).
    # Order submits carry the tax certificate base64-encoded (~14 MB). Without
    # this the HOST nginx returns 413 before the request reaches the container.
    client_max_body_size 14m;

    location / {
        proxy_pass http://127.0.0.1:8082;      # this app's published port
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # backend reads this
        proxy_read_timeout 120s;                      # matches order submit
        proxy_connect_timeout 5s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/order-form /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# http://order-form.woodenships-wholesale.com should now serve the form
```

### 4. Issue the cert (certbot rewrites the vhost for 443)

```bash
sudo certbot --nginx -d order-form.woodenships-wholesale.com
```

Choose **redirect** when prompted. Certbot adds `listen 443 ssl`, the
`ssl_certificate` lines, and the 80→443 redirect to the same vhost, and installs
a systemd timer for auto-renewal. (Done 2026-07-22; cert expires 2026-10-20,
auto-renews.)

### 5. Point the app at the new origin

Two things break until updated for the new domain:

**a) Backend CORS** — in the backend `.env`:
```
CORS_ORIGIN=https://order-form.woodenships-wholesale.com
```
```bash
docker compose up -d backend
```
Without this, the browser blocks every `/api` call (submit, lookup) with CORS
errors.

**b) Google Maps browser key** — the Places/autocomplete key
(`VITE_GOOGLE_MAPS_API_KEY`) is referrer-restricted. In Google Cloud Console →
Credentials → that key → **Website restrictions**, add:
```
https://order-form.woodenships-wholesale.com/*
```
Otherwise address search silently stops working on the new domain.

### 6. Verify

```bash
curl -I https://order-form.woodenships-wholesale.com     # 200 over TLS
curl -I http://order-form.woodenships-wholesale.com      # 301 → https
sudo certbot renew --dry-run                             # renewal works
```

Manual checklist:
- [ ] `https://…` loads the form (padlock, no cert warning)
- [ ] `http://…` redirects to `https://…`
- [ ] Address autocomplete works (browser Maps key referrer allowlist)
- [ ] A test order submits successfully (CORS + backend reachable)
- [ ] `/admin` login sticks (Secure cookie over HTTPS)

## The admin page over HTTPS

`/admin` is the **same site, same vhost** — no extra DNS/nginx/cert needed. It is
a client-side route in the SPA (`frontend/src/main.jsx`) and is served by the
container's SPA fallback. Reach it at:

```
https://order-form.woodenships-wholesale.com/admin
```

It is gated by a **password → signed session cookie**. Two `.env` requirements:

```
ADMIN_PASSWORD_HASH=<hash>     # generate below
SESSION_SECRET=<stable random value>   # rotating it logs everyone out
```

Generate the hash:
```bash
docker compose exec backend python -m app.admin.security "your-password"
```

**Why HTTPS is mandatory for admin:** the session cookie is `Secure`
(`config.py: session_cookie_secure = True`), so it is only sent over HTTPS. Over
plain HTTP the login appears to succeed but the cookie never comes back and you
bounce to the login form. Behind the host-nginx TLS, `X-Forwarded-Proto: https`
reaches the backend and the cookie works.

## Editing / redoing it later

```bash
ssh -i ~/.ssh/gcp_reports_vm ai_automation@<VM_IP>
sudo nano /etc/nginx/sites-enabled/order-form    # TLS + proxy_pass config
sudo nginx -t && sudo systemctl reload nginx      # validate + apply
```

## Google keys — the two-key rule

This app uses **two** Google Maps keys. Crossing them breaks features silently.
See [`conflict-checker.md`](../conflict-checker.md#the-two-keys--do-not-cross-them)
for the full troubleshooting table.

| Key | Env var | Restriction | Used by |
|---|---|---|---|
| Browser / Places | `VITE_GOOGLE_MAPS_API_KEY` | **HTTP referrers** (`https://<domain>/*`) | Maps JS + address autocomplete (frontend) |
| Server / Distance Matrix | `GOOGLE_MAPS_SERVER_API_KEY` | **IP address** (the VM) | Drive-time conflict check (backend) |

The server key must **not** be referrer-restricted — Distance Matrix rejects
those with *"API keys with referer restrictions cannot be used with this API."*
