#!/usr/bin/env bash
# The server half of deploy/deploy.sh, run from the stack's checkout right after it moved to
# the new version, so these steps are always the release's own. By hand, after checking out
# the version yourself:
#
#   deploy/remote-deploy.sh prod --previous <sha that was running>
#   deploy/remote-deploy.sh demo --previous <sha> --reset-data   # drop and reseed the demo's data
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$REPO_ROOT"

stack=${1:-}
require_stack "$stack"
shift
previous=""
reset_data=false
while (($#)); do
    case $1 in
        --previous) previous=${2:?--previous needs a sha}; shift 2 ;;
        --reset-data) reset_data=true; shift ;;
        *) die "unknown option $1" ;;
    esac
done
[[ $reset_data == true && $stack == prod ]] && die "--reset-data drops every volume: demo only"

# Up to ~3 min for a stack to report healthy: the backend opens LanceDB and checks the
# embedding model before /health answers.
HEALTH_TIMEOUT=180

info "Checking .env"
deploy/check-env.sh "$stack"

docker network inspect nomiamd-edge >/dev/null 2>&1 \
    || die "the nomiamd-edge network is missing: start the edge first (docker compose -f edge/docker-compose.yml up -d, from the prod checkout)"

# The edge Caddy runs from the prod checkout only (DEPLOY.md, "Edge changes").
edge_changed() { [[ -n $previous ]] && ! git diff --quiet "$previous" HEAD -- "$@"; }
if [[ $stack == prod ]]; then
    if edge_changed edge/docker-compose.yml; then
        info "edge/docker-compose.yml changed: recreating caddy"
        docker compose -f edge/docker-compose.yml up -d
    elif edge_changed edge/Caddyfile; then
        info "edge/Caddyfile changed: reloading caddy"
        docker compose -f edge/docker-compose.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile
    fi
fi

if [[ $reset_data == true ]]; then
    info "Dropping the demo stack and its volumes"
    docker compose down -v
fi

version=$(git describe --tags --always)
info "Building and starting $version"
APP_VERSION=$version docker compose up --build -d --remove-orphans

info "Waiting for backend and frontend to report healthy"
health() { docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q "$1")" 2>/dev/null || echo missing; }
deadline=$((SECONDS + HEALTH_TIMEOUT))
until [[ $(health backend) == healthy && $(health frontend) == healthy ]]; do
    if ((SECONDS > deadline)); then
        docker compose ps
        docker compose logs --tail 50 backend worker
        die "not healthy after ${HEALTH_TIMEOUT}s (backend: $(health backend), frontend: $(health frontend))"
    fi
    sleep 5
done

# Through nginx, from inside its container: 127.0.0.1 is always on the ALLOWED_CIDRS allowlist.
docker compose exec -T frontend wget -qO- http://127.0.0.1/api/health >/dev/null \
    || die "/api/health failed through nginx"

if [[ $reset_data == true ]]; then
    info "Seeding the demo data"
    docker compose exec backend python scripts/seed_db.py
fi

docker compose ps
info "Deployed $version ($stack)"
