# 飞书与模型接入清单

在你自己的项目目录和飞书企业自建应用中完成配置。本文使用占位域名
`https://team.example.com`，请替换为实际部署地址；此源码副本没有连接线上环境。

## 1. 本地配置

参考 `.env.example` 创建私有 `.env`，填写 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、
`LLM_PROVIDER`、`LLM_API_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`，并生成随机
`POSTGRES_PASSWORD`。不要提交真实凭据，不要覆盖已有部署的数据库密码。
`APP_LANGUAGE` 可设 `zh-CN` 或 `en-US`，默认简体中文。

## 2. 飞书权限与事件

在企业自建应用中启用机器人和官方 SDK 长连接，订阅 `im.message.receive_v1`。
基础收发消息沿用 `im:message.group_msg`、`im:message.p2p_msg:readonly`、
`im:message:send_as_bot`；消息中的真实 user_id 需要
`contact:user.employee_id:readonly`。

群信息读取使用 `im:chat:read`；接口也支持相应的 `im:chat` 或
`im:chat:readonly` 已有权限。个人任务的用户姓名同步需要
`contact:contact.base:readonly`、`contact:user.base:readonly` 和相应姓名字段权限，
通讯录数据范围应包含实际成员。网页模式还需要 `im:chat.members:read`。
权限变更须按企业要求发布、审批，具体权限可在飞书控制台核对。

个人/旧群模式的管理员只在首次群消息时读取群主真实 ID 并保存，无需群主发言、
昵称匹配、登记码或手工填写 ID。绑定后不随改名或群主转让自动替换。
初始化前只把机器人加入预期目标群。网页模式不通过群入口消息初始化管理员。

## 3. 模型与网页

选择支持对应严格 JSON Schema 协议的模型端点：`openai_compatible` 使用
Chat Completions，`deepseek` 使用 Responses。必须配置 HTTPS API root。

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
