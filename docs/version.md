# Version history

**The changelog lives in [`frontend/src/admin/version.md`](../frontend/src/admin/version.md).
Edit it there, not here.**

It moved because the admin page renders it: the "What's new" tab imports that
file, and the frontend Docker image is built with `build: ./frontend`, so its
build context contains `frontend/` and nothing else. A changelog in `docs/`
would work on a laptop and fail the image build.

Keeping this file as a pointer rather than a second copy is deliberate — two
copies of a changelog disagree within a release or two, and the one people read
is whichever the app happens to ship.

## Cutting a version

1. Add the entry to `frontend/src/admin/version.md`
2. Commit it, then tag: `git tag -a v1.1 main -m "Version 1.1 — <one line>"`
3. `git push origin v1.1`
4. `docker compose build frontend && docker compose up -d frontend`

Step 4 is not optional: the text is inlined into the bundle at build time, so
the tab keeps showing the old changelog until the image is rebuilt. That is
also a useful signal — if the tab looks stale, the deployed frontend is stale.
