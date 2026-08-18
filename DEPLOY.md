# Deploying to production (OVH VPS)

This is a runbook for standing up a single-instance production deploy of
NomiaMD at `https://nomiamd.com`, using the `docker-compose.yml` at the repo
root. It assumes a low-traffic demo, not a scaled/HA deploy.

Stack: `caddy` (TLS + reverse proxy, the only public ingress) → `frontend`
(nginx serving the built SPA, proxies `/api/*` to `backend`) → `backend`
(FastAPI/uvicorn) → `postgres` (users, extraction records) + `redis`
(rate-limit storage).

## 1. DNS

At OVH's DNS zone for `nomiamd.com`, point both names at the VPS's public IP:

- `A nomiamd.com -> <VPS IP>`
- `A www.nomiamd.com -> <VPS IP>` (or a `CNAME www -> nomiamd.com`)

`www` will redirect to the bare domain (see `Caddyfile`). Give DNS a few
minutes to propagate before the next steps — Caddy needs it resolvable to
issue a Let's Encrypt cert.

## 2. VPS setup

Skip this section if Docker is already installed.

```bash
# Docker Engine + Compose plugin (see docs.docker.com/engine/install/ubuntu
# for the current official steps if this repo/apt-key path has moved on)
curl -fsSL https://get.docker.com | sh

# Firewall: only SSH + HTTP/HTTPS reach the box. Everything else
# (postgres, redis, backend) is internal-only in docker-compose.yml already.
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

## 3. Get the code onto the VPS

```bash
git clone <this repo's URL> nomiamd
cd nomiamd
```

## 4. Configure secrets

```bash
cp .env.example .env
```

Fill in `.env`:

- `POSTGRES_PASSWORD` — any strong random string.
- `JWT_SECRET_KEY` — generate with:
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
- `MISTRAL_API_KEY`, `MISTRAL_EMBEDDING_MODEL=mistral-embed` — real Mistral
  credentials; `/extract` and `/query` spend real money per call.
- `RAMQ_LANCEDB_PATH` — see step 5 below.
- `COOKIE_SECURE=true` — already the `.env.example` default; keep it, since
  Caddy terminates real TLS here.
- Leave `ALLOWED_CIDRS` unset — this deploy is open to the internet, gated
  by login only (chosen deliberately for a demo shown to people at arbitrary
  IPs; see the brute-force note below).

## 5. Get the RAMQ LanceDB data onto the VPS

There's no automated sync between `ramq-ingestion` and this repo/VPS today.
From wherever `ramq-ingestion` produces its output LanceDB directory:

```bash
rsync -av /path/to/ramq-ingestion/output/ your-vps:/opt/nomiamd-lancedb/
```

Then set `RAMQ_LANCEDB_PATH=/opt/nomiamd-lancedb` in the VPS's `.env`. The
backend reads this directory at import time — it won't even start if it's
missing or empty. Repeat this rsync whenever the RAMQ code corpus changes
upstream; nothing here does it automatically.

## 6. First boot

```bash
docker compose up --build -d
docker compose ps        # all 5 services should report healthy
curl -I https://nomiamd.com/api/health
```

First TLS issuance can take a few seconds while Caddy talks to Let's
Encrypt — if `curl` fails immediately after `up`, retry after ~10s and check
`docker compose logs caddy` if it keeps failing (usually a DNS propagation
or firewall issue, not a Caddy config issue).

## 7. Create the physician account(s) to demo with

There's no signup page — accounts are provisioned manually:

```bash
docker compose exec backend python scripts/create_user.py \
  --email you@example.com --full-name "Dr. You" --role physician
```

It prompts for a password interactively (never pass it as a CLI arg).

## Known, deliberately-accepted gaps for this demo

- **No backup of the `postgres_data` volume.** Fine for a short-lived demo
  seeded with synthetic data; take a manual `pg_dump` first if that stops
  being true.
- **No purge/retention policy on `extraction_records`** (stores each
  transcript + result). Acceptable for demoing with the synthetic notes in
  `consultations/`; revisit before this ever touches real patient data
  (Law 25).
- **Docker's default `json-file` log driver has no rotation.** Not a concern
  at demo traffic/duration; add `logging: driver: json-file, options:
  {max-size: 10m, max-file: "3"}` per service if this runs long enough to
  matter.
