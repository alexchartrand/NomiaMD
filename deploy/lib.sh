# Helpers shared by the deploy/ scripts (sourced, not run). Plain bash + awk: the server needs
# nothing beyond git, docker and openssl.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
info() { printf '\033[1m==> %s\033[0m\n' "$*"; }

# The stack name (prod|demo) or die.
require_stack() {
    case "${1:-}" in
        prod | demo) ;;
        *) die "stack must be prod or demo, got '${1:-}'" ;;
    esac
}

# Keys assigned in an env file, one per line, sorted. `active` lists uncommented assignments
# only; `all` also lists commented-out ones (`#KEY=...`, the optional settings in .env.example).
env_keys() {
    local file=$1 mode=${2:-active}
    awk -v mode="$mode" '
        mode == "active" && match($0, /^[ \t]*[A-Z_][A-Z0-9_]*=/) { print substr($0, RSTART, RLENGTH - 1) }
        mode == "all" && match($0, /^[ \t]*#?[ \t]*[A-Z_][A-Z0-9_]*=/) { print substr($0, RSTART, RLENGTH - 1) }
    ' "$file" | tr -d ' \t#' | sort -u
}

# The value of KEY's last uncommented assignment in an env file, surrounding quotes stripped;
# empty when unset.
env_value() {
    local file=$1 key=$2
    awk -v key="$key" '
        index($0, key "=") == 1 { value = substr($0, length(key) + 2) }
        END {
            if (value ~ /^".*"$/ || value ~ /^\047.*\047$/) value = substr(value, 2, length(value) - 2)
            print value
        }
    ' "$file"
}
