#!/bin/sh
set -eu
cd /root/huiyang
# .env values are passed as data by Docker Compose, never sourced as shell code.
docker info >/dev/null
docker compose config --quiet
docker compose up -d --build
docker compose ps
