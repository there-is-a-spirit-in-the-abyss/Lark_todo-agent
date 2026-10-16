# Team webpage deployment

This is a reusable setup guide. `team.example.com` and `<project-dir>` are
placeholders. This source copy does not establish any live deployment status.

## Prerequisites

Build `web/` with `npm --prefix web ci` and `npm --prefix web run build`. Configure
private `.env` credentials as described in README. Keep the existing database and
secrets on upgrades. Do not install sample identities, mock sessions or demo data
into a production database.

Configure a public HTTPS origin such as `https://team.example.com`. Register
`https://team.example.com/api/team/callback` in the Feishu app's security redirect
URLs. Enable and publish `im:chat.members:read` and `im:chat:read` (or equivalent
supported group-info permission). Every API read/write verifies the user's OAuth
open_id against the complete current group roster; verification failure denies
access.

## App configuration

Set `TEAM_WEB_ENABLED=true`, `TEAM_PUBLIC_URL=https://team.example.com` and
`TEAM_STATIC_DIR=/root/huiyang/web/dist` in the app environment. The last path is
inside the supplied image. For local non-container serving, use your absolute
`web/dist` path. Keep `PLATFORM_ENABLED=true` for the live bot. Set
`APP_LANGUAGE=zh-CN` or `en-US` for default bot replies.

Build and start with the supplied team override:

```sh
cd <project-dir>
npm --prefix web ci
npm --prefix web run build
docker compose --env-file .env -f docker-compose.yml -f deploy/team.compose.yml config --quiet
docker compose --env-file .env -f docker-compose.yml -f deploy/team.compose.yml up -d --build
```

Provide an HTTPS reverse proxy to `127.0.0.1:8000` for `/team/*` and `/api/team/*`.
`deploy/Caddyfile` and `deploy/preview.compose.yml` are optional project-local
examples. They expect a compatible Caddy binary at `.runtime/tools/caddy`, persistent
Caddy directories, and reachable certificate-validation ports. Set `TEAM_HOST` to
your domain/IP and `TEAM_UPSTREAM=127.0.0.1:8000` in private `deploy/team.env`.
The isolated preview uses port 8001 and disables the bot; configure it deliberately
before use. No TLS binary, certificate or global proxy setup is bundled.

## Language and routing

Mention the actual bot with `团队任务`, `团队todo`, `team tasks` or `team todo`.
Only these mentioned group requests return the group's `/team/CHAT_ID` link. They
do not invoke the model or initialize an administrator. Group replies use
`APP_LANGUAGE`; language commands in team-web groups are ignored. Private chat
retains personal tasks, with persisted `/language en-US` and `/language zh-CN`.
The webpage selector uses browser-local preference and Chinese by default.

Existing personal tasks/reminders and legacy team data are preserved. Team-web
mode suppresses old queued group replies, team reminders and weekly summaries;
private queries and memories exclude legacy team tasks. The additive migration
creates team tables without importing demo samples.

## Verification and rollback

Run the README local checks, then verify HTTPS without certificate bypass, OAuth
with real members, access revocation, ownership and personal/group chat in your
environment. Test outcomes and service health must be recorded for that deployment.
The retained automated fixtures do not prove real OAuth or delivery.

Keep a known-good app image/configuration and a database backup before rollout.
Rollback by restoring your own previous image/configuration. Do not drop team tables
or delete personal records; disabling team mode resumes legacy group behavior and
its configured reminders. A rollback is an operational action, not performed here.
