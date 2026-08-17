#!/bin/sh
# Generates the IP/CIDR allowlist nginx.conf includes, from a comma-separated ALLOWED_CIDRS
# env var — nginx itself can't read env vars, and the allowlist is a variable number of
# `allow` directives, not a single substitutable value. 127.0.0.1 is always allowed so the
# container's own HEALTHCHECK (run from inside the container) keeps working regardless of
# ALLOWED_CIDRS.
set -eu

{
    echo "allow 127.0.0.1;"
    IFS=,
    for cidr in ${ALLOWED_CIDRS:-}; do
        [ -n "$cidr" ] && echo "allow $cidr;"
    done
} > /etc/nginx/conf.d/allowed_ips.conf

exec nginx -g 'daemon off;'
