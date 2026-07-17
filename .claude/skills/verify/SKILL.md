---
name: verify
description: Build/launch/drive recipe for verifying frontend changes to the wholesale order form at runtime
---

# Verifying this repo at runtime

## Backend / API

The real stack usually already runs in Docker on this machine:
`wholesale-order-entry-nginx-1` serves the API on **http://localhost:80**
(`curl http://localhost:80/api/health` → `{"status":"ok"}`). Port 8080 on the
host belongs to a different project — don't use it.

## Frontend dev server

```bash
cd frontend && npm run dev -- --port 5199
```

Vite proxies `/api` → `http://localhost:80` (see `frontend/vite.config.js`),
so the dev page talks to the real backend. The Google Maps browser key in
`frontend/.env` works on localhost — Places autocomplete functions in
headless Chromium.

## Driving the form (Playwright)

Install Playwright + Chromium in the scratchpad (not the repo). Useful
selectors and gotchas:

- "Filled by" radios: `getByLabel('Sales Representative')`, `getByLabel('Customer', { exact: true })`.
- Internal Use "Account" radios (rep-only): `locator('label', { hasText: 'New account' }).locator('input')`.
- Address search boxes: `.map-search` — nth(0) = Bill To, nth(1) = Ship To.
- Picking a Google suggestion: `pressSequentially(text, { delay: 60 })`, wait
  for `.pac-item`, then ArrowDown + Enter (clicking `.pac-item` is flaky).
- Two checkboxes exist on the page — target "Same as Bill To" with
  `getByRole('checkbox', { name: 'Same as Bill To' })`, not `label.check input`.
- Conflict warning modal: `.conflict-modal`; a known-conflicting address is
  `233 S Wacker Dr, Chicago, IL`; a known-clear one is `Glasgow, Montana`.
- Track `/api/accounts/nearby` calls via `page.on('request', ...)` to assert
  when the check does/doesn't fire.
