#!/usr/bin/env bash
# Checks a stack's .env against this checkout's .env.example and deploy/env/<stack>.env before
# a deploy: renamed or missing keys, empty required values, a .env that belongs to the other
# stack. remote-deploy.sh runs it first; run it by hand after editing a server's .env:
#
#   deploy/check-env.sh prod            # checks ./.env
#   deploy/check-env.sh demo path/.env
#
# Exits 1 on any error; warnings alone pass.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

stack=${1:-}
require_stack "$stack"
env_file=${2:-$REPO_ROOT/.env}
example=$REPO_ROOT/.env.example
overlay=$REPO_ROOT/deploy/env/$stack.env
[[ -f $env_file ]] || die "$env_file not found (deploy/init-env.sh $stack writes one)"

# Keys the compose files pin inside the containers, whatever the .env says: missing ones are
# harmless (most are .env.example's local-dev section).
COMPOSE_PINNED="DATABASE_URL REDIS_URL COOKIE_SECURE APP_ENV SAMPLE_PATIENTS_DIR FORWARDED_ALLOW_IPS"

errors=0
error() { printf '\033[31m  ✗ %s\033[0m\n' "$*"; errors=$((errors + 1)); }
value() { env_value "$env_file" "$1"; }
require_value() { [[ -n $(value "$1") ]] || error "$1 is empty${2:+ ($2)}"; }

active=$(env_keys "$env_file" active)
has_key() { grep -qx "$1" <<<"$active"; }

echo "Checking $env_file ($stack)"

# A key .env.example sets, or this stack's template lists, that the .env lacks: usually a
# rename since the .env was written (RAMQ_LANCEDB_PATH → DB_PATH, MISTRAL_API_KEY → ...).
expected=$( (env_keys "$example" active; env_keys "$overlay" active) | sort -u)
for key in $expected; do
    [[ " $COMPOSE_PINNED " == *" $key "* ]] && continue
    has_key "$key" || error "$key is missing (in .env.example or deploy/env/$stack.env)"
done

require_value JWT_SECRET_KEY
require_value POSTGRES_PASSWORD
require_value DB_PATH "the RAMQ LanceDB directory"
[[ $(value LLM_PROVIDER) == bedrock ]] || require_value LLM_API_KEY
case $(value EMBEDDING_PROVIDER) in
    bedrock | openai_compatible) ;;
    *) require_value EMBEDDING_API_KEY ;;
esac

# The two stacks share a host: a .env copied from the other one would collide on its network
# and edge alias, or run prod's data next to the Epic sandbox.
compose_file=$(value COMPOSE_FILE)
if [[ $stack == demo ]]; then
    [[ $(value COMPOSE_PROJECT_NAME) == nomiamd-demo ]] || error "COMPOSE_PROJECT_NAME must be nomiamd-demo"
    [[ $compose_file == *docker-compose.demo.yml* ]] || error "COMPOSE_FILE must include docker-compose.demo.yml"
    [[ $(value EDGE_ALIAS) == demo-frontend ]] || error "EDGE_ALIAS must be demo-frontend"
    [[ $(value NETWORK_PREFIX) =~ ^(|172\.28\.0)$ ]] && error "NETWORK_PREFIX must differ from prod's 172.28.0"
    require_value EPIC_SANDBOX_CLIENT_ID
    key_path=$(value EPIC_SANDBOX_PRIVATE_KEY_PATH)
    if [[ -z $key_path ]]; then
        error "EPIC_SANDBOX_PRIVATE_KEY_PATH is empty"
    elif [[ ! -f $key_path ]]; then
        error "EPIC_SANDBOX_PRIVATE_KEY_PATH: $key_path does not exist"
    fi
else
    [[ $(value COMPOSE_PROJECT_NAME) =~ ^(|nomiamd)$ ]] || error "COMPOSE_PROJECT_NAME must be unset or nomiamd on prod"
    [[ $compose_file == *docker-compose.demo.yml* ]] && error "COMPOSE_FILE must not include docker-compose.demo.yml on prod"
    [[ $(value EDGE_ALIAS) =~ ^(|prod-frontend)$ ]] || error "EDGE_ALIAS must be unset or prod-frontend on prod"
    [[ $(value NETWORK_PREFIX) =~ ^(|172\.28\.0)$ ]] || error "NETWORK_PREFIX must be unset or 172.28.0 on prod"
    [[ $(value EPIC_SANDBOX_ENABLED) == true ]] && error "EPIC_SANDBOX_ENABLED must not be true on prod"
fi

# A key .env.example doesn't mention at all, even commented out: stale, or renamed away.
known=$( (env_keys "$example" all; env_keys "$overlay" all) | sort -u)
for key in $active; do
    grep -qx "$key" <<<"$known" || warn "$key is not in .env.example (renamed or removed?)"
done
[[ -n $(value ALLOWED_CIDRS) ]] || warn "ALLOWED_CIDRS is empty: nobody can reach the app"

if ((errors > 0)); then
    printf '\033[31m%d error(s) in %s\033[0m\n' "$errors" "$env_file"
    exit 1
fi
echo "  ✓ $env_file is complete"
