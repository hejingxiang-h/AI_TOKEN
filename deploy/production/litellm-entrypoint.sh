#!/bin/sh
set -eu

load() {
    test -s "/run/secrets/$2" || { printf 'Missing or empty secret file: %s\n' "$2" >&2; exit 1; }
    export "$1=$(cat "/run/secrets/$2")"
}

DATABASE_URL="$(python -c 'from pathlib import Path; from urllib.parse import quote; password=Path("/run/secrets/proxy_db_password").read_text().rstrip("\r\n"); assert password; print("postgresql://gateway_proxy:"+quote(password,safe="")+"@postgres:5432/ai_token_proxy")')"
export DATABASE_URL
if [ "${1:-}" = migrate ]; then
    exec litellm --skip_server_startup
fi

load LITELLM_MASTER_KEY proxy_master_key
load LITELLM_SALT_KEY proxy_salt_key
load APP_GATEWAY_CALLBACK_SECRET callback_secret
load DEEPSEEK_API_KEY deepseek_api_key
test "${#APP_GATEWAY_CALLBACK_SECRET}" -ge 32
cd /opt/prod
exec litellm --config /opt/prod/litellm.yaml --host 0.0.0.0 --port 4000
