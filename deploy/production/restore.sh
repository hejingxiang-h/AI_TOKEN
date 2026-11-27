#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"

[ "$#" -eq 2 ] || { printf 'Usage: %s /backup/snapshot restore_label\n' "$0" >&2; exit 2; }
backup="$(realpath -e -- "$1")"
label="$2"
case "$label" in restore_*) ;; *) printf 'Use a new database prefix starting with restore_.\n' >&2; exit 2 ;; esac
case "$label" in *[!a-z0-9_]*) exit 2 ;; esac
test "${#label}" -le 45
(cd "$backup" && sha256sum business.dump proxy.dump | cmp - SHA256SUMS)

check_absent() {
    found="$(dc exec -T postgres psql --username=gateway_bootstrap --dbname=postgres -X -A -t \
        --command="SELECT 1 FROM pg_database WHERE datname = '$1'")"
    [ -z "$found" ] || { printf 'Database already exists: %s\n' "$1" >&2; exit 1; }
}
business="${label}_business"
proxy="${label}_proxy"
check_absent "$business"
check_absent "$proxy"

restore() {
    dc exec -T postgres createdb --username=gateway_bootstrap --owner="$2" "$1"
    dc exec -T postgres psql --username=gateway_bootstrap --dbname=postgres --set ON_ERROR_STOP=1 \
        --command="REVOKE CONNECT ON DATABASE $1 FROM PUBLIC"
    dc exec -T postgres pg_restore --username=gateway_bootstrap --dbname="$1" \
        --single-transaction --exit-on-error --no-owner --no-privileges --role="$2" < "$3"
}
restore "$business" gateway_app "$backup/business.dump"
restore "$proxy" gateway_proxy "$backup/proxy.dump"
printf 'Restored to %s and %s. Active databases were preserved.\n' "$business" "$proxy"
