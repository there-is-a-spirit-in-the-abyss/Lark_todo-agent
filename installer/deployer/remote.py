"""Privileged deployment orchestration; importing this module never connects."""
from __future__ import annotations

import hashlib
import csv
import io
import json
import posixpath
import re
import shlex
import tarfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .config import import_env, normalize_directory, parse_env, redact, validate_deployment, validate_host
from .models import Bundle, Connection, DeployRequest, RemoteDirectory, ServerInfo
from .ssh import SSHTransport
from .templates import (GATEWAY_NETWORK, GATEWAY_ROOT, compose_document, dotenv,
                        environment, gateway_compose, gateway_document, json_bytes)

MANIFEST = '.huiyang-installer.json'
OWNER = 'huiyang-installer'
LOCK = '/var/lib/huiyang-installer-operation-lock'


class PublicVerificationError(RuntimeError):
    """The app is healthy but public TLS has not yet been verified."""


SQLITE_BACKUP_CODE = '''import os, pathlib, sqlite3, sys
source = sqlite3.connect(pathlib.Path(sys.argv[1]).as_uri() + '?mode=ro', uri=True, timeout=30)
temporary = sys.argv[2] + '.partial'
try:
    destination = sqlite3.connect(temporary, timeout=30)
    try:
        source.backup(destination)
    finally:
        destination.close()
    os.chmod(temporary, 0o600)
    os.replace(temporary, sys.argv[2])
finally:
    source.close()
    if os.path.exists(temporary):
        os.unlink(temporary)
'''


def check_manifest(manifest: dict, directory: str, profile_id: str):
    if (not isinstance(manifest, dict) or manifest.get('owner') != OWNER
            or manifest.get('schema') != 1 or manifest.get('profile') != profile_id
            or manifest.get('directory') != directory):
        raise ValueError('目录不属于此项目的安装器，或安装位置已改变；拒绝操作。')


def _absolute(path: str) -> str:
    if not isinstance(path, str) or not path.startswith('/') or len(path) > 2048:
        raise ValueError('需要有效的 Linux 绝对路径。')
    if any(ord(c) < 32 or ord(c) == 127 for c in path) or any(p in ('.', '..') for p in path.split('/')):
        raise ValueError('路径包含不安全的字符或路径跳转。')
    return re.sub('/+', '/', path).rstrip('/') or '/'


def _identity(profile: str, directory: str) -> str:
    return 'hy-' + hashlib.sha256((profile + ':' + directory).encode()).hexdigest()[:16]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]


class RemoteSession:
    def __init__(self, connection: Connection, trust_callback):
        self.connection = connection
        self.ssh = SSHTransport(connection, trust_callback)
        self._lock = threading.Lock()
        self._secrets = [connection.password, connection.passphrase, connection.sudo_password]

    def connect(self) -> ServerInfo:
        self.ssh.connect()
        return self.inspect()

    def close(self):
        self.ssh.close()

    def inspect(self) -> ServerInfo:
        result = self.ssh.run('''
. /etc/os-release
printf '%s\\n' "$ID" "$VERSION_ID" "$(uname -m)" "$(id -un)"
docker --version 2>/dev/null || true
docker compose version --short 2>/dev/null || true
df -Pm / | awk 'NR==2 {print $4}'
awk '/MemTotal:/ {print int($2/1024)}' /proc/meminfo
''').splitlines()
        if len(result) < 6:
            raise RuntimeError('无法读取服务器系统信息。')
        system, version, architecture, user = result[:4]
        if system.lower() not in ('ubuntu','debian','opencloudos','rocky','almalinux','centos'):
            raise ValueError(f'暂不支持 {system}；支持 Ubuntu/Debian/OpenCloudOS/Rocky/AlmaLinux/CentOS。')
        if architecture not in ('x86_64', 'aarch64'):
            raise ValueError(f'暂不支持 CPU 架构 {architecture}。')
        middle = result[4:-2]
        docker = next((x for x in middle if x.startswith('Docker version ')), '')
        compose = next((x for x in middle if re.match(r'^v?\d+\.\d+', x)), '')
        return ServerInfo(system=system, version=version, architecture=architecture, user=user,
                          docker=docker, compose=compose, free_mb=int(result[-2]), memory_mb=int(result[-1]),
                          message='root/sudo 检查通过。已有 Docker 将保留。')

    def _safe(self, path: str, file=False) -> str:
        path = _absolute(path)
        parts = path.strip('/').split('/') if path != '/' else []
        for index in range(len(parts)):
            current = '/' + '/'.join(parts[:index+1])
            kind = self.ssh.kind(current)
            if kind == 'symlink' or (kind not in ('directory','missing') and not (file and index == len(parts)-1 and kind == 'file')):
                raise ValueError('路径包含符号链接或非目录项目；拒绝写入或读取。')
        return path

    def list_directories(self, path: str) -> list[RemoteDirectory]:
        path = self._safe(path)
        return [RemoteDirectory(name, posixpath.join(path, name))
                for name, kind in sorted(self.ssh.list_directory(path))
                if kind == 'directory' and not any(ord(c) < 32 for c in name)]

    def mkdir(self, path: str):
        path = normalize_directory(path)
        with self._lock:
            self._safe(path)
            self.ssh.mkdir(path)

    def read_env(self, path: str) -> dict[str, str]:
        # Called only with the file explicitly selected by the user.
        path = self._safe(path, file=True)
        if posixpath.basename(path) != '.env':
            raise ValueError('请选择明确的 .env 文件。')
        return import_env(self.ssh.read_file(path).decode('utf-8-sig'))

    def _manifest(self, directory, profile_id, allow_new=False):
        self._safe(directory)
        kind = self.ssh.kind(directory)
        if kind == 'missing':
            if allow_new: return None
            raise ValueError('安装目录不存在。')
        names = dict(self.ssh.list_directory(directory))
        if MANIFEST not in names:
            if allow_new and not names: return None
            raise ValueError('该目录非空且没有本安装器的项目标识；请选择空文件夹。')
        if names[MANIFEST] != 'file':
            raise ValueError('安装标识不是普通文件。')
        try:
            manifest = json.loads(self.ssh.read_file(directory + '/' + MANIFEST).decode())
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError('安装标识损坏；拒绝操作。') from None
        check_manifest(manifest, directory, profile_id)
        for name in ('.env', 'compose.yaml', 'data', 'postgres_data', 'backups'):
            if names.get(name) in ('symlink','other'):
                raise ValueError('项目配置或数据包含符号链接；拒绝操作。')
        return manifest

    def _compose(self, directory: str, manifest: dict | None = None) -> str:
        profile = manifest['profile'] if manifest else 'team-todo'
        name = _identity(profile, directory)
        return f'docker compose --project-name {shlex.quote(name)} --project-directory {shlex.quote(directory)} -f {shlex.quote(directory + "/compose.yaml")}'

    def _begin(self):
        self._safe('/var/lib')
        self.ssh.run(f'if ! mkdir -- {shlex.quote(LOCK)}; then echo "另一个安装器正在操作，或上次会话中断。请确认没有部署后移除 {LOCK} 空锁目录。" >&2; exit 75; fi')

    def _end(self):
        try:
            self.ssh.run(f'rmdir -- {shlex.quote(LOCK)}')
        except Exception:
            pass

    def _ensure_docker(self, allow_install: bool, emit):
        available = self.ssh.run('if docker info >/dev/null 2>&1; then docker --version; docker compose version --short 2>/dev/null || true; fi').splitlines()
        if len(available) >= 2:
            emit('复用服务器现有 Docker 和 Compose。')
            return
        if not allow_install:
            raise ValueError('服务器需要可运行的 Docker 与 Compose；已禁止自动安装。')
        emit('检查受支持的系统并安装缺少的 Docker/Compose 组件（不会重启现有 Docker）。')
        self.ssh.run(DOCKER_INSTALL, timeout=1800)
        self.ssh.run('docker info >/dev/null\ndocker compose version --short')

    def _disk_space(self, directory: str, emit):
        ancestor = directory
        while self.ssh.kind(ancestor) == 'missing':
            if ancestor == '/':
                raise ValueError('无法读取服务器根目录，不能确认目标磁盘空间。')
            ancestor = posixpath.dirname(ancestor)
        result = self.ssh.run('df -Pm -- ' + shlex.quote(ancestor) + " | awk 'NR==2 {print $4}'\n"
                              + "docker_root=$(docker info --format '{{.DockerRootDir}}')\n"
                              + '[ -n "$docker_root" ] || exit 78\n'
                              + "df -Pm -- \"$docker_root\" | awk 'NR==2 {print $4}'").splitlines()
        if len(result) != 2 or not all(re.fullmatch(r'\d+', item) for item in result):
            raise ValueError('无法确认目标目录或 Docker 数据所在磁盘的剩余空间；请检查挂载后重试。')
        target_mb, docker_mb = map(int, result)
        emit(f'目标目录所在磁盘可用 {target_mb} MB；Docker 数据所在磁盘可用 {docker_mb} MB。')
        if target_mb < 256 or docker_mb < 1024:
            raise ValueError('目标目录至少需要 256 MB、Docker 数据磁盘至少需要 1024 MB 可用空间；请清理或更换磁盘后重试。实际构建可能需要更多空间。')

    def _snapshot(self, directory: str, manifest: dict, emit) -> tuple[str, dict[str, bytes]]:
        backup = directory + '/backups/' + _timestamp()
        self._safe(directory + '/backups')
        self.ssh.mkdir(backup)
        files = {}
        for name in ('.env','compose.yaml',MANIFEST):
            self._safe(directory + '/' + name, file=True)
            if self.ssh.kind(directory + '/' + name) == 'file':
                files[name] = self.ssh.read_file(directory + '/' + name)
                self.ssh.write_file(backup + '/' + name, files[name])
        emit('已备份现有私有配置。')
        return backup, files

    def _schema(self, directory: str, manifest: dict) -> str:
        compose = self._compose(directory, manifest)
        try:
            if manifest['profile'] == 'huiyang':
                script = compose + " exec -T db psql -U huiyang -d huiyang -Atc 'SELECT version_num FROM alembic_version ORDER BY version_num'"
            else:
                code = "import sqlite3,hashlib; c=sqlite3.connect('file:/app/data/team-todo.db?mode=ro',uri=True); print(hashlib.sha256(repr(c.execute(\"SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name\").fetchall()).encode()).hexdigest())"
                script = compose + ' exec -T app python -c ' + shlex.quote(code)
            result = self.ssh.run(script).strip()
            return hashlib.sha256(result.encode()).hexdigest() if result else ''
        except Exception:
            return ''  # Unknown migration state always disables image rollback.

    def _database_backup(self, directory: str, manifest: dict, backup: str):
        compose = self._compose(directory, manifest)
        if manifest['profile'] == 'huiyang':
            data = directory + '/postgres_data'
            self._safe(data)
            if self.ssh.kind(data) == 'missing' or not self.ssh.list_directory(data):
                return ''  # An initial failed attempt has no database to back up.
            self._safe(data + '/PG_VERSION', file=True)
            if self.ssh.kind(data + '/PG_VERSION') != 'file':
                raise ValueError('PostgreSQL 数据目录非空但尚未完整初始化；请检查后重试，安装器不会清理它。')
            if self.ssh.kind(directory + '/compose.yaml') != 'file' or self.ssh.kind(directory + '/.env') != 'file':
                raise ValueError('已有 PostgreSQL 数据但缺少原配置；无法安全启动数据库备份，拒绝生成新凭据。')
            path = backup + '/database.dump'
            # Start only PostgreSQL if it is stopped. Never run a previous app
            # version merely to make a backup during failure recovery.
            self.ssh.run(compose + ' up -d --wait --wait-timeout 120 db', timeout=180)
            self.ssh.run(compose + ' exec -T db pg_dump -U huiyang -d huiyang -Fc > ' + shlex.quote(path), timeout=600)
        else:
            data = directory + '/data'
            database = data + '/team-todo.db'
            for name in (database, database + '-wal', database + '-shm'):
                self._safe(name, file=True)
            if self.ssh.kind(database) == 'missing':
                return ''
            path = backup + '/database.sqlite'
            # A separate Python container works even when the app is stopped or
            # has never started. Read/write bind access permits SQLite's WAL/SHM
            # coordination; mode=ro prevents source database writes.
            self.ssh.run('docker run --rm --network none --entrypoint python '
                         + '--mount ' + shlex.quote(self._bind_mount(data, '/data')) + ' '
                         + '--mount ' + shlex.quote(self._bind_mount(backup, '/backup'))
                         + ' python:3.11-slim -c ' + shlex.quote(SQLITE_BACKUP_CODE)
                         + ' /data/team-todo.db /backup/database.sqlite', timeout=600)
        return path

    @staticmethod
    def _bind_mount(source: str, target: str) -> str:
        # --mount is CSV, so commas/quotes in custom Linux paths need an extra
        # layer of escaping before the whole argument is shell-quoted.
        output = io.StringIO()
        csv.writer(output, lineterminator='').writerow(['type=bind', 'src=' + source, 'dst=' + target])
        return output.getvalue()

    def _gateway(self, request: DeployRequest, alias: str) -> tuple[dict | None, dict[str, bytes]]:
        self._safe(GATEWAY_ROOT)
        exists = self.ssh.kind(GATEWAY_ROOT) != 'missing'
        saved = {}
        if exists:
            entries = dict(self.ssh.list_directory(GATEWAY_ROOT))
            if '.owner.json' not in entries:
                if entries: raise ValueError('共享 HTTPS 目录已有其他内容，拒绝接管。')
                owner = {'owner':OWNER,'schema':1,'routes':[]}
            else:
                self._safe(GATEWAY_ROOT + '/.owner.json', file=True)
                owner = json.loads(self.ssh.read_file(GATEWAY_ROOT + '/.owner.json'))
                if owner.get('owner') != OWNER or owner.get('schema') != 1:
                    raise ValueError('共享 HTTPS 网关不是本安装器管理，拒绝接管。')
                for name in ('.owner.json','compose.yaml','config/caddy.json'):
                    self._safe(GATEWAY_ROOT + '/' + name, file=True)
                    if self.ssh.kind(GATEWAY_ROOT + '/' + name) == 'file':
                        saved[name] = self.ssh.read_file(GATEWAY_ROOT + '/' + name)
        else:
            if not request.https: return None, {}
            owner = {'owner':OWNER,'schema':1,'routes':[]}
        routes = owner.get('routes')
        if not isinstance(routes, list): raise ValueError('共享网关路由损坏。')
        for route in routes:
            if (not isinstance(route, dict) or route.get('profile') not in ('huiyang','team-todo')
                    or not re.fullmatch(r'hy-[a-f0-9]{16}', route.get('alias',''))):
                raise ValueError('共享网关路由损坏。')
            validate_host(route.get('host',''))
            normalize_directory(route.get('directory',''))
            if (route['host'] == request.public_host and route['profile'] == request.profile.id
                    and route['directory'] != request.directory and request.https):
                raise ValueError('该域名/IP 的本项目路由已属于另一安装目录；拒绝覆盖。')
        routes = [r for r in routes if not (r['directory'] == request.directory and r['profile'] == request.profile.id)]
        if request.https:
            routes.append({'host':request.public_host,'profile':request.profile.id,'alias':alias,'directory':request.directory})
        owner['routes'] = routes
        return owner, saved

    def _write_gateway(self, owner: dict):
        self.ssh.mkdir(GATEWAY_ROOT)
        for sub in ('config','data','runtime'):
            self._safe(GATEWAY_ROOT + '/' + sub)
            self.ssh.mkdir(GATEWAY_ROOT + '/' + sub)
        self.ssh.write_file(GATEWAY_ROOT + '/compose.yaml', json_bytes(gateway_compose()))
        self.ssh.write_file(GATEWAY_ROOT + '/config/caddy.json', json_bytes(gateway_document(owner['routes'])))
        self.ssh.write_file(GATEWAY_ROOT + '/.owner.json', json_bytes(owner))

    def _gateway_command(self):
        return f'docker compose --project-name huiyang-installer-gateway --project-directory {GATEWAY_ROOT} -f {GATEWAY_ROOT}/compose.yaml'

    def _gateway_ports(self, known_owner: bool):
        # Both host listeners and Docker's NAT-only published ports must be checked.
        all_owned = self.ssh.run('docker ps -aq --filter label=com.docker.compose.project=huiyang-installer-gateway --filter label=com.docker.compose.service=gateway').split()
        if all_owned:
            if not known_owner or len(all_owned) != 1 or not re.fullmatch(r'[a-f0-9]{12,64}', all_owned[0]):
                raise ValueError('发现没有可信安装标识的同名网关容器（可能已停止），拒绝接管。')
            label = self.ssh.run('docker inspect --format ' + shlex.quote('{{ index .Config.Labels "io.huiyang.installer.owner" }}') + ' ' + shlex.quote(all_owned[0])).strip()
            if label != OWNER:
                raise ValueError('同名网关容器所有权标识不匹配，拒绝接管。')
        self.ssh.run(('known_owner=1\n' if known_owner else 'known_owner=0\n') + '''
owned=$(docker ps -q --filter label=com.docker.compose.project=huiyang-installer-gateway --filter label=com.docker.compose.service=gateway)
if [ -n "$owned" ]; then
  [ "$known_owner" = 1 ] || { echo '发现没有可信安装标识的同名网关容器，拒绝接管。' >&2; exit 76; }
  label=$(docker inspect --format '{{ index .Config.Labels "io.huiyang.installer.owner" }}' "$owned")
  [ "$label" = huiyang-installer ] || { echo '网关容器所有权标识不匹配，拒绝接管。' >&2; exit 76; }
fi
for port in 80 443; do
  for id in $(docker ps -q --filter "publish=$port"); do
    [ "$id" = "$owned" ] || { echo "端口 80/443 已被其他容器占用；请先配置现有代理或使用其他服务器。" >&2; exit 76; }
  done
done
if [ -z "$owned" ]; then
  command -v ss >/dev/null || { echo '缺少 ss，无法安全检测 HTTPS 端口占用。' >&2; exit 76; }
  busy=$(ss -H -ltn '( sport = :80 or sport = :443 )')
  [ -z "$busy" ] || { echo '端口 80/443 已被其他服务占用；安装器不会替换现有代理。' >&2; exit 76; }
fi
''')

    def _gateway_network(self):
        self.ssh.run('''
if docker network inspect huiyang-installer-gateway >/dev/null 2>&1; then
  owner=$(docker network inspect --format '{{ index .Labels "io.huiyang.installer.owner" }}' huiyang-installer-gateway)
  [ "$owner" = huiyang-installer ] || { echo '共享网络名称被其他网络占用，拒绝接管。' >&2; exit 76; }
else
  docker network create --label io.huiyang.installer.owner=huiyang-installer huiyang-installer-gateway >/dev/null
fi
''')

    def _health(self, directory, manifest):
        compose = self._compose(directory, manifest)
        # --wait is required; missing/old Compose fails clearly instead of reporting success.
        self.ssh.run(compose + ' up -d --wait --wait-timeout 240', timeout=300)
        raw = self.ssh.run(compose + ' ps --format json')
        try:
            parsed = json.loads(raw)
            rows = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        app = next((row for row in rows if row.get('Service') == 'app'), None)
        if not app or app.get('State') != 'running' or app.get('Health') != 'healthy':
            raise RuntimeError('应用容器尚未通过健康检查；部署未成功。')

    def _image(self, request, bundle, alias, emit):
        if bundle.profile.id != request.profile.id:
            raise ValueError('安装包与项目不匹配。')
        if bundle.image:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./:@_-]{0,511}', bundle.image):
                raise ValueError('安装包的镜像名称无效。')
            emit('拉取安装包指定的应用镜像。')
            self.ssh.run('docker pull ' + shlex.quote(bundle.image), timeout=1800)
            return bundle.image
        if bundle.payload is None or not Path(bundle.payload).is_file():
            raise ValueError('此安装包没有预构建镜像或本地源码归档。')
        payload = Path(bundle.payload)
        with payload.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if not bundle.sha256 or digest != bundle.sha256:
            raise ValueError('源码归档校验失败；拒绝上传。')
        with tarfile.open(payload) as archive:
            for item in archive:
                name = PurePosixPath(item.name)
                if name.is_absolute() or '..' in name.parts or not (item.isfile() or item.isdir()):
                    raise ValueError('源码归档包含不安全的路径或链接。')
        build = request.directory + '/.build-' + uuid.uuid4().hex
        self.ssh.mkdir(build)
        image = 'huiyang-installer/' + alias + ':' + digest[:16]
        emit('在服务器 Docker 内构建应用；电脑和服务器无需另装 Python/Node。')
        try:
            self.ssh.upload(payload, build + '/source.tar.gz')
            self.ssh.run('echo ' + shlex.quote(digest + '  ' + build + '/source.tar.gz') + ' | sha256sum -c -\n'
                         + 'tar --no-same-owner --no-same-permissions -xf ' + shlex.quote(build + '/source.tar.gz') + ' -C ' + shlex.quote(build)
                         + '\ndocker build -t ' + shlex.quote(image) + ' ' + shlex.quote(build), timeout=3600)
        finally:
            # This generated directory is below the validated, installer-owned root.
            self.ssh.run('rm -rf -- ' + shlex.quote(build))
        return image

    def _verify_public(self, request, manifest, emit):
        emit('验证公网 HTTPS 证书和网页访问，首次签发最多等待约两分钟。')
        code = '''import time, urllib.request, urllib.error
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
opener = urllib.request.build_opener(NoRedirect())
last = None
for attempt in range(12):
    try:
        try:
            response = opener.open(URL, timeout=6)
            status = response.status
            response.close()
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
        if not 200 <= status < 400:
            raise RuntimeError('public route returned HTTP ' + str(status))
        print('PUBLIC_HTTPS_OK')
        break
    except Exception as error:
        last = type(error).__name__
        if attempt == 11:
            raise RuntimeError('public HTTPS verification failed: ' + str(last))
        time.sleep(4)
'''.replace('URL', repr(request.url))
        try:
            output = self.ssh.run(self._compose(request.directory, manifest) + ' exec -T app python -c ' + shlex.quote(code), timeout=150)
            if 'PUBLIC_HTTPS_OK' not in output:
                raise RuntimeError('未收到可信 HTTPS 验证结果。')
        except Exception:
            raise PublicVerificationError('应用已启动，但公网 HTTPS 证书或网页验证未通过。已保留运行中的应用和网关；请检查域名解析、80/443 云防火墙与证书签发日志，再重试部署。') from None

    def deploy(self, request: DeployRequest, bundle: Bundle, emit) -> dict:
        with self._lock:
            directory = normalize_directory(request.directory)
            manifest = self._manifest(directory, request.profile.id, allow_new=True)
            safe_emit = lambda text: emit(redact(text, self._secrets))
            alias = _identity(request.profile.id, directory)
            self._begin()
            saved, gateway_saved, owner, backup, new = {}, {}, None, '', None
            changed_gateway = False
            app_changed = False
            try:
                # Recheck ownership under the shared lock before making any writes.
                manifest = self._manifest(directory, request.profile.id, allow_new=True)
                old_env = {}
                if manifest:
                    self._safe(directory + '/.env', file=True)
                    if self.ssh.kind(directory + '/.env') == 'file':
                        old_env = parse_env(self.ssh.read_file(directory + '/.env').decode('utf-8-sig'))
                    elif manifest.get('state') not in ('failed', 'installing'):
                        raise ValueError('现有安装缺少私有 .env；拒绝生成新凭据，请先恢复配置备份。')
                    if request.profile.requires_feishu and not old_env.get('POSTGRES_PASSWORD'):
                        data = directory + '/postgres_data'
                        self._safe(data)
                        if self.ssh.kind(data) == 'directory' and self.ssh.list_directory(data):
                            raise ValueError('已有 PostgreSQL 数据但缺少原数据库密码；请先恢复 .env，安装器不会更换凭据。')
                request = validate_deployment(request, old_env)
                private = environment(request, old_env)
                self._secrets.extend(v for k,v in private.items() if any(x in k for x in ('SECRET','PASSWORD','TOKEN','KEY')))
                if hasattr(self.ssh, 'secrets'): self.ssh.secrets = self._secrets
                self._ensure_docker(request.allow_install_docker, safe_emit)
                self._disk_space(directory, safe_emit)
                owner, gateway_saved = self._gateway(request, alias)
                if owner is not None:
                    self._gateway_ports('.owner.json' in gateway_saved)
                if request.https:
                    self._gateway_network()
                self.ssh.mkdir(directory)
                schema_before = self._schema(directory, manifest) if manifest else ''
                if manifest:
                    backup, saved = self._snapshot(directory, manifest, safe_emit)
                    database_backup = self._database_backup(directory, manifest, backup)
                    safe_emit('已完成一致性数据库备份，更新将保留现有数据。' if database_backup else '尚未发现已初始化的数据库；保留原数据目录，继续修复安装。')
                new = {'owner':OWNER,'schema':1,'profile':request.profile.id,'directory':directory,
                       'version':bundle.version,'image':'','url':request.url,'state':'installing',
                       'updated_at':datetime.now(timezone.utc).isoformat()}
                if not manifest:
                    self.ssh.write_file(directory + '/' + MANIFEST, json_bytes(new))
                    self.ssh.write_file(directory + '/.env', dotenv(private))
                image = self._image(request, bundle, alias, safe_emit)
                new['image'] = image
                if request.profile.id == 'team-todo':
                    self._safe(directory + '/data')
                    self.ssh.mkdir(directory + '/data')
                    self.ssh.run('chown 10001:10001 -- ' + shlex.quote(directory + '/data'))
                self.ssh.write_file(directory + '/.env', dotenv(private))
                self.ssh.write_file(directory + '/compose.yaml', json_bytes(compose_document(request, image, alias)))
                app_changed = True
                safe_emit('启动应用并等待容器健康检查。')
                self._health(directory, new)
                schema_after = self._schema(directory, new)
                if owner is not None:
                    changed_gateway = True
                    self._write_gateway(owner)
                    gateway = self._gateway_command()
                    self.ssh.run(gateway + ' run --rm --no-deps gateway caddy validate --config /etc/caddy/caddy.json', timeout=180)
                    self.ssh.run(gateway + ' up -d', timeout=180)
                    # Existing containers mount the directory so atomic file replacement is visible.
                    self.ssh.run(gateway + ' exec -T gateway caddy reload --config /etc/caddy/caddy.json', timeout=120)
                new.update(database_schema=schema_after)
                if manifest:
                    new['previous'] = {'image':manifest.get('image',''),'version':manifest.get('version',''),
                                       'schema_before':schema_before,'schema_after':schema_after}
                if request.https:
                    self._verify_public(request, new, safe_emit)
                new.update(state='healthy')
                self.ssh.write_file(directory + '/' + MANIFEST, json_bytes(new))
                message = '容器健康检查通过。'
                if request.https:
                    message += ' 公网 HTTPS 证书与页面验证通过。'
                if request.profile.requires_feishu:
                    message += ' 飞书 OAuth 回调：' + request.origin + '/api/team/callback；尚未验证飞书权限、真实账号或模型 API。'
                receipt = {k:new[k] for k in ('profile','directory','version','image','url','state','updated_at')}
                receipt.update(message=message, backup_path=backup)
                self.ssh.write_file(directory + '/installation-receipt.json', json_bytes(receipt))
                return receipt
            except Exception as error:
                if isinstance(error, PublicVerificationError) and new:
                    new.update(state='certificate_pending')
                    new.pop('url', None)
                    self.ssh.write_file(directory + '/' + MANIFEST, json_bytes(new))
                    raise RuntimeError(redact(str(error), self._secrets)) from None
                # Restore configuration only. Never restore a database or blindly run an old image.
                for name, content in saved.items():
                    try: self.ssh.write_file(directory + '/' + name, content)
                    except Exception: pass
                if manifest and app_changed:
                    # A migration may already have run. Stop the app rather than
                    # silently run old code against possibly newer data.
                    try: self.ssh.run(self._compose(directory, manifest) + ' stop app', timeout=120)
                    except Exception: pass
                    failed = dict(manifest, state='update_failed')
                    try: self.ssh.write_file(directory + '/' + MANIFEST, json_bytes(failed))
                    except Exception: pass
                if not manifest and new:
                    new.update(state='failed'); new.pop('url', None)
                    try: self.ssh.write_file(directory + '/' + MANIFEST, json_bytes(new))
                    except Exception: pass
                if changed_gateway:
                    try:
                        if gateway_saved:
                            for name, content in gateway_saved.items():
                                self.ssh.write_file(GATEWAY_ROOT + '/' + name, content)
                            self.ssh.run(self._gateway_command() + ' exec -T gateway caddy reload --config /etc/caddy/caddy.json')
                        else:
                            self.ssh.run(self._gateway_command() + ' down')
                            empty = {'owner':OWNER,'schema':1,'routes':[]}
                            self._write_gateway(empty)
                    except Exception:
                        safe_emit('网关恢复未完成，请检查服务器网关状态。')
                raise RuntimeError(redact(str(error), self._secrets) + ('；原配置已尝试恢复，数据库保持当前状态。若已更换应用，已尝试停止它以避免不安全降级；请检查状态后重新部署。' if manifest else '；部署未完成。')) from None
            finally:
                self._end()

    def maintain(self, action: str, directory: str, emit, profile_id: str | None = None) -> dict:
        if profile_id not in ('huiyang','team-todo'):
            raise ValueError('维护操作必须明确指定预期项目。')
        directory = normalize_directory(directory)
        with self._lock:
            manifest = self._manifest(directory, profile_id)
            if action not in ('status','logs','restart','backup','rollback','upgrade'):
                raise ValueError('不支持的维护操作。')
            if action == 'upgrade':
                raise ValueError('请在部署页选择当前安装目录，使用此安装包执行升级；升级前会自动备份。')
            self._begin()
            try:
                manifest = self._manifest(directory, profile_id)
                if self.ssh.kind(directory + '/.env') == 'file':
                    values = parse_env(self.ssh.read_file(directory + '/.env').decode())
                    self._secrets.extend(v for k,v in values.items() if any(x in k for x in ('SECRET','PASSWORD','TOKEN','KEY')))
                    if hasattr(self.ssh, 'secrets'): self.ssh.secrets = self._secrets
                compose = self._compose(directory, manifest)
                if action == 'status':
                    message = self.ssh.run(compose + ' ps --all --format json')
                    state = 'checked'
                elif action == 'logs':
                    message = self.ssh.run(compose + ' logs --no-color --tail 150', timeout=120)
                    state = 'logs'
                elif action == 'restart':
                    self.ssh.run(compose + ' restart', timeout=180)
                    self._health(directory, manifest)
                    message, state = '应用已重启并通过健康检查。', 'healthy'
                elif action == 'backup':
                    backup, _ = self._snapshot(directory, manifest, emit)
                    path = self._database_backup(directory, manifest, backup)
                    return {'state':'backed_up','backup_path':backup,'message':('数据库一致性备份完成：' + path) if path else '已备份现有配置；尚未发现已初始化的数据库。'}
                else:
                    previous = manifest.get('previous', {})
                    actual = self._schema(directory, manifest)
                    if (not previous.get('image') or not actual or not previous.get('schema_before')
                            or previous['schema_before'] != previous.get('schema_after') or actual != previous.get('schema_after')):
                        raise ValueError('没有可安全回滚的应用镜像，或数据库结构已改变/无法验证；拒绝降级。请使用兼容当前数据的修复版本。')
                    backup, saved = self._snapshot(directory, manifest, emit)
                    self._database_backup(directory, manifest, backup)
                    document = json.loads(self.ssh.read_file(directory + '/compose.yaml'))
                    document['services']['app']['image'] = previous['image']
                    self.ssh.write_file(directory + '/compose.yaml', json_bytes(document))
                    try:
                        self._health(directory, manifest)
                    except Exception:
                        self.ssh.write_file(directory + '/compose.yaml', saved['compose.yaml'])
                        raise
                    manifest.update(image=previous['image'],version=previous.get('version',''),state='healthy')
                    manifest.pop('previous',None)
                    self.ssh.write_file(directory + '/' + MANIFEST, json_bytes(manifest))
                    message, state = '应用镜像已安全回滚；数据库保留当前数据。', 'healthy'
                message = redact(message, self._secrets)
                emit(message)
                return {'state':state,'message':message,'directory':directory}
            except Exception as error:
                kind = ValueError if isinstance(error, ValueError) else RuntimeError
                raise kind(redact(str(error), self._secrets)) from None
            finally:
                self._end()


DOCKER_INSTALL = r'''
. /etc/os-release
case "$(uname -m)" in x86_64|aarch64) ;; *) echo '不支持此 CPU 架构。' >&2; exit 77;; esac
had_docker=0
if command -v docker >/dev/null 2>&1; then
  had_docker=1
  docker info >/dev/null 2>&1 || { echo '已有 Docker 不能运行，请先修复服务或权限；安装器不会重启它。' >&2; exit 77; }
fi
case "$ID" in
  ubuntu|debian)
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/huiyang-docker.asc
    chmod a+r /etc/apt/keyrings/huiyang-docker.asc
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/huiyang-docker.asc] https://download.docker.com/linux/%s %s stable\n' "$(dpkg --print-architecture)" "$ID" "$VERSION_CODENAME" > /etc/apt/sources.list.d/huiyang-docker.list
    apt-get update
    if [ "$had_docker" = 1 ]; then
      DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin
    else
      DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    fi
    ;;
  opencloudos|rocky|almalinux|centos)
    if command -v dnf >/dev/null 2>&1; then package=dnf; else package=yum; fi
    "$package" install -y ca-certificates curl
    curl -fsSL https://download.docker.com/linux/centos/docker-ce.repo -o /etc/yum.repos.d/huiyang-docker-ce.repo
    if [ "$had_docker" = 1 ]; then
      "$package" install -y docker-compose-plugin
    else
      "$package" install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    fi
    ;;
  *) echo '系统不受支持；不会运行未经支持的 Docker 安装脚本。' >&2; exit 77;;
esac
if [ "$had_docker" = 0 ]; then systemctl enable --now docker; fi
'''
