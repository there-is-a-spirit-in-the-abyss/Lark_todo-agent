# Windows 图形安装器

两个项目各自提供 Windows x64 单文件安装器：`huiyang-setup.exe` 与 `team-todo-setup.exe`。客户端不需要另外安装 Python、Node、SSH 或 Docker。当前不提供 Windows ARM64、macOS 或 Linux 桌面客户端。服务器上应用运行在 Docker 中；源码回退构建使用容器中的 Node 22 与 Python 3.11，不直接安装到服务器系统。

## 使用前准备

准备 Linux 服务器的公网地址、SSH 端口、用户名，以及密码或私钥文件；私钥可以有口令。需要 root 或可用 sudo，必要时填写 sudo 密码。支持 Linux x86_64 / aarch64，Debian / Ubuntu、OpenCloudOS / Rocky / AlmaLinux / CentOS 系列；具体发行版与版本仍需通过安装器预检和 Docker 官方仓库支持检查，停止支持的版本不会强行安装。已有 Docker/Compose 会被复用。

默认安装目录分别是 `/Lark_todo-agent` 和 `/team-todo`。可在界面浏览、创建并选择绝对路径，支持空格和中文。不要选择已有其他文件的业务目录；安装器只允许更新属于本项目的受管安装，拒绝符号链接目录。

首次连接核对 SSH 主机指纹并明确接受；保存过的指纹发生变化时会拒绝连接。连接密码、私钥口令和 sudo 密码不保存到偏好设置。应用必需的配置会写入目标目录权限受限的 `.env`。仅能导入明确选中的本地或当前安装的远程 `.env`；不会提取浏览器登录账号，也不会搜索其他文件。

汇漾需要飞书自建应用的 App ID / App Secret、模型 HTTPS Base URL、API Key 和模型名。飞书应用凭据来自飞书开发者后台，与当前浏览器登录的飞书个人账号不同。部署后按向导显示的精确回调地址手动配置 OAuth、应用权限、发布与可见范围；模型账号、额度、模型权限、云防火墙和域名解析也需自行确认。Team Todo 使用 SQLite，无需飞书或模型凭据；汇漾使用 PostgreSQL，安装器生成数据库密码。

## 安装与维护

打开对应的 `.exe`，连接 SSH，核对服务器检查结果和目录，填写应用与访问地址后点击部署。只有点击部署后，才会按预检结果安装缺失且受支持的 Docker/Compose。正式 Release 安装包使用固定 SHA-256 摘要的镜像；本地安装包没有镜像地址时会自动上传干净的源码包，在服务器 Docker 中构建，首次耗时更长且需要联网下载依赖。

默认 HTTPS 使用共享 Caddy 网关，同一服务器可分别承载汇漾 `/team`、`/api/team` 与 Team Todo 根路径。共享配置保存在 `/var/lib/huiyang-installer`，保留已有受管路由。如 80/443 已被其他代理占用，安装会停止并给出处理提示，不会替换该服务。域名或公网 IP 的证书签发需要 ACME 校验端口可达；需要在云控制台手动放通端口。可选 HTTP 仅用于独立 Team Todo。

维护页提供状态、脱敏日志、重启、一致性备份、升级及应用镜像回退。升级保留已有密钥和业务数据，先备份部署配置；镜像回退不会自动回滚数据库迁移，也不会用旧库覆盖新数据。备份下载后自行妥善保管，其中可能包含业务数据。安装回执不包含密钥。部署失败时以错误提示为准，不会把失败显示为可用地址。

容器健康检查通过，只说明应用容器启动并响应；并不代表飞书授权、模型调用、账号权限、云防火墙或公网证书已经完成真实验证。本次开发仅做本地测试，没有连接真实服务器、申请公网证书、发布 GitHub 或验证真实飞书/模型集成。

## 开发构建

在项目根目录使用 **Windows x64 Python 3.11**。Tkinter 随官方 Windows Python 安装；Paramiko 和 PyInstaller 会被打入单文件。

```powershell
py -3.11 -m venv .runtime/installer-venv
.runtime/installer-venv/Scripts/python.exe -m pip install -r installer/requirements-build.txt
.runtime/installer-venv/Scripts/python.exe -m pytest installer/tests -q
.runtime/installer-venv/Scripts/python.exe installer/build.py --bundle-only
.runtime/installer-venv/Scripts/python.exe installer/build.py
```

产物位于 `installer/dist/<project>-setup.exe` 及旁边的 `.exe.sha256`；`<project>` 来自 `installer/project.json`。构建不需要 Git 仓库，不会创建 Git 仓库、连接部署服务器或发布资源。源码归档包含生产代码、Dockerfile、`.dockerignore`、前端源文件与 npm 锁文件，排除真实 env、数据库、密钥文件、缓存、依赖目录、截图、测试结果及日志。不要把真实凭据硬编码到生产源码中。`installer/bundle`、`installer/build`、`installer/dist` 是生成目录，不应提交。

正式镜像可通过参数指定，必须使用不可变摘要。版本号（含 Release 标签）最多 80 字符，首位为字母或数字，其余只允许字母、数字、`.`、`_`、`+`、`-`：

```powershell
python installer/build.py --version v1.0.0 --image ghcr.io/your-owner/your-repository@sha256:<64位小写十六进制摘要>
```

即使指定镜像也始终包含源码回退包。`installer/bundle/manifest.json` 的字段是 `project`、`version`、`image`、`sha256`，最后一项是 `source.tar.gz` 的 SHA-256。冻结后的程序从 `_MEIPASS/bundle` 读取，开发运行从 `installer/bundle` 读取。PyInstaller 使用 `--onefile --windowed` 打包。

无窗口程序可能没有标准输出，自动自检须使用输出文件：

```powershell
$exe = (Resolve-Path installer/dist/*-setup.exe).Path
$process = Start-Process -FilePath $exe -ArgumentList '--self-test','--self-test-output','self-test.json' -Wait -PassThru -WindowStyle Hidden
Get-Content self-test.json
& $exe --preview
```

`--self-test` 校验项目与归档完整性，输出 `project`、`version`、`image`、`source_sha256`、`bundled`、`credentials_embedded`、`gui_available`，不连接服务器。`--preview` 只做本地图形预览，禁用连接操作；`--smoke-ui --self-test-output gui-smoke.json` 自动打开界面、切换配置页并退出，输出 `gui_ready`。

## GitHub Release 工作流

此目录的 `.github/workflows/release.yml` 在发布 Release 后执行应用与安装器测试，构建并推送 `linux/amd64`、`linux/arm64` 镜像，然后把不可变摘要写入 Windows 安装包，上传 `.exe` 和 `.sha256` 到该 Release。镜像名完全由实际 `github.repository` 小写转换得到，不预设仓库所有者。仅使用该次工作流的 `GITHUB_TOKEN`；镜像 job 需要 `packages: write`，Release 上传 job 需要 `contents: write`。无需把 SSH、飞书、模型或服务器凭据放进 Actions secrets。

**公开代码仓库不等于 GHCR 包公开。** 首次推送后，在账号/组织的 Packages 中找到容器包，进入 Package settings，把可见性设为 Public，并确认包与仓库关联及 Actions 访问权限。组织策略可能限制发布权限。工作流退出登录后检查匿名拉取能力；若此时包仍私有则停止，调整可见性后重新运行失败的工作流。安装器不内置 GHCR 访问令牌。

手动 `workflow_dispatch` 只构建检查多架构镜像，不推送 GHCR，不发布 Release；Windows 产物作为 Actions artifact 下载，使用源码构建路径。版本默认取提交标识。工作流定义已提供，但实际云端执行和多架构 Docker 构建需在 GitHub/有 Docker 的环境验证。

参考：[GitHub 容器注册表及可见性](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)、[Docker 构建动作及 digest 输出](https://github.com/docker/build-push-action)。
