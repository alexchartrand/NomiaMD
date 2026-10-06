#!/bin/sh
# Generates the IP/CIDR allowlist nginx.conf includes in its restricted locations, from a
# comma-separated ALLOWED_CIDRS env var — nginx itself can't read env vars, and the
# allowlist is a variable number of `allow` directives, not a single substitutable value.
# 127.0.0.1 is always allowed so checks run from inside the container (e.g.
# `wget localhost/api/health`) keep working regardless of ALLOWED_CIDRS.
#
# Written outside conf.d on purpose: nginx's main config includes conf.d/*.conf at the http
# level, where this file's `deny all` would be inherited by the public locations too.
set -eu

{
    echo "allow 127.0.0.1;"
    IFS=,
    for cidr in ${ALLOWED_CIDRS:-}; do
        [ -n "$cidr" ] && echo "allow $cidr;"
    done
    echo "deny all;"
} > /etc/nginx/allowlist.conf

exec nginx -g 'daemon off;'
