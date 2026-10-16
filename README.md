# Huiyang

English | [简体中文](README.zh-CN.md)

## Windows installer

**[Download huiyang-setup.exe](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases/latest/download/huiyang-setup.exe)** · [All releases and checksums](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases)

Download and double-click the `.exe`, enter your SSH connection details, choose a
server directory, and deploy. Your computer does not need a separate Python,
Node.js, or SSH installation. The default server directory is `/Lark_todo-agent`.
Provide your own Feishu app and model settings, or import an existing `.env` file.
Downloads require an authorized GitHub account while this repository is private.

See the [installer guide (Simplified Chinese)](installer/README.md). After the
GitHub release workflow succeeds, the installer pulls a prebuilt app image.
Local installer builds include clean source that Docker builds on the server.

Huiyang is a Feishu Todo secretary bot with a shared project-tree webpage.
It turns explicit chat instructions into validated actions, stores tasks and
conversation references in PostgreSQL, and delivers replies and reminders through
Feishu. Simplified Chinese is the default; English is selectable.

Private chats manage personal tasks; groups collaborate through the shared
project-tree webpage. Task operations pass structured model-output validation,
permission checks, and durable transactions. Ordinary group messages do not
automatically create tasks.

## Languages

- Set `APP_LANGUAGE=zh-CN` (default) or `APP_LANGUAGE=en-US` in `.env`, then recreate
  the app container so it reloads configuration.
- In private chat send `/language en-US` or `/language zh-CN`. This stores a
  preference by the real Feishu user ID and applies to future private replies and
  reminders, including after restarts. An unsupported code returns command usage.
- In legacy group mode (`TEAM_WEB_ENABLED=false`), mention the actual bot and send
  the same command to change the language shared by that group. Without the bot
  mention it is not a language command.
- In team-web mode, group messages remain entry-link-only. Mention the bot with
  `team tasks` or `team todo`. Entry-link replies use
  `APP_LANGUAGE`; private language commands do not change group routing.
- The webpage language selector switches between Simplified Chinese and English.
  Chinese is the browser default. Selection persists in that browser's local
  storage, including on the login/error screen. It does not change chat preferences.
- Names, task/project titles, descriptions, IDs, stored status enum values and
  original instructions remain unchanged. Model-generated understanding and
  clarification fields receive explicit language instructions; external model
  compliance still needs live verification.

## Install and deploy

Windows users can use the [Chinese graphical installer](installer/README.md):
double-click `huiyang-setup.exe`, enter SSH connection information, browse or
create a server folder (default `/Lark_todo-agent`), import or enter Feishu/model settings,
then deploy. The executable bundles its client dependencies. GitHub Releases
use a prebuilt app image; local builds include a clean source fallback which
Docker builds automatically on the server. App credentials cannot be obtained
from a personal Feishu login; explicitly selected `.env` files can be imported.

For source development, the following commands require Python 3.11+ and Node/npm.
Docker builds now build the frontend internally; they do not need host Node/npm.
Run commands from your checkout; `<project-dir>` means where you unpacked it.

```powershell
cd <project-dir>
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[test]"
npm --prefix web ci
npm --prefix web run build
```

On Linux, use `.venv/bin/python` instead of the Windows Python path. Configure a
private `.env` using `.env.example`; generate a new random `POSTGRES_PASSWORD`.
Set your Feishu app credentials and HTTPS model endpoint/key/model there. Never
commit `.env`. See [Feishu setup](docs/MANUAL_SETUP.md) for app scopes and events.

```sh
docker compose config --quiet
docker compose up -d --build
```

Compose migrates the database and starts one worker plus a separate SDK receiver
process. `/root/huiyang` is the image's internal working directory; your host
checkout can use another location. Host API binding is `127.0.0.1:8000`.
`GET /health` checks the app; it does not prove Feishu subscriptions or model access.
Data stays in `postgres_data/`; do not delete this directory when upgrading.

For the group webpage, follow [team deployment](docs/TEAM_WEB_SETUP.md): configure
public HTTPS, Feishu OAuth callback, `TEAM_PUBLIC_URL`, and the explicit
`TEAM_WEB_ENABLED` flag. The webpage always uses real Feishu membership checks.
`demo/` is retained as the original reference and test fixture; it is separate
from the connected application in `web/` and has no live Feishu integration.

## Rules and boundaries

SDK events enter a durable inbox before acknowledgment. Validated model actions
run in a business transaction with pending replies; transport retries reuse the
committed result. Feishu IDs come from authenticated events/API responses, and
names never grant permissions. Do not add app replicas or Uvicorn workers without
redesigning inbox and scheduler coordination.

In legacy mode, the first target-group event binds the API-reported group owner
once as administrator. Private messages do not initialize this binding; do not
add the bot to unrelated groups before the intended group initializes it.
Ordinary members manage their assigned tasks. Personal task states cover
to do, in progress, blocked, completed, and canceled; overdue is derived.

Team-web mode has independent group-scoped boards, three task states, immutable
authors, subtree moves/deletion, shared staging, cycle rejection, derived project
completion and empty-project cleanup. Departed authors' tasks can be maintained
by current members. Existing personal and legacy team records are retained;
legacy team records/reminders/summaries are excluded from personal mode.
See [team rules](docs/team-web-integration.md).

`LLM_PROVIDER=openai_compatible` uses strict Chat Completions JSON Schema;
`LLM_PROVIDER=deepseek` uses Responses with adapter-owned wire normalization.
No model SDK or translation call is introduced into the business layer.

## Local verification

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
npm --prefix web run test:unit
npm --prefix web run build
npm --prefix web exec -- playwright install chromium
npm --prefix web test
```

For Linux source tests use `PYTHONPATH=src .venv/bin/python -m pytest`.

PostgreSQL integration tests are opt-in and require an isolated test database;
read their environment flags before running them. Browser tests intercept the
external API and use retained fixtures; they do not verify live OAuth or Feishu.
No production deployment or live service verification is claimed for this copy.
The pinned Feishu SDK may emit existing dependency deprecation warnings.
