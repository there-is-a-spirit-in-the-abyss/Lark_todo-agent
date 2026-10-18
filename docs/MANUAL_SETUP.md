# 飞书与模型接入清单

在你自己的项目目录和飞书企业自建应用中完成配置。本文使用占位域名
`https://team.example.com`，请替换为实际部署地址；此源码副本没有连接线上环境。

## 1. 本地配置

参考 `.env.example` 创建私有 `.env`，填写 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、
`LLM_PROVIDER`、`LLM_API_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`，并生成随机
`POSTGRES_PASSWORD`。不要提交真实凭据，不要覆盖已有部署的数据库密码。
`APP_LANGUAGE` 可设 `zh-CN` 或 `en-US`，默认简体中文。

## 2. 飞书权限与事件

在企业自建应用中启用机器人。按 README 截图，将下面 **10 项应用身份权限全部开通**，确认每项均显示“已开通”：

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

在“权限管理 → 开通权限”中选择“应用身份权限”，按标识逐项搜索。
按提供的示例将通讯录数据范围设为“全部成员”，并确认应用可用范围包含实际使用人员。
权限变更按企业要求发布、审批。已有 `im:chat` 或 `im:chat:readonly` 权限也可供群信息接口使用；上表是本教程截图采用的完整配置。

服务器程序启动并建立长连接后，在“事件与回调”选择长连接接收事件，验证并保存，再订阅 `im.message.receive_v1`。
图文步骤与操作截图见 [README 安装与部署](../README.zh-CN.md#安装与部署)。

个人/旧群模式的管理员只在首次群消息时读取群主真实 ID 并保存，无需群主发言、
昵称匹配、登记码或手工填写 ID。绑定后不随改名或群主转让自动替换。
初始化前只把机器人加入预期目标群。网页模式不通过群入口消息初始化管理员。

## 3. 模型与网页

选择支持对应严格 JSON Schema 协议的模型端点：`openai_compatible` 使用
Chat Completions，`deepseek` 使用 Responses。必须配置 HTTPS API root。

DeepSeek 账号创建、按需充值和 API Key 获取步骤见 [DeepSeek 图文教程](../README.zh-CN.md#deepseek-api)。
本项目采用以下配置，对应官方 Responses API：

```dotenv
LLM_PROVIDER=deepseek
LLM_API_BASE_URL=https://api.deepseek.com
LLM_API_KEY=<填写自己的完整密钥>
LLM_MODEL=deepseek-flash
```

`deepseek-flash` 为当前官方文档中的示例标识，实际以账号可用模型为准。
程序追加 `/responses`，因此填写 API 根地址即可。参考 [官方接口说明](https://api-docs.deepseek.com/zh-cn/guides/responses_api/)。

填写完安装器各项配置并一键部署成功后，复制部署结果或日志给出的完整重定向 URL，
到飞书“安全设置 → 重定向 URL”中添加并保存。该 URL 以 `/api/team/callback` 结尾，
例如 `https://tasks.example.com/api/team/callback`；实际使用自己的部署地址。

私聊发送 `/language en-US` 或 `/language zh-CN` 选择语言。网页通过右上角
**Language / 语言** 独立切换。网页部署和 OAuth callback 见
[TEAM_WEB_SETUP.md](TEAM_WEB_SETUP.md)。纯长连接机器人不需要入站 Webhook。

## 4. 启动后自行验证

按 README 构建、迁移并启动，先检查 `/health`，再由真实成员验证私聊任务、
语言切换、提醒和群入口。网页模式用两位成员验证登录、任务权限和撤销成员后的拒绝访问。
模型、真实飞书权限、TLS、OAuth 与消息投递必须在你的环境中验证；本地测试不能替代。

诊断命令在容器中执行：`python -m huiyang.manage check`、`status`、`admin-status`、
`probe-llm`。`discovered` 会显示真实成员和群标识，仅在私有终端查看。
平台凭据更新后重新创建 app 容器以读取新值。
