# 汇漾

[English](README.md) | 简体中文

## 下载 Windows 安装包

**[下载 huiyang-setup.exe](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases/latest/download/huiyang-setup.exe)** · [全部版本与校验文件](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases)

下载后双击 `.exe`，填写 SSH 登录信息，选择服务器目录，再点击部署。
电脑无需另外安装 Python、Node.js 或 SSH。默认服务器目录为 `/Lark_todo-agent`。
需要填写自己的飞书应用和模型配置，也可以导入已有的 `.env` 文件。
仓库保持私有期间，下载安装包需要登录有访问权限的 GitHub 账号。

详见[安装器使用说明](installer/README.md)。GitHub 发布工作流通过后，安装器会直接
拉取预构建的应用镜像；本地构建的安装器包含干净源码，由服务器上的 Docker 自动构建。

## 项目介绍

汇漾是飞书任务秘书，支持通过私聊管理个人任务，以及在群内通过网页协作项目树。
它将明确的聊天指令转换为经过校验的任务操作，使用 PostgreSQL 保存任务和会话引用，
通过飞书发送回复和提醒。任务操作经过结构化模型输出校验、权限检查和持久化事务；
普通群聊不会自动变成任务。

应用默认使用简体中文，也可以选择英文。

## 语言设置

- 在 `.env` 中设置 `APP_LANGUAGE=zh-CN`（默认）或 `APP_LANGUAGE=en-US`，
  然后重新创建应用容器，使配置生效。
- 在私聊中发送 `/language zh-CN` 或 `/language en-US`，按真实飞书用户标识保存
  语言偏好。此设置会影响后续私聊回复和提醒，重启后仍保留。不支持的语言会返回用法提示。
- 在旧版群任务模式（`TEAM_WEB_ENABLED=false`）中，需要先提及机器人，再发送上述命令，
  才会切换该群共享的语言偏好。
- 在团队网页模式中，群消息只提供网页入口。提及机器人并发送“团队任务”或“团队todo”
  即可获取链接，也支持对应的英文指令。入口回复使用 `APP_LANGUAGE`；
  私聊语言命令不改变群内路由行为。
- 网页的语言选择器支持简体中文和英文，浏览器默认使用简体中文。选择会保存在当前浏览器，
  登录页和错误页也会生效，不改变聊天偏好。
- 用户姓名、项目与任务标题、描述、标识、已有状态值和原始指令均保持原样。
  模型生成的理解与澄清会收到明确的语言要求，但外部模型是否遵从仍需实际验证。

## 安装与部署

Windows 用户可以使用[中文图形安装器](installer/README.md)：双击 `huiyang-setup.exe`，
填写 SSH 连接信息，浏览或新建服务器目录，导入或填写飞书和模型配置，再点击部署。
安装器已打包客户端依赖。正式发布版使用预构建应用镜像；本地构建版包含源码备用包，
由服务器 Docker 自动构建。飞书应用凭据不能从个人飞书登录账号中自动获取，
但可以从明确选择的 `.env` 文件导入。

从源码开发时，需要 Python 3.11 及以上版本，以及 Node.js 和 npm。
Docker 构建会在容器内构建前端，无需在服务器系统中单独安装 Node.js 或 npm。
以下命令均在项目根目录执行，`<project-dir>` 表示项目解压目录。

```powershell
cd <project-dir>
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[test]"
npm --prefix web ci
npm --prefix web run build
```

Linux 环境将 Windows 的 Python 路径替换为 `.venv/bin/python`。
参照 `.env.example` 创建私有的 `.env`，为 `POSTGRES_PASSWORD` 生成新的随机密码，
并填写飞书应用凭据及模型的 HTTPS 接口地址、密钥和模型名称。不要提交真实 `.env`。
飞书应用权限和事件配置详见[飞书配置指南](docs/MANUAL_SETUP.md)。

```sh
docker compose config --quiet
docker compose up -d --build
```

Compose 会执行数据库迁移，启动一个任务处理进程和独立的飞书事件接收进程。
`/root/huiyang` 是镜像内部工作目录，服务器上的项目目录可以使用其他位置。
接口仅绑定 `127.0.0.1:8000`。`GET /health` 用于检查应用响应，不能证明飞书订阅
或模型调用已经可用。数据保存在 `postgres_data/`，升级时不要删除该目录。

群内网页部署参照[团队网页部署指南](docs/TEAM_WEB_SETUP.md)，配置公网 HTTPS、
飞书登录回调、`TEAM_PUBLIC_URL` 和 `TEAM_WEB_ENABLED`。
网页始终通过飞书接口检查真实群成员身份。
`demo/` 保留原始参考页面和测试数据，与 `web/` 中的实际应用分离，不连接真实飞书。

## 任务规则与边界

飞书事件在确认接收前写入持久化收件箱。通过校验的模型操作与待发送回复一起提交事务，
传输重试复用已提交的结果。飞书身份来自已验证的事件或接口响应，姓名不用于授权。
收件箱和定时任务协调机制重新设计前，不应增加应用副本或 Uvicorn 工作进程。

旧版群任务模式中，目标群的首个事件会将飞书接口报告的群主绑定为管理员，仅绑定一次。
私聊不会初始化此绑定，因此不要在目标群完成初始化前，将机器人添加到无关群中。
普通成员管理分配给自己的任务。个人任务状态包括待办、进行中、阻塞、已完成和已取消；
逾期状态根据时间计算。

团队网页模式中，各群拥有独立任务板，支持三种任务状态、不可变的作者身份、
整条任务分支移动与删除、共享暂存区、循环关系检查、项目进度计算和空项目清理。
作者退群后，其任务可由当前成员维护。已有个人和旧版群任务记录会保留；
旧版群任务记录、提醒和汇总不会进入个人任务模式。
详见[团队任务规则](docs/team-web-integration.md)。

`LLM_PROVIDER=openai_compatible` 使用严格的聊天补全结构化输出；
`LLM_PROVIDER=deepseek` 使用响应接口，由适配器负责协议转换。
业务层不引入模型专用客户端库或额外翻译调用。

## 本地验证

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
npm --prefix web run test:unit
npm --prefix web run build
npm --prefix web exec -- playwright install chromium
npm --prefix web test
```

Linux 环境使用 `PYTHONPATH=src .venv/bin/python -m pytest` 执行源码测试。

PostgreSQL 集成测试需要主动启用，并使用独立测试数据库；运行前请阅读测试中的环境开关。
浏览器测试使用接口拦截和保留的测试数据，不验证真实 OAuth 或飞书服务。
上述本地检查不代表真实服务器部署或外部服务已完成验证。
固定版本的飞书客户端库可能产生现有依赖的弃用提示。
