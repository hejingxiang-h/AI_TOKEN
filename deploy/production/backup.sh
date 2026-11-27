#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
umask 077

[ "$#" -eq 1 ] || { printf 'Usage: %s /backup/directory\n' "$0" >&2; exit 2; }
base="$(realpath -e -- "$1")"
case "$base/" in "$ROOT/"*) printf 'Use a backup directory outside the source tree.\n' >&2; exit 2 ;; esac
test -d "$base"
pending="$(mktemp -d "$base/.pending.XXXXXX")"
final="$base/gateway-$(date -u +%Y%m%dT%H%M%SZ)-${pending##*.}"
trap 'rm -f -- "$pending/business.dump" "$pending/proxy.dump" "$pending/SHA256SUMS"; rmdir -- "$pending" 2>/dev/null || true' EXIT HUP INT TERM

dump() {
    dc exec -T postgres pg_dump --username=gateway_bootstrap --format=custom \
        --no-owner --no-acl --dbname="$1" > "$2"
    test -s "$2"
}
dump ai_token_gateway "$pending/business.dump"
dump ai_token_proxy "$pending/proxy.dump"
(cd "$pending" && sha256sum business.dump proxy.dump > SHA256SUMS)
mv -- "$pending" "$final"
printf '%s\n' "$final"
