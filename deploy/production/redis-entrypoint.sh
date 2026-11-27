#!/bin/sh
set -eu
REDIS_PASSWORD="$(cat /run/secrets/redis_password)"
export REDIS_PASSWORD
exec /bin/sh /opt/prod/redis-start.sh
