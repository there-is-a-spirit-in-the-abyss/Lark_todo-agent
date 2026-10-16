# Installer implementation plan

> **For agentic workers:** Use test-driven-development and dispatching-parallel-agents for independent file owners. The user explicitly authorized coding without another approval round.

**Goal:** Deliver double-click Windows deployment wizards in both local projects.
**Architecture:** Bundled Python/Tkinter client, Paramiko SSH/SFTP, Docker Compose app profiles and a managed HTTPS gateway. Shared installer source is mirrored into both delivery trees.
**Tech stack:** Python 3.11, Tkinter, Paramiko, PyInstaller, pytest, Docker Compose, GitHub Actions.
**Spec:** ../specs/2026-10-16-installer-design.md

## Constraints

- Only edit C:/Users/渊中有灵/Desktop/huiyang_source and C:/Users/渊中有灵/Desktop/项目todo.
- No real server connection, no GitHub publish, no actual credentials in artifacts.
- Defaults /Lark_todo-agent and /team-todo; each project has its own executable.
- No Git metadata exists; do not invent commits/worktrees.

## Review focus

- Shell metacharacters in SSH host/user, directory names, domains, imported values and log output.
- Existing unmanaged folders, mismatched profiles, symlinks and interrupted upgrades.
- Private-key passphrases, first host trust and changed keys.
- Existing proxy/ports and two projects sharing one HTTPS host.
- Failure recovery, backup consistency and absent published registry image.

### Task 1: validated installer inputs and credentials

Owner: primary agent. Files installer/deployer/models.py, config.py, tests/test_config.py.
- [x] Add and run failing behavioral tests for defaults, path validation, env imports, redaction and model endpoint validation.
- [x] Implement Connection, Profile, Bundle and DeployRequest data contracts, config parser and safe validation.
- [x] Run focused tests and record results.

### Task 2: SSH and remote deployment engine

Owner: independent remote-engine worker. Files installer/deployer/ssh.py, remote.py, templates.py, scripts/*, tests/test_remote.py and test_ssh.py.
- [x] Add failing behavioral tests for trust, directory ownership, safe config generation and data-preserving maintenance.
- [x] Implement RemoteSession with connect, inspect, list_directories, mkdir, read_env, deploy, maintain, close; use contracts from Task 1.
- [x] Validate command timeouts, private writes, sudo, shared gateway ownership and failure states.

### Task 3: native installer UI

Owner: primary agent. Files installer/deployer/gui.py, installer/launch.py.
- [x] Write tests for wizard state transitions and operation gating; observe failure.
- [x] Implement Chinese connection, destination browser, config import, deployment progress/result and maintenance UI.
- [x] Run local GUI smoke using synthetic connection data; never connect a real server.

### Task 4: source/image/executable packaging

Owner: independent packaging worker. Files Dockerfile, .dockerignore, installer/project.json, installer/build.py, requirements*, .github/workflows/release.yml, installer/README.md in both projects.
- [x] Test clean source archive generation with credentials/runtime fixtures excluded.
- [x] Make Huiyang Dockerfile build the frontend internally; keep container paths independent of host destination.
- [x] Add multiarch image build plus Windows standalone executable releases, using digest references and no embedded registry credentials.
- [x] Build both actual executable files locally and validate their bundled manifest.

### Task 5: integration and verification

Owner: primary agent, then fresh independent review.
- [x] Mirror installer source to the second project, preserving project.json and app-specific changes.
- [x] Run installer tests, app backend suites, frontend units/builds and executable smoke.
- [x] Review whole implementation for safety and user requirements; fix substantive findings with regression coverage.
- [x] Update verification and hand off local executable links, remaining external steps and untested integrations.
