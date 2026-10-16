# Huiyang · 汇漾

## Windows 安装包下载

**[下载 huiyang-setup.exe](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases/latest/download/huiyang-setup.exe)** · [全部版本与校验文件](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases)

下载后双击 `.exe`，填写 SSH 登录信息、选择服务器目录，再点击部署。电脑无需另外安装 Python、Node.js 或 SSH。默认目录 `/Lark_todo-agent`；需要自己的飞书应用与模型配置，可导入已有 `.env`。

[安装器使用说明](installer/README.md)。GitHub 自动构建通过后，发布页提供直接拉取预构建镜像的安装器；本地构建的安装器包含干净源码，服务器 Docker 会自动完成构建。

Huiyang is a Feishu Todo secretary bot with a shared project-tree webpage.
It turns explicit chat instructions into validated actions, stores tasks and
conversation references in PostgreSQL, and delivers replies and reminders through
Feishu. Simplified Chinese is the default; English is selectable.

汇漾是飞书 Todo 秘书：私聊维护个人任务，群内通过网页协作项目树。任务操作经过结构化
模型输出校验、业务权限检查和持久化事务；普通群聊不会自动变成任务。

## Languages / 语言

- Set `APP_LANGUAGE=zh-CN` (default) or `APP_LANGUAGE=en-US` in `.env`, then recreate
  the app container so it reloads configuration.
- In private chat send `/language en-US` or `/language zh-CN`. This stores a
  preference by the real Feishu user ID and applies to future private replies and
  reminders, including after restarts. An unsupported code returns command usage.
- In legacy group mode (`TEAM_WEB_ENABLED=false`), mention the actual bot and send
  the same command to change the language shared by that group. Without the bot
  mention it is not a language command.
- In team-web mode, group messages remain entry-link-only. Mention the bot with
  `团队任务`, `团队todo`, `team tasks` or `team todo`. Entry-link replies use
  `APP_LANGUAGE`; private language commands do not change group routing.
- The webpage selector **Language / 语言** switches between 简体中文 and English.
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
Ordinary members manage their assigned tasks. Canonical personal statuses remain
待办、进行中、阻塞、已完成、已取消; overdue is derived.

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
