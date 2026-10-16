#!/bin/sh
set -eu
cd /root/huiyang
test -f deploy/team.env || { echo 'Configure deploy/team.env first'; exit 1; }
# Trusted public HTTPS and the Feishu OAuth redirect must be verified first.
grep -qx 'TEAM_UPSTREAM=127.0.0.1:8000' deploy/team.env || {
    echo 'Set TEAM_UPSTREAM=127.0.0.1:8000 before integrated rollout'
    exit 1
}
npm --prefix web run build
docker compose --env-file .env --env-file deploy/team.env -f docker-compose.yml -f deploy/team.compose.yml config --quiet
docker compose --env-file .env --env-file deploy/team.env -f docker-compose.yml -f deploy/team.compose.yml up -d --no-deps --build app
docker compose --env-file .env --env-file deploy/team.env -p huiyang-team -f deploy/preview.compose.yml up -d team-proxy
