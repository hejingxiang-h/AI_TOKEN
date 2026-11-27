#!/bin/sh
set -eu

load() {
    test -s "/run/secrets/$2" || { printf 'Missing or empty secret file: %s\n' "$2" >&2; exit 1; }
    export "$1=$(cat "/run/secrets/$2")"
}

load APP_DB_PASSWORD app_db_password
if [ -f /run/secrets/redis_password ]; then
    load REDIS_PASSWORD redis_password
fi
if [ "${1:-}" = uvicorn ]; then
    load APP_JWT_SECRET jwt_secret
    load APP_LITELLM_SERVICE_KEY proxy_service_key
    load APP_GATEWAY_CALLBACK_SECRET callback_secret
    test "${#APP_JWT_SECRET}" -ge 32
    test "${#APP_GATEWAY_CALLBACK_SECRET}" -ge 32
fi
exec "$@"
