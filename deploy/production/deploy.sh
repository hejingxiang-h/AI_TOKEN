#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"

case "${1:-}" in
    check)
        dc config --quiet
        ;;
    prepare)
        # Match the public redirect and CORS origin to a plain hostname.
        dc config --format json | python3 -c '
import json, re, sys
from pathlib import Path
cfg=json.load(sys.stdin)
host=cfg["services"]["nginx"]["environment"]["APP_PUBLIC_HOST"]
tag=cfg["services"]["backend"]["image"].rsplit(":",1)[1]
if (not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",host)
        or host.endswith(".invalid") or tag=="replace-with-release-tag"):
    raise SystemExit("Set a deployment hostname and release tag first.")
root=Path(sys.argv[1]).resolve()
for name, item in cfg["secrets"].items():
    path=Path(item["file"]).resolve()
    if path.is_relative_to(root) or not path.is_file():
        raise SystemExit("Missing secret file or stored in the source tree: "+name)
    if name != "proxy_service_key" and path.stat().st_size == 0:
        raise SystemExit("Empty secret file: "+name)' "$ROOT"
        dc build backend nginx
        dc up -d --wait postgres redis
        ;;
    start-proxy)
        dc up -d --wait litellm
        ;;
    provision-key)
        umask 077
        destination="$(dc config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["secrets"]["proxy_service_key"]["file"])')"
        if [ -L "$destination" ] || [ -s "$destination" ]; then
            printf 'Service Key file already exists. Follow the rotation procedure.\n' >&2
            exit 1
        fi
        pending="$(mktemp "${destination}.XXXXXX")"
        trap 'rm -f -- "$pending"' EXIT HUP INT TERM
        dc exec -T litellm python /opt/prod/provision-key.py > "$pending"
        test "$(wc -l < "$pending" | tr -d ' ')" = 1
        LC_ALL=C grep -Eq '^sk-[A-Za-z0-9_-]{16,}$' "$pending"
        chmod 0444 "$pending"
        mv -f -- "$pending" "$destination"
        ;;
    migrate)
        dc --profile ops run --rm migrate
        dc --profile ops run --rm proxy-migrate
        ;;
    initialize-admin)
        dc --profile ops run --rm migrate python -m app.tasks.bootstrap_admin
        ;;
    start)
        dc --profile ops run --rm migrate alembic current --check-heads
        dc up -d --wait backend worker nginx
        ;;
    status)
        dc ps
        ;;
    *)
        printf 'Usage: %s {check|prepare|start-proxy|provision-key|migrate|initialize-admin|start|status}\n' "$0" >&2
        exit 2
        ;;
esac
