#!/bin/sh
(
  set -eu
  export APP_DB_PASSWORD="$(cat /run/secrets/app_db_password)"
  export LITELLM_DB_PASSWORD="$(cat /run/secrets/proxy_db_password)"
  psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 <<'SQL'
\getenv app_user APP_DB_USER
\getenv app_database APP_DB_NAME
\getenv app_password APP_DB_PASSWORD
\getenv proxy_user LITELLM_DB_USER
\getenv proxy_database LITELLM_DB_NAME
\getenv proxy_password LITELLM_DB_PASSWORD
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'proxy_user', :'proxy_password') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'app_database', :'app_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'proxy_database', :'proxy_user') \gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'app_database') \gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'proxy_database') \gexec
SQL
)
