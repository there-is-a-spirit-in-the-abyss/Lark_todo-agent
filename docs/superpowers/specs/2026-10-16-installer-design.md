# Huiyang and Team Todo installers

The user authorized implementation in the two local source directories. No connection to, changes on, or rollout to any real server is authorized in this task. Do not publish to GitHub. Do not create a Git repository or relocate the user's working copies.

## User experience

Each project ships its own Windows x64 executable, bundling Python, Tk and SSH dependencies with PyInstaller. The same maintained installer source is included in each project; project.json identifies huiyang or team-todo. The Chinese wizard connects using an SSH password or private-key file (optional passphrase), checks the remote host, browses and creates remote directories, deploys, then shows a clickable URL and status. Default server directories are /Lark_todo-agent and /team-todo. Both folder names are ASCII. Custom absolute Linux paths may contain spaces and Unicode.

New host keys require explicit fingerprint acceptance; changed saved keys are rejected. Credentials remain in memory, except the application's required private .env on the target server. No credentials are baked into release assets, saved in user preferences, printed in logs or included in diagnostics. Import only a user-selected local .env or remote .env; never scrape browser accounts or search unrelated files. App ID and App Secret belong to a Feishu application, not a logged-in account.

## Deployment

Support Linux x86_64 and aarch64. Support Debian/Ubuntu and RPM-family OpenCloudOS/Rocky/AlmaLinux/CentOS hosts using supported Docker repositories; reject unsupported systems clearly. Require root or working sudo, with optional sudo password. Reuse existing Docker without upgrading or restarting it. A missing supported Docker/Compose installation can be installed after the user clicks deploy.

The selected directory contains compose.yaml, private .env, application data and an installer ownership manifest. An unrelated nonempty directory must never be overwritten or adopted. A symlink directory must not redirect writes. A managed existing installation can be updated, preserving secrets and data. Project identity and paths must be checked for every maintenance operation. Validate paths and shell arguments, serialize operations, use private upload permissions, and never run user values as shell code.

GitHub releases build and publish prebuilt multi-architecture app images, then bundle the immutable image reference into the executable. As the local copies have no GitHub repository/image yet, locally built executables also include a clean source archive and can build it automatically using Docker on the target. No Python or Node is installed directly on the user's computer or target host. Release archives exclude credentials, databases, caches, dependencies, screenshots and deployment logs.

HTTPS is the default. A small installer-owned shared Caddy gateway serves Huiyang /team and /api/team routes and Team Todo's root routes on the same host, using an external Docker network and distinct per-installation aliases. Gateway configuration belongs under /var/lib/huiyang-installer and its existing routes must be preserved. If ports 80/443 belong to an unrelated service, stop with actionable guidance; never replace that proxy automatically. Domain and public-IP HTTPS need reachable ACME validation ports; cloud firewall changes require user action unless separately authorized. Optional HTTP mode is for standalone Team Todo only.

Huiyang requires Feishu App ID/Secret, model HTTPS base URL/key/name, and uses PostgreSQL with a generated password. The installer generates the exact OAuth callback instruction for the chosen origin. It distinguishes container health from live Feishu/model/account permission verification. Team Todo requires no Feishu or model credentials and uses SQLite.

## Maintenance

Expose status, redacted recent logs, restart, consistent database backup, upgrade and application-image rollback. Back up existing deployment configuration before an update; preserve application data. Rollback must not blindly downgrade database migrations or restore an old database over newer data. Include an installation receipt containing no secrets. Initial deployment failure must be reported honestly and must not display a success URL.

## Validation and delivery

Write behavioral tests before implementation for path validation/injection, env parsing/secret handling, ownership checks, host-key trust, configuration generation, update preservation and rollback limits. Exercise the real GUI locally and build both standalone executables. Run both existing application test suites and frontend checks appropriate to Dockerfile changes. Validate release definitions locally where tools allow; report that actual Linux provisioning, public certificates, GitHub publication and live Feishu integration are not exercised, because the user requested local-only work.
