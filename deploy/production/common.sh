#!/bin/sh
# Sourced by production operator scripts.
ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)"
ENV_FILE=${PROD_ENV_FILE:-"$ROOT/.env.production"}
case "$ENV_FILE" in /*) ;; *) ENV_FILE="$ROOT/$ENV_FILE" ;; esac

dc() {
    docker compose --project-directory "$ROOT" --env-file "$ENV_FILE" \
        --file "$ROOT/compose.production.yaml" "$@"
}
