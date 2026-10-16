"""Real SSH framing and shell execution, restricted to loopback and temp files."""
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import threading

import paramiko
import pytest

from deployer.models import Connection
from deployer.ssh import RemoteCommandError, SSHTransport


def bash_executable():
    candidates = [
        Path('C:/Git/Git/bin/bash.exe'),
        Path('C:/Git/Git/usr/bin/bash.exe'),
        Path('C:/Program Files/Git/bin/bash.exe'),
    ]
    discovered = shutil.which('bash')
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    pytest.skip('A local Bash executable is required for the SSH integration test')


def shell_path(path):
    absolute = Path(path).resolve()
    if os.name == 'nt':
        return '/' + absolute.drive[0].lower() + absolute.as_posix()[2:]
    return str(absolute)


class LocalSSHServer(paramiko.ServerInterface):
    def __init__(self, owner):
        self.owner = owner
        self.requests = queue.Queue()

    def get_allowed_auths(self, username):
        return 'password,publickey'

    def check_auth_password(self, username, password):
        if username == 'root' and password == self.owner.password:
            self.owner.authentications.append('password')
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        if username == 'root' and key == self.owner.client_key:
            self.owner.authentications.append('publickey')
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        self.owner.commands.append(command.decode('utf-8'))
        self.requests.put(command)
        return True


class LoopbackShell:
    password = 'local-only-ssh-password-$not-a-command'

    def __init__(self, bash, directory):
        self.bash, self.directory = bash, directory
        self.host_key = paramiko.RSAKey.generate(2048)
        self.client_key = paramiko.RSAKey.generate(2048)
        self.commands, self.authentications, self.failures = [], [], []
        self.transports, self.workers = [], []
        self.stopped = threading.Event()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.port = self.listener.getsockname()[1]
        self.listener.listen(4)
        self.listener.settimeout(.1)
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        while not self.stopped.is_set():
            try:
                connection, address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            assert address[0] == '127.0.0.1'
            worker = threading.Thread(target=self._serve, args=(connection, self.host_key), daemon=True)
            self.workers.append(worker)
            worker.start()

    def _serve(self, connection, host_key):
        transport = paramiko.Transport(connection)
        self.transports.append(transport)
        transport.add_server_key(host_key)
        server = LocalSSHServer(self)
        try:
            transport.start_server(server=server)
            while transport.is_active() and not self.stopped.is_set():
                channel = transport.accept(.1)
                if channel is None:
                    continue
                command = server.requests.get(timeout=5)
                # The only platform shim is id -u: Windows cannot provide Linux
                # root, while all production script bytes run in the real shell.
                assert command == b'sh -s'
                channel.settimeout(5)
                script = bytearray()
                while chunk := channel.recv(65536):
                    script.extend(chunk)
                prelude = b"id() { if [ \"$#\" = 1 ] && [ \"$1\" = -u ]; then printf '0\\n'; else command id \"$@\"; fi; }\n"
                environment = dict(os.environ, LANG='C.UTF-8', LC_ALL='C.UTF-8')
                result = subprocess.run(
                    [self.bash, '--noprofile', '--norc', '-s'],
                    input=prelude + script, capture_output=True, timeout=15,
                    cwd=self.directory, env=environment,
                )
                if result.stdout:
                    channel.sendall(result.stdout)
                if result.stderr:
                    channel.sendall_stderr(result.stderr)
                channel.send_exit_status(result.returncode)
                channel.shutdown_write()
                channel.close()
        except (EOFError, ConnectionResetError, paramiko.SSHException):
            # Host-key rejection closes the real connection before any channel.
            if server.requests.qsize():
                self.failures.append('SSH disconnected with an unhandled command')
        except Exception as error:
            if not self.stopped.is_set():
                self.failures.append(repr(error))
        finally:
            transport.close()

    def connection(self, known_hosts, **authentication):
        return Connection('127.0.0.1', port=self.port, known_hosts_path=known_hosts, **authentication)

    def close(self):
        self.stopped.set()
        self.listener.close()
        for transport in self.transports:
            transport.close()
        self.thread.join(timeout=5)
        for worker in self.workers:
            worker.join(timeout=5)
        assert not self.thread.is_alive()
        assert not any(worker.is_alive() for worker in self.workers)
        assert not self.failures, self.failures


@pytest.fixture
def loopback_shell(tmp_path):
    server = LoopbackShell(bash_executable(), tmp_path)
    try:
        yield server
    finally:
        server.close()


def test_real_password_ssh_and_shell_preserve_private_file_bytes(loopback_shell, tmp_path):
    server = loopback_shell
    trusted = []
    known_hosts = tmp_path / 'known_hosts'
    client = SSHTransport(server.connection(known_hosts, password=server.password),
                          lambda host, fingerprint: trusted.append((host, fingerprint)) or True)
    try:
        client.connect()
        folder = tmp_path / "资料 spaces $HOME 'quoted' $(touch ESCAPED)"
        filename = folder / "private $value '秘密'.env"
        data = "API_KEY=private-${EXPAND}-'quoted'-中文\n".encode() + b'\x00binary\xff'
        client.mkdir(shell_path(folder))
        client.write_file(shell_path(filename), data)
        assert client.kind(shell_path(filename)) == 'file'
        assert client.read_file(shell_path(filename)) == data
        assert filename.read_bytes() == data
        assert (filename.name, 'file') in client.list_directory(shell_path(folder))
        assert not (tmp_path / 'ESCAPED').exists()
        assert not (folder / 'ESCAPED').exists()
        with pytest.raises(RemoteCommandError) as error:
            client.run("printf '%s\\n' '" + server.password + "' >&2\nexit 9")
        assert error.value.status == 9
        assert server.password not in str(error.value)
        assert '[REDACTED]' in str(error.value)
    finally:
        client.close()
    assert server.authentications == ['password']
    assert len(trusted) == 1 and trusted[0][1].startswith('SHA256:')
    saved = paramiko.HostKeys(str(known_hosts))
    assert saved.lookup(f'[127.0.0.1]:{server.port}')['ssh-rsa'] == server.host_key
    assert server.commands and set(server.commands) == {'sh -s'}
    assert all(server.password not in command and 'API_KEY' not in command for command in server.commands)


def test_real_ssh_accepts_encrypted_private_key(loopback_shell, tmp_path):
    server = loopback_shell
    key_path = tmp_path / "加密 private key 'local'.pem"
    passphrase = 'local-only-key-passphrase-$literal'
    server.client_key.write_private_key_file(str(key_path), password=passphrase)
    client = SSHTransport(server.connection(tmp_path / 'known_hosts', key_path=str(key_path), passphrase=passphrase),
                          lambda *_: True)
    try:
        client.connect()
        assert client.run("printf '%s' 'authenticated with encrypted key'") == 'authenticated with encrypted key'
    finally:
        client.close()
    assert server.authentications and set(server.authentications) == {'publickey'}
    assert set(server.commands) == {'sh -s'}
    assert all(passphrase not in command for command in server.commands)


def test_real_ssh_rejects_changed_saved_host_key_without_prompt(loopback_shell, tmp_path):
    server = loopback_shell
    known_hosts = tmp_path / 'known_hosts'
    prompts = []
    first = SSHTransport(server.connection(known_hosts, password=server.password),
                         lambda *_: prompts.append('accepted') or True)
    first.connect()
    first.close()
    original_store = known_hosts.read_bytes()
    server.host_key = paramiko.RSAKey.generate(2048)
    changed = SSHTransport(server.connection(known_hosts, password=server.password),
                           lambda *_: prompts.append('unexpected new trust prompt') or True)
    try:
        with pytest.raises(paramiko.SSHException, match='主机密钥已改变'):
            changed.connect()
    finally:
        changed.close()
    assert prompts == ['accepted']
    assert known_hosts.read_bytes() == original_store
    assert server.authentications == ['password']
