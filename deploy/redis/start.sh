#!/bin/sh
set -eu

: "${REDIS_PASSWORD:?A Redis password is required}"
acl_file=$(mktemp /tmp/gateway-redis.XXXXXX)
hash=$(printf '%s' "$REDIS_PASSWORD" | sha256sum)
printf 'user default on #%s ~* &* +@all -@dangerous\n' "${hash%% *}" > "$acl_file"
chmod 644 "$acl_file"
exec docker-entrypoint.sh redis-server --aclfile "$acl_file" --appendonly yes
