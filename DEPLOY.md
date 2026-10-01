# Deploying a new version (OVH VPS)

This is a runbook for shipping an update to the running NomiaMD deploy at
`https://nomiamd.com`. It assumes the server is already provisioned — DNS,
Docker, TLS (Caddy), and `.env` secrets are one-time setup done previously;
see git history for that initial-setup runbook if standing up a new server
from scratch.

Stack: `caddy` (TLS + reverse proxy, the only public ingress) → `frontend`
(nginx serving the built SPA, proxies `/api/*` to `backend`) → `backend`
(FastAPI/uvicorn) → `postgres` (users, physician profiles, patients, extraction
runs, claims, bills) + `redis` (rate-limit storage). The RAMQ LanceDB directory is a
read-only bind mount into `backend`, not a service.

## 1. Tag the release

Version tags follow [SemVer](https://semver.org): `vMAJOR.MINOR.PATCH` — bump
MAJOR for breaking changes, MINOR for backwards-compatible features, PATCH
for fixes only. Check the current latest tag first:

```bash
git tag -l --sort=-v:refname | head -1
```

Then tag and push the new release (replace `vX.Y.Z`):

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

## 2. Push the RAMQ LanceDB data (only if the corpus changed)

From `ramq-ingestion`, wherever it produced the new tables, using its
`scripts/deploy_db.sh`:

```bash
cd ~/Software/ramq-ingestion
scripts/deploy_db.sh --dry-run user@nomiamd-server   # preview the diff first
scripts/deploy_db.sh user@nomiamd-server              # ship it
```

Syncs the local LanceDB directory (`DB_PATH` from ramq-ingestion's `.env`, or
`LOCAL_DB`) — the versioned `codes_<rev>` tables plus the `code_versions`
registry for `billing_codes`, and `documents-embeddings` for `ramq_chatbot` — to
`/opt/nomiamd/data/<basename of that directory>/` on the server (`rsync
--delete`). The server's `RAMQ_LANCEDB_PATH` (in its `.env`) must point at that
subdirectory, not at `/opt/nomiamd/data/` itself; pass a different remote base
path as a second argument if it lives elsewhere.

The backend retrieves from whichever table `code_versions` marks `is_current`,
re-read on every lookup — a newly promoted revision is picked up within ~30 s
(`READ_CONSISTENCY_INTERVAL`) with no restart. Promote in ramq-ingestion
*before* syncing: if no row is current, the backend refuses to start
(`NoCurrentCodesTableError`). Skip this step entirely if only application code
changed, not the RAMQ data.

## 3. Deploy the new version to the server

```bash
ssh user@nomiamd.com
cd /opt/nomiamd/NomiaMD/
git fetch --tags
git checkout vX.Y.Z
docker compose up --build -d
docker compose ps        # postgres, redis, backend, frontend report healthy; caddy (no healthcheck) just "Up"
curl -I https://nomiamd.com/api/health
```

`/api/health` sits behind the nginx IP allowlist (`ALLOWED_CIDRS`), so the
`curl` gets a 403 from anywhere not on it — run it from an allowed address.

**Schema changes:** there are no migrations yet (no Alembic until the first
release). On startup the backend only runs `create_all`, which creates *missing*
tables and never alters an existing one. Before deploying, check whether the
ORM models changed since the running tag:

```bash
git diff vPREVIOUS vX.Y.Z -- backend/app/postgresdb/models.py
```

If an existing table changed, it has to be altered by hand in the `postgres`
container (or the `postgres_data` volume dropped, which **deletes all users,
patients, claims and bills**) before the new backend will work against it.

## 4. Create the physician account(s), if new ones are needed

There's no signup page — accounts are provisioned manually:

```bash
docker compose exec backend python scripts/create_user.py \
  --email you@example.com --full-name "Dr. You" --role physician \
  --practice-number 123456 --physician-type med_fam \
  --panel-size 800 --remuneration-type mixte
```

It prompts for a password interactively (never pass it as a CLI arg). The
practice facts are optional but matter for billing: `--practice-number` is what
patient registration is derived from (matched against a patient's family-doctor
practice number), and panel size filters panel-size-bounded code variants out
of retrieval (physician/remuneration type are recorded alongside). Physicians can also set them later from
the profile page. `--role admin` is needed to edit shared patient records.

To reset a forgotten password:

```bash
docker compose exec backend python scripts/reset_password.py --email you@example.com
```
