# Deploying a new version (OVH VPS)

This is a runbook for shipping an update to the running NomiaMD deploy at
`https://nomiamd.com`. It assumes the server is already provisioned — DNS,
Docker, TLS (Caddy), and `.env` secrets are one-time setup done previously;
see git history for that initial-setup runbook if standing up a new server
from scratch.

Stack: `caddy` (TLS + reverse proxy, the only public ingress) → `frontend`
(nginx serving the built SPA, proxies `/api/*` to `backend`) → `backend`
(FastAPI/uvicorn) → `postgres` (users, extraction records) + `redis`
(rate-limit storage).

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

Syncs both LanceDB stores (`codes`/`code-embeddings` for `billing_codes`, and
`documents-embeddings` for `ramq_chatbot`) to `/opt/nomiamd/data/` on the
server by default — pass a different remote base path as a second argument
if the server's `RAMQ_LANCEDB_PATH`/`RAMQ_CHATBOT_LANCEDB_PATH` (in its
`.env`) point somewhere else. Skip this step entirely if only application
code changed, not the RAMQ data.

## 3. Deploy the new version to the server

```bash
ssh user@nomiamd.com
cd /opt/nomiamd/NomiaMD/
git fetch --tags
git checkout vX.Y.Z
docker compose up --build -d
docker compose ps        # all 5 services should report healthy
curl -I https://nomiamd.com/api/health
```

## 4. Create the physician account(s), if new ones are needed

There's no signup page — accounts are provisioned manually:

```bash
docker compose exec backend python scripts/create_user.py \
  --email you@example.com --full-name "Dr. You" --role physician
```

It prompts for a password interactively (never pass it as a CLI arg).
