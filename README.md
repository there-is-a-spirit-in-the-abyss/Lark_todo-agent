# Huiyang · Feishu Task Agent

English | [简体中文](README.zh-CN.md)

## Features

**Tell the bot your personal tasks. Build a shared task tree for team progress.**

- **Capture personal tasks in chat:** create, find and update todos through private Feishu conversations, with reminders.
- **Build team projects quickly:** members of the same organization open a shared webpage from their Feishu group and break projects into tasks and subtasks.
- **See progress clearly:** visualize task relationships and status in a tree, with project progress derived from tasks.
- **Organize work flexibly:** use multiple projects, shared staging and whole-branch moves to turn loose tasks into a structured plan.
- **Collaborate by group:** each group has its own board, with real Feishu membership checks and task permissions.

For example, manage a personal todo in private chat, then mention the bot with `team tasks` in a project group to build a tree such as “Product launch → Design / Development / Testing”.
Ordinary group messages do not automatically create tasks.

## Download

**[Download the Feishu Agent installer · huiyang-setup.exe](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases/latest/download/huiyang-setup.exe)**

[All releases and checksums](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases) · [GitHub repository](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent)

Double-click the download to open the deployment wizard. Your computer needs no separate Python, Node.js or SSH installation.
The repository is currently private; downloading requires an authorized GitHub account.

## Installation and deployment

### What you need

- A Linux server reachable over SSH, with its address, port, username and password or private key.
- A Feishu group for the same organization or team, and permission to create and configure an internal app.
- The app's App ID / App Secret, plus a model endpoint, API key and model name.
- A reachable HTTPS address for the team webpage, with the required cloud firewall ports open.

### Steps

1. Manually create an internal Feishu app, enable its bot, configure permissions and long-connection message events, publish it with the appropriate availability, and add the bot to the target group.
2. Open `huiyang-setup.exe`, enter SSH connection details, choose a server directory, and supply Feishu, model and webpage settings. You can import an existing `.env`.
3. Deploy. The installer checks the server, installs missing supported Docker/Compose components, and deploys the application and database.
4. Manually add the webpage's login callback URL ending in `/api/team/callback` to the Feishu app's security redirect settings.
5. Verify private todos, reminder delivery and the group's `team tasks` entry, then confirm that group members can sign in and collaborate.

**Bot creation, permission approval, event subscription, app publishing and callback configuration remain manual.** The wizard deploys the server application; it cannot obtain app credentials from a personal Feishu login.

[Installer guide](installer/README.md) · [Feishu and model setup](docs/MANUAL_SETUP.md) · [Team webpage deployment](docs/TEAM_WEB_SETUP.md)

<details>
<summary>Languages, source deployment, task rules and verification</summary>

### Languages

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

### Install and deploy

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

### Rules and boundaries

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

### Local verification

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

</details>
