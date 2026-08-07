# Putting the dev environment online on the VM

Gives reviewers a real URL instead of a laptop tunnel. Same shape as production
(see [`https-and-domain.md`](https-and-domain.md)) — one more vhost, one more
port, one more cert:

```
browser ──HTTPS──> host nginx ──> 127.0.0.1:8082   production  order-form.woodenships-wholesale.com
                              └─> 127.0.0.1:8083   development dev.order-form…  ← this doc
```

Production is untouched throughout: different port, different containers,
different database volume.

## Before you start

The dev site serves **real customer data** (Salesforce reads are live). What it
cannot do is email a real rep or write to Salesforce — but the data is real, so
**put a password on it**. Step 4.

## 1. DNS

Add an A record at the registrar (GoDaddy), pointing at the same VM IP as
production:

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `dev.order-form` | `<VM static IP>` | 600 |

```bash
dig +short dev.order-form.woodenships-wholesale.com   # must return the VM IP
```

No firewall change: 80/443 are already open, and 8083 stays on loopback.

## 2. Get the code and the env file onto the VM

```bash
# on the VM, in the repo
git fetch origin
git checkout feat/dev-environment      # or main, once it is merged

cp .env .env.dev                       # start from the production secrets
```

Then edit `.env.dev` — these five lines are what make it a dev environment:

```bash
DEV_BUYER_EMAIL=ai-automation@pt-infashion.com
DEV_REP_EMAIL=webadmin@wooden-ships.com
MAIL_REDIRECT_TO=webadmin@wooden-ships.com
SALESFORCE_READONLY=1
CORS_ORIGIN=https://dev.order-form.woodenships-wholesale.com
```

`CORS_ORIGIN` is the one that is easy to forget: leave production's value there
and every `/api` call from the dev domain is blocked by the browser.

`.env.dev` is gitignored, like `.env` — it never leaves the VM.

## 3. Start the dev stack

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build
curl -s http://127.0.0.1:8083/api/health
# {"status":"ok","env":"development","dev":true,...}
```

If `env` says `production`, the switches did not load — check `.env.dev` before
going further. That value is what drives the DEVELOPMENT banner.

## 4. Password-protect it

```bash
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd-dev reviewer     # prompts for a password
```

## 5. Host-nginx vhost

`/etc/nginx/sites-available/dev-order-form`:

```nginx
server {
    listen 80;
    server_name dev.order-form.woodenships-wholesale.com;

    # Must match the container nginx — tax certs are ~14 MB base64.
    client_max_body_size 14m;

    auth_basic           "Wooden Ships — development";
    auth_basic_user_file /etc/nginx/.htpasswd-dev;

    location / {
        proxy_pass http://127.0.0.1:8083;      # the DEV port
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 5s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/dev-order-form /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 6. Certificate

```bash
sudo certbot --nginx -d dev.order-form.woodenships-wholesale.com
```

Choose **redirect**. Certbot edits this vhost only; production's is untouched.

## 7. Google Maps browser key

The Places key is referrer-restricted, so address search silently stops working
on a new domain. In Cloud Console → Credentials → that key → Website
restrictions, add:

```
https://dev.order-form.woodenships-wholesale.com/*
```

## 8. Verify

```bash
curl -I https://dev.order-form.woodenships-wholesale.com          # 401 (auth_basic working)
curl -I -u reviewer:PASSWORD https://dev.order-form.woodenships-wholesale.com   # 200
curl -s -u reviewer:PASSWORD https://dev.order-form.woodenships-wholesale.com/api/health
```

Manual checklist:

- [ ] The red **DEVELOPMENT** bar is across the top of every page
- [ ] `https://order-form.woodenships-wholesale.com` (production) still loads, no bar
- [ ] Address autocomplete works (Maps key referrer)
- [ ] A test order submits, and the email arrives at the **test** inboxes with
      `[DEV → …]` in the subject
- [ ] Accepting that order in `/admin` refuses with the read-only message
- [ ] `http://<VM ip>:8083` is **refused** — the port must not be public

## Updating dev later

```bash
git pull
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build
```

Every command needs both `-f` and `--env-file`. Without them you are rebuilding
production.

## Tearing it down

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev down       # keep the data
docker compose -f docker-compose.dev.yml --env-file .env.dev down -v    # and drop the DB
sudo rm /etc/nginx/sites-enabled/dev-order-form && sudo systemctl reload nginx
```

The cert can stay; certbot renews it harmlessly.
