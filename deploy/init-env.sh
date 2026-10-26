#!/usr/bin/env bash
# Writes a new stack's .env: the root .env.example with deploy/env/<stack>.env's values applied
# and fresh secrets generated, then lists what's still blank for you to fill. Run it once, on
# the server, from the stack's checkout:
#
#   deploy/init-env.sh prod
#   deploy/init-env.sh demo [--output path/.env] [--force]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

stack=${1:-}
require_stack "$stack"
shift
output=$REPO_ROOT/.env
force=false
while (($#)); do
    case $1 in
        --output) output=${2:?--output needs a path}; shift 2 ;;
        --force) force=true; shift ;;
        *) die "unknown option $1" ;;
    esac
done
[[ -e $output && $force == false ]] && die "$output already exists (--force overwrites it)"
command -v openssl >/dev/null || die "openssl is needed to generate the secrets"

# The lines to put in place, KEY=value each: the template's own lines, then the generated
# secrets. Hex only: POSTGRES_PASSWORD ends up inside docker-compose.yml's DATABASE_URL.
assignments=$(mktemp)
trap 'rm -f "$assignments"' EXIT
grep -E '^[A-Z_][A-Z0-9_]*=' "$REPO_ROOT/deploy/env/$stack.env" >"$assignments"
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >>"$assignments"
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" >>"$assignments"
[[ $stack == demo ]] && echo "SEED_ADMIN_PASSWORD=$(openssl rand -hex 12)" >>"$assignments"

# Each key replaces its line in .env.example: the uncommented one if there is one, else the
# first commented-out `#KEY=` (uncommenting it). Keys .env.example lacks go at the end. Later
# assignments win, so a generated secret overrides a blank template value.
umask 077
awk '
    function key_of(line) {
        if (match(line, /^[ \t]*#?[ \t]*[A-Z_][A-Z0-9_]*=/)) {
            k = substr(line, RSTART, RLENGTH - 1); gsub(/[ \t#]/, "", k); return k
        }
        return ""
    }
    FNR == 1 { file++ }
    file == 1 { k = key_of($0); line[k] = $0; if (!(k in seen)) { order[++n] = k; seen[k] } next }
    file == 2 { if ($0 !~ /^[ \t]*#/ && (k = key_of($0)) != "") active[k]; next }
    {
        k = key_of($0)
        if (k in line && !(k in done) && ($0 !~ /^[ \t]*#/ || !(k in active))) { print line[k]; done[k]; next }
        print
    }
    END {
        for (i = 1; i <= n; i++) if (!(order[i] in done)) { if (!header++) print "\n# deploy/env additions"; print line[order[i]] }
    }
' "$assignments" "$REPO_ROOT/.env.example" "$REPO_ROOT/.env.example" >"$output"
chmod 600 "$output"

info "Wrote $output ($stack)"
"$REPO_ROOT/deploy/check-env.sh" "$stack" "$output" || {
    echo "Fill in the values above, then re-run: deploy/check-env.sh $stack $output"
    exit 0
}
