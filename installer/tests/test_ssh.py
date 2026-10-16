import base64
import hashlib

import paramiko
import pytest

from deployer.ssh import TrustPolicy, RemoteCommandError, SSHTransport
from deployer.models import Connection


def test_unknown_host_requires_explicit_acceptance_and_persists_only_public_key(tmp_path):
    key = paramiko.RSAKey.generate(1024)
    seen = []
    known = tmp_path / 'known_hosts'
    client = paramiko.SSHClient()
    policy = TrustPolicy(known, lambda host, fp: seen.append((host, fp)) or False)
    with pytest.raises(paramiko.SSHException): policy.missing_host_key(client, 'example.com', key)
    assert not known.exists()
    policy = TrustPolicy(known, lambda host, fp: seen.append((host, fp)) or True)
    policy.missing_host_key(client, 'example.com', key)
    assert seen[-1] == ('example.com', 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('='))
    assert paramiko.HostKeys(str(known)).lookup('example.com')['ssh-rsa'] == key


def test_changed_saved_host_key_cannot_be_accepted_again(tmp_path):
    first, changed = paramiko.RSAKey.generate(1024), paramiko.RSAKey.generate(1024)
    known = tmp_path / 'known_hosts'
    keys = paramiko.HostKeys(); keys.add('example.com','ssh-rsa',first); keys.save(str(known))
    called = []
    with pytest.raises(paramiko.SSHException):
        TrustPolicy(known, lambda *_: called.append(True) or True).missing_host_key(paramiko.SSHClient(), 'example.com', changed)
    assert called == []


def test_remote_errors_redact_secrets():
    error = RemoteCommandError(1, 'bad ssh-secret\nLLM_API_KEY=unknown', ['ssh-secret'])
    assert 'ssh-secret' not in str(error)
    assert 'unknown' not in str(error)


class Channel:
    def __init__(self): self.result = b''; self.command = ''; self.payload = b''
    def settimeout(self, _): pass
    def exec_command(self, command): self.command = command
    def sendall(self, payload):
        self.payload = payload
        # Model a NOPASSWD sudo: it consumes no credential from stdin. A raw
        # password would become the first shell command and fail.
        if payload.startswith(b'password-not-a-command\n'):
            if 'while IFS= read -r' in self.command:
                self.result = b'0\n'
            else:
                self.result = b'password-not-a-command: command not found\n'
        else: self.result = b'0\n'
    def shutdown_write(self): pass
    def recv_ready(self): return bool(self.result)
    def recv(self, _): result, self.result = self.result, b''; return result
    def recv_stderr_ready(self): return False
    def recv_stderr(self, _): return b''
    def exit_status_ready(self): return True
    def recv_exit_status(self): return 0
    def close(self): pass


class Client:
    def __init__(self): self.channel = Channel()
    def get_transport(self): return self
    def is_active(self): return True
    def open_session(self, timeout): return self.channel


def test_sudo_password_cannot_be_executed_if_sudo_stops_consuming_password():
    transport = SSHTransport(Connection('example.com', user='deploy', password='ssh', sudo_password='password-not-a-command'), lambda *_:False)
    transport.client = Client()
    transport._sudo_password_required = True
    assert transport.run('id -u').strip() == '0'
    assert 'password-not-a-command' not in transport.client.channel.command


def test_supplied_sudo_password_is_not_sent_for_nopasswd_policy():
    transport = SSHTransport(Connection('example.com', user='deploy', password='ssh', sudo_password='password-not-a-command'), lambda *_:False)
    transport.client = Client()
    assert transport.run('id -u').strip() == '0'
    assert b'password-not-a-command' not in transport.client.channel.payload
