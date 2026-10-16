"""SSH transport. Commands and private file contents travel only on SSH stdin."""
from __future__ import annotations

import base64
import hashlib
import os
import shlex
import time
import uuid
from pathlib import Path

import paramiko

from .config import redact, validate_connection
from .models import Connection


class RemoteCommandError(RuntimeError):
    def __init__(self, status: int, output: str, secrets=()):
        self.status = status
        super().__init__(redact(f'服务器命令失败 ({status})：{output[-6000:]}', secrets))


class TrustPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, known_hosts: Path, callback):
        self.known_hosts = Path(known_hosts)
        self.callback = callback

    def missing_host_key(self, client, hostname, key):
        saved = paramiko.HostKeys()
        if self.known_hosts.exists():
            saved.load(str(self.known_hosts))
        # A previously trusted host must never be prompted as a new identity,
        # including when the server changes its key algorithm.
        if saved.lookup(hostname):
            raise paramiko.SSHException('服务器主机密钥已改变，请先通过独立渠道核实；安装器拒绝连接。')
        fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        if not self.callback(hostname, fingerprint):
            raise paramiko.SSHException('未接受服务器主机密钥。')
        saved.add(hostname, key.get_name(), key)
        self.known_hosts.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.known_hosts.with_name(self.known_hosts.name + '.' + uuid.uuid4().hex)
        try:
            saved.save(str(temporary))
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.known_hosts)
        finally:
            temporary.unlink(missing_ok=True)
        client.get_host_keys().add(hostname, key.get_name(), key)


class SSHTransport:
    def __init__(self, connection: Connection, trust_callback):
        self.connection = connection
        self.trust_callback = trust_callback
        self.client = None
        self.secrets = [connection.password, connection.passphrase, connection.sudo_password]
        self._sudo_password_required = False

    def connect(self):
        c = validate_connection(self.connection)
        self.connection = c
        known = c.known_hosts_path or Path.home() / '.huiyang-installer' / 'known_hosts'
        client = paramiko.SSHClient()
        # Keep a dedicated public-key trust store. Do not silently trust system keys.
        if Path(known).exists():
            client.load_host_keys(str(known))
        client.set_missing_host_key_policy(TrustPolicy(Path(known), self.trust_callback))
        try:
            client.connect(c.host, port=c.port, username=c.user,
                           password=c.password or None, key_filename=c.key_path or None,
                           passphrase=c.passphrase or None, look_for_keys=False,
                           allow_agent=False, timeout=20, auth_timeout=30, banner_timeout=30)
        except paramiko.BadHostKeyException:
            client.close()
            raise paramiko.SSHException('服务器主机密钥已改变；拒绝连接，请通过独立渠道核实。') from None
        except Exception:
            client.close()
            raise
        self.client = client
        try:
            identity = self.run('id -u', timeout=30).strip()
        except RemoteCommandError:
            if c.user == 'root' or not c.sudo_password:
                self.close()
                raise RuntimeError('需要 root 或可用的 sudo；请填写 sudo 密码后重试。') from None
            if '\n' in c.sudo_password or '\r' in c.sudo_password:
                self.close()
                raise ValueError('sudo 密码不能包含换行。')
            self._sudo_password_required = True
            identity = self.run('id -u', timeout=30).strip()
        if identity != '0':
            self.close()
            raise RuntimeError('sudo 未获得 root 权限，拒绝部署。')

    def run(self, script: str, timeout: int = 120) -> str:
        if self.client is None:
            raise RuntimeError('SSH 尚未连接。')
        c = self.connection
        command = 'sh -s'
        prefix = ''
        if c.user != 'root':
            command = 'sudo -n -- sh -s'
            if self._sudo_password_required:
                marker = 'huiyang-stdin-' + uuid.uuid4().hex
                # sudo may stop consuming a password after policy/cache changes.
                # Discard stdin until a random delimiter before interpreting a
                # script, so no credential line can ever become a shell command.
                bootstrap = 'while IFS= read -r line; do [ "$line" = ' + shlex.quote(marker) + ' ] && exec sh -s; done; exit 78'
                command = "sudo -S -p '' -- sh -c " + shlex.quote(bootstrap)
                prefix = c.sudo_password + '\n' + marker + '\n'
        transport = self.client.get_transport()
        if transport is None or not transport.is_active():
            raise RuntimeError('SSH 连接已断开。')
        channel = transport.open_session(timeout=30)
        channel.settimeout(30)
        output = bytearray()
        started = time.monotonic()
        try:
            channel.exec_command(command)
            # The command is a fixed string. Paths, scripts and secrets never enter argv.
            channel.sendall((prefix + 'set -eu\numask 077\n' + script + '\n').encode('utf-8'))
            channel.shutdown_write()
            while True:
                for ready, receive in ((channel.recv_ready, channel.recv), (channel.recv_stderr_ready, channel.recv_stderr)):
                    while ready():
                        part = receive(65536)
                        if len(output) < 8_388_608:
                            output.extend(part[:8_388_608 - len(output)])
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if time.monotonic() - started > timeout:
                    raise TimeoutError('服务器操作超时，请使用状态检查确认实际结果。')
                time.sleep(0.03)
            text = output.decode('utf-8', 'replace')
            status = channel.recv_exit_status()
            if status:
                raise RemoteCommandError(status, text, self.secrets)
            return text
        finally:
            channel.close()

    def kind(self, path: str) -> str:
        q = shlex.quote(path)
        return self.run(f'if [ -L {q} ]; then echo symlink; elif [ -d {q} ]; then echo directory; elif [ -f {q} ]; then echo file; elif [ -e {q} ]; then echo other; else echo missing; fi').strip()

    def list_directory(self, path: str) -> list[tuple[str, str]]:
        # NUL delimiters preserve spaces, Unicode, quotes and newlines in filenames.
        raw = self.run(f'find {shlex.quote(path)} -mindepth 1 -maxdepth 1 -printf "%f\\0%y\\0"')
        fields = raw.split('\x00')
        return [(fields[i], {'d':'directory', 'l':'symlink', 'f':'file'}.get(fields[i+1], 'other')) for i in range(0, len(fields)-1, 2)]

    def mkdir(self, path: str):
        q = shlex.quote(path)
        self.run(f'if [ ! -d {q} ]; then mkdir -p -m 700 -- {q}; fi')

    def read_file(self, path: str, limit: int = 1_048_576) -> bytes:
        q = shlex.quote(path)
        raw = self.run(f'[ -f {q} ] && [ ! -L {q} ] || {{ echo "文件不存在或不是普通文件" >&2; exit 74; }}\nsize=$(wc -c < {q})\n[ "$size" -le {int(limit)} ] || {{ echo "文件超过读取限制" >&2; exit 74; }}\nbase64 -- {q}')
        result = base64.b64decode(raw)
        if len(result) > limit:
            raise ValueError('服务器文件过大，无法读取。')
        return result

    def write_file(self, path: str, data: bytes, mode: int = 0o600):
        q = shlex.quote(path)
        temp = shlex.quote(path + '.tmp-' + uuid.uuid4().hex)
        encoded = base64.b64encode(data).decode()
        self.run(f"[ ! -L {q} ] || exit 73\nprintf '%s' '{encoded}' | base64 -d > {temp}\nchmod {mode:o} -- {temp}\nmv -f -- {temp} {q}")

    def upload(self, source: Path, path: str):
        if self.client is None:
            raise RuntimeError('SSH 尚未连接。')
        temporary = '/tmp/huiyang-upload-' + uuid.uuid4().hex
        sftp = self.client.open_sftp()
        try:
            with sftp.open(temporary, 'wx') as target, Path(source).open('rb') as origin:
                sftp.chmod(temporary, 0o600)
                while chunk := origin.read(1_048_576):
                    target.write(chunk)
            self.run(f'[ ! -L {shlex.quote(path)} ] || exit 73\ncp -- {shlex.quote(temporary)} {shlex.quote(path)}\nchmod 600 -- {shlex.quote(path)}')
        finally:
            try:
                sftp.remove(temporary)
            finally:
                sftp.close()

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None
