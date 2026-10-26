#!/usr/bin/env bash
# Deploys a version to the prod or demo stack, from your machine, over SSH (DEPLOY.md):
#
#   deploy/deploy.sh prod v3.1.0         # a pushed release tag
#   deploy/deploy.sh demo [branch]       # a pushed branch, dev by default
#
# Options: --yes (no confirmation, except for a prod schema change), --dry-run (print the remote
# command instead of running it), --reset-data (demo only: drop its volumes and reseed),
# --running <sha> (the version the server runs, instead of asking it over SSH).
#
# The server is DEPLOY_SSH (user@host), from the environment or deploy/deploy.local.env
# (gitignored, copy deploy/deploy.local.env.example). PROD_DIR / DEMO_DIR override the
# checkouts' paths.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$REPO_ROOT"

stack=${1:-}
require_stack "$stack"
shift
ref=""
yes=false
dry_run=false
reset_data=false
running=""
while (($#)); do
    case $1 in
        --yes) yes=true; shift ;;
        --dry-run) dry_run=true; shift ;;
        --reset-data) reset_data=true; shift ;;
        --running) running=${2:?--running needs a sha}; shift 2 ;;
        -*) die "unknown option $1" ;;
        *) [[ -z $ref ]] || die "one version only"; ref=$1; shift ;;
    esac
done

# The environment wins over the local file.
deploy_ssh=${DEPLOY_SSH:-}
prod_dir=${PROD_DIR:-}
demo_dir=${DEMO_DIR:-}
if [[ -f deploy/deploy.local.env ]]; then
    source deploy/deploy.local.env
    deploy_ssh=${deploy_ssh:-${DEPLOY_SSH:-}}
    prod_dir=${prod_dir:-${PROD_DIR:-}}
    demo_dir=${demo_dir:-${DEMO_DIR:-}}
fi
[[ -n $deploy_ssh ]] || die "set DEPLOY_SSH=user@host in the environment, or: cp deploy/deploy.local.env.example deploy/deploy.local.env"
prod_dir=${prod_dir:-/opt/nomiamd/NomiaMD}
demo_dir=${demo_dir:-/opt/nomiamd/NomiaMD-demo}

info "Fetching origin"
git fetch --tags --quiet origin

if [[ $stack == prod ]]; then
    dir=$prod_dir
    [[ $reset_data == true ]] && die "--reset-data drops every volume: demo only"
    [[ $ref =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || die "prod deploys a release tag vX.Y.Z (latest: $(git tag -l --sort=-v:refname | head -1))"
    git ls-remote --exit-code --tags origin "refs/tags/$ref" >/dev/null || die "$ref isn't on origin. Tag and push it first:
  git tag -a $ref -m \"Release $ref\" && git push origin $ref"
    new_sha=$(git rev-parse "$ref^{commit}")
    checkout="git checkout --quiet $ref"
else
    dir=$demo_dir
    ref=${ref:-dev}
    [[ $ref =~ ^[A-Za-z0-9._/-]+$ ]] || die "invalid branch name $ref"
    new_sha=$(git rev-parse --verify --quiet "origin/$ref^{commit}") || die "origin/$ref doesn't exist (pushed?)"
    checkout="git checkout --quiet $ref && git merge --ff-only --quiet origin/$ref"
fi

if [[ -z $running ]]; then
    running=$(ssh "$deploy_ssh" "git -C '$dir' rev-parse HEAD") || die "couldn't read the running version from $deploy_ssh:$dir"
fi

info "$stack ($deploy_ssh:$dir): $(git describe --tags --always "$running" 2>/dev/null || echo "$running") → $ref ($(git rev-parse --short "$new_sha"))"
schema_changed=false
if ! git cat-file -e "$running^{commit}" 2>/dev/null; then
    warn "the running commit $running isn't in this clone: can't show what changed"
elif [[ $running == "$new_sha" ]]; then
    echo "Already running this commit: the stack is only rebuilt and restarted."
else
    git --no-pager log --oneline "$running..$new_sha"
    # The changes DEPLOY.md's step 3 asks to check by hand.
    if ! git diff --quiet "$running" "$new_sha" -- .env.example; then
        info ".env.example changed (the server's .env is checked against it before the deploy)"
        git --no-pager diff "$running" "$new_sha" -- .env.example
    fi
    if ! git diff --quiet "$running" "$new_sha" -- backend/app/postgresdb/models.py; then
        schema_changed=true
        info "The ORM models changed"
        git --no-pager diff --stat "$running" "$new_sha" -- backend/app/postgresdb/models.py
        warn "create_all never alters an existing table: an altered one must be migrated by hand (DEPLOY.md, \"Schema changes\")"
        [[ $stack == demo && $reset_data == false ]] && warn "on the demo, --reset-data drops and reseeds its data instead"
    fi
    if [[ $stack == prod ]] && ! git diff --quiet "$running" "$new_sha" -- edge/; then
        info "edge/ changed (caddy is recreated or reloaded during the deploy)"
        git --no-pager diff --stat "$running" "$new_sha" -- edge/
    fi
fi
[[ $reset_data == true ]] && warn "--reset-data: every demo user, patient, claim and bill is dropped, then reseeded"

remote="set -e; cd '$dir'; git fetch --tags --quiet origin; $checkout; exec deploy/remote-deploy.sh $stack --previous $running"
[[ $reset_data == true ]] && remote+=" --reset-data"

if [[ $dry_run == true ]]; then
    info "Dry run, would run on $deploy_ssh:"
    echo "$remote"
    exit 0
fi

# A prod schema change asks even with --yes: a missed migration breaks the live stack.
if [[ $stack == prod && $schema_changed == true ]]; then
    read -rp "The schema changed: is the database ready for it (DEPLOY.md, \"Schema changes\")? Type yes to deploy: " answer
    [[ $answer == yes ]] || die "aborted"
elif [[ $yes == false ]]; then
    read -rp "Deploy $ref to $stack? [y/N] " answer
    [[ $answer =~ ^[yY]$ ]] || die "aborted"
fi

ssh -t "$deploy_ssh" "$remote"
