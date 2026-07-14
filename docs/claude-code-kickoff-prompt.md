# Claude Code — kickoff prompt

> How to use: create a new repo, drop `CLAUDE.md` in the root and `PRD.md` + `architecture.md`
> (and the flow diagrams) into `docs/`. Then paste the prompt below into Claude Code.

---

## Opening prompt (paste this)

You are building the Wooden Ships wholesale order form web app.

Before writing any code, read these files and treat them as the source of truth:
- `CLAUDE.md` (root) — rules, stack, conventions, constraints
- `docs/PRD.md` — what to build and why, full field list, validation rules
- `docs/architecture.md` — technical design, DB schema, API endpoints, Docker setup

Then:
1. Summarize back to me, in 8–10 bullets, your understanding of the project, the stack, and the non-negotiable rules. Call out anything ambiguous or any assumption you'd have to make (especially Salesforce object/field names).
2. Propose a phased implementation plan with these milestones, each independently runnable and verifiable:
   - Phase 0 — Scaffold: repo structure, `docker-compose.yml`, backend `Dockerfile` (python:3.11-slim + WeasyPrint deps), `frontend/Dockerfile` + `nginx.conf`, `.env.example`, FastAPI app with `GET /api/health`, React+Vite skeleton, Postgres container, Alembic init.
   - Phase 1 — Salesforce: `simple-salesforce` client + `app/salesforce/mapping.py`, endpoints `GET /api/seasons`, `GET /api/products?season=`, `GET /api/accounts?email=|accountId=`.
   - Phase 2 — Frontend form: reproduce EVERY field/section from PRD §5 (matching the approved mockup), season selector loads products, buyer lookup auto-fills (dropdown on multiple matches), live line/grand totals.
   - Phase 3 — Submit: Pydantic schema, server-side order-minimum validation (18 total / 4 per style / 2 per SKU / no pre-packs), persist order + items to Postgres WITHOUT card number/CVV, Alembic migration.
   - Phase 4 — PDF + email: WeasyPrint (Jinja2 template mirroring the form, includes card details for manual processing), `fastapi-mail` to `ADMIN_EMAIL`, wire into `POST /api/orders`, buyer confirmation page.
   - Phase 5 — Hardening: nginx TLS + reverse proxy, rate limiting, CORS locked to origin, basic tests, README.

Do NOT start coding until I approve the plan.

Work one phase at a time. At the end of each phase: list what you built, how to run/verify it (exact commands), and wait for my confirmation before starting the next phase.

Hard rules you must never break:
- Never store or log the full credit card number or CVV. They may only exist transiently in memory to render the PDF, then be discarded. No card/CVV columns in the DB.
- The web form must contain every field from `docs/PRD.md` §5, including the Internal Use section (it IS shown on the form).
- All Salesforce calls happen on the backend only; credentials never reach the browser.
- Keep Salesforce object/field names in `app/salesforce/mapping.py` only. If you're unsure of a real field name, STOP and ask me — do not guess and scatter it through the code.
- Secrets only in `.env`; provide `.env.example`.

Start with step 1 (the summary) now.

---

## Follow-up prompt for each phase (reuse)

Phase N is approved. Implement it now following `CLAUDE.md` and `docs/architecture.md`.
When done: (a) show the file tree you added/changed, (b) give exact commands to build, run,
and verify this phase, (c) note any assumption you made. Then stop and wait for me.

---

## Tips
- If Claude Code drifts from the docs, reply: "Re-read CLAUDE.md and docs/architecture.md, then correct this to match."
- Give it the real Salesforce field names / SOQL as soon as you have them so it updates `mapping.py`.
- Ask it to write a test for the order-minimum validator early — that logic is the easiest to get subtly wrong.
- Keep each phase in its own commit/PR so you can review incrementally.
