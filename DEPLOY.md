# Deploying a new version (OVH VPS)

This is a runbook for shipping an update to the running NomiaMD deploy at
`https://nomiamd.com`. It assumes the server is already provisioned — DNS,
Docker, TLS (Caddy), and `.env` secrets are one-time setup done previously;
see git history for that initial-setup runbook if standing up a new server
from scratch.

Stack: `caddy` (TLS + reverse proxy, the only public ingress) → `frontend`
(nginx serving the built SPA, proxies `/api/*` to `backend`) → `backend`
(FastAPI/uvicorn) → `postgres` (users, physician profiles, patients, extraction
runs, claims, bills) + `redis` (rate-limit storage, extraction queue for `worker`).
The RAMQ LanceDB directory is a read-only bind mount into `backend`, not a service.

The host runs three independent compose projects:

| Project | Checkout | Runs | Domain |
|---|---|---|---|
| `nomiamd-edge` | prod's (`edge/docker-compose.yml`) | `caddy`, on 80/443 | both below |
| `nomiamd` | `/opt/nomiamd/NomiaMD/`, a release tag | the app stack | `nomiamd.com` |
| `nomiamd-demo` | `/opt/nomiamd/NomiaMD-demo/`, a branch (e.g. `dev`) | the app stack + `docker-compose.demo.yml` (Epic sandbox) | `demo.nomiamd.com` |

Each app stack has its own `.env`, Postgres volume and private network, so deploying
one never restarts the other. `caddy` reaches each stack's `frontend` over the shared
`nomiamd-edge` network (`EDGE_ALIAS`). The demo holds synthetic and Epic-sandbox data
only: `APP_ENV=development` there is what lets the sandbox run, and prod is pinned to
`production`, which refuses it.

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
--delete`). The server's `DB_PATH` (in its `.env`) must point at that
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
docker compose ps        # postgres, redis, backend, frontend report healthy; worker (no healthcheck) just "Up"
curl -I https://nomiamd.com/api/health
```

`/api/health` sits behind the nginx IP allowlist (`ALLOWED_CIDRS`), so the
`curl` gets a 403 from anywhere not on it — run it from an allowed address.

**Env changes:** the server's `.env` follows the root `.env.example` (compose hands all of
it to `backend` and `worker`). Before deploying, check whether it changed since the running
tag and update the server's `.env` to match:

```bash
git diff vPREVIOUS vX.Y.Z -- .env.example
```

Renamed so far: `RAMQ_LANCEDB_PATH` → `DB_PATH` (compose refuses to start until it's set),
and the vendor-named Mistral settings → per-role ones: `MISTRAL_API_KEY` → `LLM_API_KEY`
**and** `EMBEDDING_API_KEY` (the same key in both while Mistral serves both),
`MISTRAL_EMBEDDING_MODEL` → `EMBEDDING_MODEL`.

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

**Edge changes:** if `edge/` changed since the running tag (`git diff vPREVIOUS vX.Y.Z
-- edge/`), apply it from the prod checkout after the checkout above:

```bash
docker compose -f edge/docker-compose.yml up -d                                   # compose file changed
docker compose -f edge/docker-compose.yml exec caddy caddy reload --config /etc/caddy/Caddyfile   # Caddyfile only
```

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

## Demo stack (`demo.nomiamd.com`)

Same steps as prod, from `/opt/nomiamd/NomiaMD-demo/`, on a branch instead of a tag. It
shares the RAMQ LanceDB directory with prod (same `DB_PATH`, mounted read-only).

### Deploy a new version

```bash
cd /opt/nomiamd/NomiaMD-demo/
git fetch && git checkout dev && git pull
docker compose up --build -d
docker compose ps
```

The checklist under step 3 (env, schema) applies here too. The demo's data is
disposable: on a schema change, `docker compose down -v` (drops this stack's volumes
only, never prod's) then re-seed.

### One-time setup

1. DNS: an A record for `demo.nomiamd.com` pointing at this host. `caddy` gets its
   certificate on the first request once the record resolves.
2. Checkout and `.env`:
   ```bash
   git clone <repo> /opt/nomiamd/NomiaMD-demo && cd /opt/nomiamd/NomiaMD-demo
   git checkout dev
   cp .env.example .env
   ```
   Fill it in like prod's (its own `POSTGRES_PASSWORD` and `JWT_SECRET_KEY`), plus:
   ```bash
   COMPOSE_PROJECT_NAME=nomiamd-demo
   COMPOSE_FILE=docker-compose.yml:docker-compose.demo.yml
   NETWORK_PREFIX=172.28.1
   EDGE_ALIAS=demo-frontend
   EPIC_SANDBOX_ENABLED=true
   EPIC_SANDBOX_CLIENT_ID=<the fhir.epic.com app's non-production client id>
   EPIC_SANDBOX_PRIVATE_KEY_PATH=/opt/nomiamd/secrets/epic-sandbox.pem
   ```
3. The Epic private key, readable by the containers' user (uid 10001). Its public half
   must already be served by prod at `https://nomiamd.com/.well-known/jwks.json`:
   ```bash
   scp ~/.config/nomiamd/epic-sandbox/privatekey.pem user@nomiamd.com:/opt/nomiamd/secrets/epic-sandbox.pem
   sudo chown 10001 /opt/nomiamd/secrets/epic-sandbox.pem && sudo chmod 400 /opt/nomiamd/secrets/epic-sandbox.pem
   ```
4. Start and seed it (the demo physician, the simulated patients and the Epic sandbox
   patients):
   ```bash
   docker compose up --build -d
   docker compose exec backend python scripts/seed_db.py
   ```

## One-time migration: Caddy out of the prod stack

Before the edge project existed, `caddy` was a service of the prod stack. The first
deploy of a tag that has `edge/` moves it out, with a minute or two of downtime:

```bash
cd /opt/nomiamd/NomiaMD/
git fetch --tags && git checkout vX.Y.Z
# .env: RAMQ_LANCEDB_PATH → DB_PATH (see "Env changes" in step 3)
docker rm -f caddy                                  # frees 80/443
docker compose -f edge/docker-compose.yml up -d     # new caddy + the nomiamd-edge network
docker compose up --build -d --remove-orphans       # prod rejoins via the edge network
# ufw: let public traffic through to the new caddy (see below)
sudo ufw route allow proto tcp from any to 172.30.0.11 port 80
sudo ufw route allow proto tcp from any to 172.30.0.11 port 443
sudo ufw route allow proto udp from any to 172.30.0.11 port 443   # HTTP/3
```

**Firewall:** ufw only lets traffic through to a container that a `ufw route allow` rule
names by IP, and the old rules (added with `ufw-docker allow caddy …`) point at the old
`caddy` container's address. Until the new caddy's static address (`172.30.0.11`,
`edge/docker-compose.yml`) is allowed, every request — Let's Encrypt's HTTP challenge
included — times out (`Timeout during connect (likely firewall problem)` in `docker
compose -f edge/docker-compose.yml logs caddy`). Then delete the stale rules for the old
address (`sudo ufw status numbered`, `sudo ufw delete <n>`). If you change the edge
subnet or caddy's address, update these rules too.

Every prod container is recreated (they lose their fixed `container_name`s); data lives
in the `nomiamd_postgres_data` volume and is kept. The new `caddy` has its own
certificate volume and fetches fresh certificates on start. Once it's healthy, the old
`nomiamd_caddy_data` and `nomiamd_caddy_config` volumes can be removed.
