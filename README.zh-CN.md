# 汇漾 · 飞书任务 Agent

[English](README.md) | 简体中文

## 功能

**个人任务告诉机器人，团队进度用任务树展开。**

- **聊天记录个人任务**：在飞书私聊中告诉机器人要做什么，通过自然语言创建、查询和更新待办，并接收提醒。
- **快速搭建团队项目**：同一企业或团体的成员，通过飞书群进入共享任务网页，将项目逐层拆解为任务和子任务。
- **直观看到项目进度**：用树形结构呈现任务关系与状态，根据任务完成情况计算项目进度。
- **按实际工作灵活调整**：支持多项目、共享暂存区和整条任务分支移动，既能先记零散任务，也能逐步整理成完整项目。
- **按群协作**：不同群有独立任务板，网页通过飞书验证成员身份，并按任务规则检查操作权限。

例如：私聊机器人安排个人待办；在项目群中提及机器人并发送“团队任务”，打开网页，搭建“产品发布 → 设计 / 开发 / 测试”的任务树。
普通群聊消息不会自动被记录为任务。

### 个人 Todo：聊天记录，到点提醒

把任务和提醒时间告诉飞书机器人，随后可继续查询自己的待办。下面的对话展示了创建“吃药”待办、查询任务，以及机器人实际发出提醒的案例。

[![飞书个人 Todo：通过聊天创建、查询待办并收到提醒](docs/images/lark-personal-todo.png)](docs/images/lark-personal-todo.png)

### 项目 Todo：重点看清团队进度

项目以任务树呈现：项目、任务和子任务之间的关系、任务状态与负责人放在同一张图中。顶部进度条显示已结束任务的比例，左侧切换项目，适合把复杂工作逐层拆解、持续跟踪。

下图为项目任务树界面示例，展示六个任务的层级关系及 1/6 已结束的进度。

[![项目 Todo 任务树示例：六个任务的层级关系和 1/6 已结束的项目进度](docs/images/lark-project-progress.png)](docs/images/lark-project-progress.png)

## 下载

**[下载飞书 Agent 安装包 · huiyang-setup.exe](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases/latest/download/huiyang-setup.exe)**

[全部版本与校验文件](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent/releases) · [GitHub 项目地址](https://github.com/there-is-a-spirit-in-the-abyss/Lark_todo-agent)

下载后双击安装包即可打开部署向导，电脑无需另外安装 Python、Node.js 或 SSH。
仓库目前为私有，下载安装包需要登录有访问权限的 GitHub 账号。

## 安装与部署

### 准备什么

- 一台可通过 SSH 连接的 Linux 服务器，以及服务器地址、端口、用户名和密码或私钥。
- 同一企业或团体的飞书群，以及创建和配置企业自建应用的权限。
- 飞书应用的 App ID / App Secret，以及模型接口地址、API Key 和模型名称。
- 团队网页使用的 HTTPS 访问地址，并放通部署和证书验证所需端口。

### 部署顺序

1. 创建飞书企业自建应用，启用机器人，取得 App ID / App Secret；按下表将截图中的 10 项应用身份权限**全部开通**，配置数据范围并发布初始版本。
2. 准备模型配置；使用 DeepSeek 时，按下方[获取 DeepSeek API](#deepseek-api)教程创建自己的 Key。
3. 打开 `huiyang-setup.exe`，填写 SSH 信息、安装目录、飞书凭据、模型参数和网页访问地址；已有 `.env` 可以导入。
4. 点击一键部署并等待服务器启动成功。**重定向 URL 在填写各项配置并成功部署后，由安装器给出**，可在部署结果或日志中找到。
5. 复制这个完整 URL，回到飞书后台的“安全设置 → 重定向 URL”，添加并保存。
6. 程序启动并建立飞书长连接后，在“事件与回调”选择长连接接收事件，保存，并订阅 `im.message.receive_v1`。
7. 发布这些配置变更并完成审批，将机器人加入目标群；测试个人待办、实际提醒，以及群内提及机器人发送“团队任务”后打开的协作网页。

飞书应用创建、权限开通、事件订阅、发布审批和回调登记需要手动完成；安装器负责服务器上的部署。

### 创建应用、获取凭据并添加机器人

<details>
<summary>展开创建应用的三张操作图</summary>

进入[飞书开放平台](https://open.feishu.cn/app)，点击“创建企业自建应用”。

[![飞书开放平台：创建企业自建应用](docs/images/feishu-create-app.png)](docs/images/feishu-create-app.png)

在“凭证与基础信息”中取得自己应用的 App ID 和 App Secret，填入安装器对应字段。

[![应用凭证页面：App ID 和已隐藏的 App Secret 位置](docs/images/feishu-app-credentials.png)](docs/images/feishu-app-credentials.png)

在“添加应用能力”中添加“机器人”。

[![添加应用能力：选择机器人并添加](docs/images/feishu-add-bot.png)](docs/images/feishu-add-bot.png)

</details>

### 权限：截图列出的 10 项全部开通

**按下图逐项开通，全部显示“已开通”后再继续。** 在“权限管理 → 开通权限”中选择“应用身份权限”，按标识搜索，避免漏开。

| 权限标识 | 用途 |
|---|---|
| `contact:contact.base:readonly` | 获取通讯录基本信息 |
| `contact:user.base:readonly` | 获取用户基本信息 |
| `contact:user.employee_id:readonly` | 获取用户 user ID |
| `im:chat.members:read` | 查看群成员 |
| `im:chat:read` | 查看群信息 |
| `im:message` | 获取与发送单聊、群组消息 |
| `im:message.group_msg` | 获取群组中所有消息 |
| `im:message.p2p_msg:readonly` | 读取用户发给机器人的单聊消息 |
| `im:message:send_as_bot` | 以应用身份发消息 |
| `im:resource` | 获取与上传图片或文件资源 |

[![需要全部开通的十项飞书应用身份权限](docs/images/feishu-permissions.png)](docs/images/feishu-permissions.png)

<details>
<summary>展开权限添加与通讯录数据范围示例</summary>

搜索并勾选应用身份权限；截图以 `contact:user.base:readonly` 为例。对上表所有权限逐项完成。

[![搜索并勾选应用身份权限的操作示例](docs/images/feishu-add-permission.png)](docs/images/feishu-add-permission.png)

按示例将通讯录可访问数据范围设为“全部成员”，并确认应用的可用范围包含实际参与使用的人，保存、确认开通。

[![通讯录数据范围设置为全部成员并确认开通](docs/images/feishu-data-scope.png)](docs/images/feishu-data-scope.png)

</details>

### 重定向 URL：先部署，再复制到飞书后台

**先填完安装器各项配置并点击一键部署；部署成功后会得到完整的重定向 URL，再填入下图位置。**
它来自本次部署的实际 HTTPS 地址，以 `/api/team/callback` 结尾；带“飞书配置”页的安装器版本可以直接复制，其他版本可从部署日志取得。

例如网页地址是 `https://tasks.example.com/team`，重定向 URL 则为：

```text
https://tasks.example.com/api/team/callback
```

上面是格式示例。实际使用时，复制自己安装器给出的完整链接，到“安全设置 → 重定向 URL”点击“添加”并保存。

[![飞书安全设置：添加部署后获得的完整重定向 URL](docs/images/feishu-redirect-url.png)](docs/images/feishu-redirect-url.png)

### 启动后配置长连接与消息事件

<details>
<summary>展开长连接保存与消息事件订阅示例</summary>

服务器程序启动并成功建立飞书长连接后，进入“事件与回调”，选择“使用长连接接收事件”，验证连接并保存。尚未建立连接时，先检查部署状态和应用凭据。

[![选择长连接接收事件并在建立连接后保存](docs/images/feishu-long-connection.png)](docs/images/feishu-long-connection.png)

点击“添加事件”，搜索并添加“接收消息”事件 `im.message.receive_v1`。

[![添加接收消息事件 im.message.receive_v1](docs/images/feishu-message-event.png)](docs/images/feishu-message-event.png)

</details>

### 发布并验证

<details>
<summary>展开应用可用范围与发布成功示例</summary>

在“版本管理与发布”中创建版本，确保可用范围包含实际使用人员，保存并提交审批。截图同时展示了示例账号的外部共享选项；企业内协作按本企业使用范围设置即可。

[![版本发布设置：可用范围及示例账号的外部共享选项](docs/images/feishu-publish-settings.png)](docs/images/feishu-publish-settings.png)

收到“应用审批通过，已发布成功”通知后，确认机器人已加入目标群，再验证私聊任务、提醒和群内团队网页。

[![飞书通知：应用通过管理员审批并发布成功](docs/images/feishu-publish-success.png)](docs/images/feishu-publish-success.png)

</details>

[安装器详细说明](installer/README.md) · [飞书与模型接入清单](docs/MANUAL_SETUP.md) · [团队网页部署指南](docs/TEAM_WEB_SETUP.md)

<details>
<summary>语言设置、源码部署、任务规则与验证</summary>

### 语言设置

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

### 安装与部署

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

### 任务规则与边界

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

### 本地验证

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

</details>

<a id="deepseek-api"></a>

## 获取 DeepSeek API

下面保留提供的五张 DeepSeek 操作截图，按“登录平台 → 查看余额／按需充值 → 创建 Key → 复制保存 → 填入安装器”操作。

### 1. 登录开放平台，查看用量与余额

打开 [DeepSeek 开放平台](https://platform.deepseek.com/)，登录或注册自己的账号。在“用量信息”查看 API 使用情况和可用余额。

[![DeepSeek 开放平台用量信息及余额页面](docs/images/deepseek-usage.png)](docs/images/deepseek-usage.png)

### 2. 按需充值

需要增加可用余额时，进入[充值页面](https://platform.deepseek.com/top_up)，按平台显示选择金额和支付方式。截图金额是示例，不是部署要求；API 费用、可用额度及支付方式以平台当前页面为准。

[![DeepSeek API 充值页面示例：选择金额及支付方式](docs/images/deepseek-top-up.png)](docs/images/deepseek-top-up.png)

### 3. 创建 API Key

进入 [API keys](https://platform.deepseek.com/api_keys)，点击“创建 API key”。

[![DeepSeek API keys 页面：点击创建 API key](docs/images/deepseek-api-keys.png)](docs/images/deepseek-api-keys.png)

给 Key 填写一个便于辨认的名称，例如“飞书 Todo”，然后点击“创建”。

[![为 DeepSeek API Key 命名并创建](docs/images/deepseek-create-key.png)](docs/images/deepseek-create-key.png)

### 4. 立即复制并保存

创建完成后点击“复制”，保存好完整 Key，再填写到安装器的“模型 API Key”。Key 的完整内容只在创建时展示，遗失后需要重新创建；图中密钥已做遮挡。

[![创建完成后复制 DeepSeek API Key，截图中的密钥已遮挡](docs/images/deepseek-copy-key.png)](docs/images/deepseek-copy-key.png)

### 5. 填入飞书 Agent 安装器

| 安装器配置项 | 填写内容 |
|---|---|
| 模型提供方 `LLM_PROVIDER` | `deepseek` |
| 模型 HTTPS API 地址 `LLM_API_BASE_URL` | `https://api.deepseek.com` |
| 模型 API Key `LLM_API_KEY` | 刚创建并复制的完整 Key |
| 模型名称 `LLM_MODEL` | 平台当前提供的模型标识，例如 `deepseek-flash` |

本项目的 `deepseek` 适配器使用 Responses API，填写上表的 API 根地址即可，程序会追加 `/responses`。
不要把平台网页地址或完整 `/responses` 路径填进 API 根地址。模型名称以自己的账号当前可用模型为准。

参数依据：[DeepSeek 官方 Responses API 指南](https://api-docs.deepseek.com/zh-cn/guides/responses_api/)及[接口参考](https://api-docs.deepseek.com/zh-cn/api/create-response/)。
填写后继续上方服务器部署，再通过真实飞书对话验证模型响应、个人待办与提醒。
