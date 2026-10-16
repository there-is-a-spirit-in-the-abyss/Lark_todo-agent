import json
import csv
import shlex
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from deployer.models import Bundle, Connection, DeployRequest, PROFILES
from deployer.remote import RemoteSession, check_manifest
from deployer.templates import compose_document, environment, gateway_document
from deployer.config import parse_env
from deployer.templates import dotenv


def test_wrong_project_or_moved_manifest_cannot_be_adopted():
    manifest = {'owner': 'huiyang-installer', 'schema': 1, 'profile': 'huiyang', 'directory': '/huiyang'}
    check_manifest(manifest, '/huiyang', 'huiyang')
    with pytest.raises(ValueError):
        check_manifest(manifest, '/huiyang', 'team-todo')
    with pytest.raises(ValueError):
        check_manifest(manifest, '/other', 'huiyang')


def test_update_preserves_database_password_and_existing_private_values():
    request = DeployRequest(PROFILES['huiyang'], '/huiyang', 'example.com', values={'LLM_MODEL': 'new'})
    result = environment(request, {'POSTGRES_PASSWORD': 'keep-db', 'FEISHU_APP_SECRET': 'keep-secret', 'LLM_MODEL': 'old'})
    assert result['POSTGRES_PASSWORD'] == 'keep-db'
    assert result['FEISHU_APP_SECRET'] == 'keep-secret'
    assert result['LLM_MODEL'] == 'new'
    assert result['TEAM_PUBLIC_URL'] == 'https://example.com'


def test_compose_uses_persistent_data_and_does_not_publish_https_app_port():
    request = DeployRequest(PROFILES['huiyang'], '/资料/a $x', 'example.com')
    compose = compose_document(request, 'registry/app@sha256:' + 'a' * 64, 'hy_test')
    assert 'ports' not in compose['services']['app']
    assert compose['services']['db']['volumes'] == ['./postgres_data:/var/lib/postgresql/data']
    assert compose['networks']['gateway']['external'] is True
    assert compose['services']['app']['networks']['gateway']['aliases'] == ['hy_test']
    todo = compose_document(DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False, port=8088), 'app:test', 'td_test')
    assert todo['services']['app']['ports'] == ['8088:8000']
    assert todo['services']['app']['volumes'] == ['./data:/app/data']


def test_shared_gateway_container_carries_installer_ownership_label():
    from deployer.templates import gateway_compose
    assert gateway_compose()['services']['gateway']['labels']['io.huiyang.installer.owner'] == 'huiyang-installer'


def test_shared_gateway_preserves_both_projects_and_explicit_public_ip_acme():
    routes = [{'host':'203.0.113.1', 'profile':'huiyang', 'alias':'hy_one', 'directory':'/huiyang'},
              {'host':'203.0.113.1', 'profile':'team-todo', 'alias':'td_two', 'directory':'/todo'}]
    doc = gateway_document(routes)
    routes = doc['apps']['http']['servers']['public']['routes'][0]['handle'][0]['routes']
    assert routes[0]['match'] == [{'path': ['/team', '/team/*', '/api/team', '/api/team/*']}]
    assert routes[0]['handle'][0]['upstreams'] == [{'dial':'hy_one:8000'}]
    assert routes[1]['handle'][0]['upstreams'] == [{'dial':'td_two:8000'}]
    issuer = doc['apps']['tls']['automation']['policies'][0]['issuers'][0]
    assert issuer['module'] == 'acme'
    assert issuer['profile'] == 'shortlived'


class MemoryTransport:
    """Privileged remote filesystem/command boundary; never opens a socket."""
    def __init__(self, tmp_path):
        self.base = tmp_path
        self.base.mkdir(parents=True, exist_ok=True)  # Linux remote / always exists.
        self.commands = []
        self.fail_health = False
        self.symlinks = set()
        self.schema = 'schema-1'
        self.public_https = True
        self.app_running = True
        self.fail_build = False
        self.fail_upload = False
        self.on_lock = None
        self.stopped_gateway = False
        self.disk_mb = (4096, 8192)
    def local(self, path):
        return self.base / path.lstrip('/')
    def kind(self, path):
        if path in self.symlinks: return 'symlink'
        p = self.local(path)
        if p.is_symlink(): return 'symlink'
        if p.is_dir(): return 'directory'
        if p.is_file(): return 'file'
        return 'missing'
    def list_directory(self, path):
        return [(p.name, 'symlink' if p.is_symlink() else 'directory' if p.is_dir() else 'file') for p in self.local(path).iterdir()]
    def mkdir(self, path): self.local(path).mkdir(parents=True, exist_ok=True)
    def read_file(self, path, limit=1048576): return self.local(path).read_bytes()[:limit+1]
    def write_file(self, path, data, mode=0o600):
        p = self.local(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    def upload(self, source, path):
        if self.fail_upload: raise RuntimeError('upload disconnected')
        self.write_file(path, Path(source).read_bytes())
    def run(self, script, timeout=120):
        self.commands.append(script)
        if 'if ! mkdir -- /var/lib/huiyang-installer-operation-lock' in script and self.on_lock:
            callback, self.on_lock = self.on_lock, None
            callback()
        if 'DockerRootDir' in script: return '\n'.join(map(str,self.disk_mb))
        if script.startswith('docker ps -aq'):
            return 'abcdef123456' if self.stopped_gateway else ''
        if 'docker build' in script and self.fail_build: raise RuntimeError('Docker build failed')
        if ' exec -T app ' in script and not self.app_running:
            raise RuntimeError('service app is not running')
        if 'docker run --rm' in script and 'sqlite3' in script:
            # Execute the real helper's Python against local SQLite files. Only
            # the Docker bind-mount transport is substituted.
            args = shlex.split(script)
            mounts = {}
            for index, value in enumerate(args):
                if value == '--mount':
                    parts = dict(field.split('=',1) for field in next(csv.reader([args[index+1]])))
                    mounts[parts['dst']] = self.local(parts['src'])
            start = args.index('-c')
            mapped = []
            for argument in args[start+2:]:
                for prefix, target in mounts.items():
                    if argument.startswith(prefix + '/'):
                        argument = str(target / argument[len(prefix)+1:]); break
                mapped.append(argument)
            result = subprocess.run([sys.executable, '-c', args[start+1], *mapped], capture_output=True, text=True)
            if result.returncode: raise RuntimeError(result.stderr)
            return result.stdout
        if 'docker info' in script: return '24.0\n2.24\n'
        if 'sqlite_master' in script or 'SELECT version_num' in script: return self.schema
        if 'PUBLIC_HTTPS_OK' in script:
            if not self.public_https: raise RuntimeError('certificate not trusted')
            return 'PUBLIC_HTTPS_OK'
        if 'docker compose' in script and 'ps --format json' in script:
            if self.fail_health: raise RuntimeError('health failed API_KEY=leak')
            return '[{"Service":"app","State":"running","Health":"healthy"}]'
        if 'ss -H' in script: return ''
        if ' stop app' in script: self.app_running = False
        if ' up -d --wait' in script and script.rstrip().endswith('240'): self.app_running = True
        return ''
    def close(self): pass


def session_at(tmp_path):
    session = RemoteSession(Connection('example.com', password='ssh-secret'), lambda *_: False)
    session.ssh = MemoryTransport(tmp_path)
    return session


def test_unmanaged_nonempty_directory_and_symlink_ancestor_are_refused(tmp_path):
    s = session_at(tmp_path)
    s.ssh.mkdir('/todo'); s.ssh.write_file('/todo/private.txt', b'keep')
    with pytest.raises(ValueError):
        s.deploy(DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False), Bundle(PROFILES['team-todo'], image='app:v1'), lambda _:None)
    assert s.ssh.read_file('/todo/private.txt') == b'keep'
    # Windows may forbid creating native symlinks; the remote transport returns
    # Linux lstat kinds, so exercise that boundary explicitly.
    s.ssh.symlinks.add('/link')
    with pytest.raises(ValueError): s.mkdir('/link/new')


def test_deploy_receipt_has_no_secrets_and_failed_update_restores_configuration(tmp_path):
    s = session_at(tmp_path)
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False)
    receipt = s.deploy(req, Bundle(req.profile, version='v1', image='app:v1'), lambda _:None)
    assert receipt['url'] == 'http://example.com:8080/'
    assert receipt['state'] == 'healthy'
    assert 'ssh-secret' not in json.dumps(receipt)
    old = s.ssh.read_file('/todo/compose.yaml')
    s.ssh.fail_health = True
    with pytest.raises(RuntimeError):
        s.deploy(req, Bundle(req.profile, version='v2', image='app:v2'), lambda _:None)
    assert s.ssh.read_file('/todo/compose.yaml') == old
    restored = json.loads(s.ssh.read_file('/todo/.huiyang-installer.json'))
    assert restored['version'] == 'v1'
    assert restored['state'] == 'update_failed'


def test_maintenance_requires_expected_identity_and_refuses_schema_downgrade(tmp_path):
    s = session_at(tmp_path)
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False)
    s.deploy(req, Bundle(req.profile, version='v1', image='app:v1'), lambda _:None)
    with pytest.raises(ValueError): s.maintain('status', '/todo', lambda _:None, profile_id='huiyang')
    with pytest.raises(ValueError): s.maintain('rollback', '/todo', lambda _:None, profile_id='team-todo')


def test_remote_env_import_does_not_include_database_or_other_secrets(tmp_path):
    s = session_at(tmp_path)
    s.ssh.mkdir('/chosen')
    s.ssh.write_file('/chosen/.env', b'FEISHU_APP_ID=app\nFEISHU_APP_SECRET=selected\nPOSTGRES_PASSWORD=private\nAWS_SECRET_ACCESS_KEY=other\n')
    assert s.read_env('/chosen/.env') == {'FEISHU_APP_ID':'app', 'FEISHU_APP_SECRET':'selected'}


def test_private_env_round_trip_preserves_shell_metacharacters_without_execution():
    values = {'FEISHU_APP_SECRET': "x' $HOME ${ATTACK} `id` \\ z", 'LLM_API_KEY':'key"quoted'}
    assert parse_env(dotenv(values).decode()) == values


def test_https_second_project_keeps_first_route_and_rejects_same_route_takeover(tmp_path):
    s = session_at(tmp_path)
    one = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com')
    s.deploy(one, Bundle(one.profile, image='app:v1'), lambda _:None)
    hy = DeployRequest(PROFILES['huiyang'], '/huiyang', 'example.com', values={
        'FEISHU_APP_ID':'app', 'FEISHU_APP_SECRET':'feishu-private', 'LLM_API_BASE_URL':'https://llm.example.com/v1',
        'LLM_API_KEY':'model-private', 'LLM_MODEL':'model'})
    s.deploy(hy, Bundle(hy.profile, image='hy:v1'), lambda _:None)
    saved = s.ssh.read_file('/var/lib/huiyang-installer/.owner.json')
    routes = json.loads(saved)['routes']
    assert {(r['profile'],r['directory']) for r in routes} == {('team-todo','/todo'),('huiyang','/huiyang')}
    two = DeployRequest(PROFILES['team-todo'], '/other-todo', 'example.com')
    with pytest.raises(RuntimeError): s.deploy(two, Bundle(two.profile, image='app:v1'), lambda _:None)
    assert s.ssh.read_file('/var/lib/huiyang-installer/.owner.json') == saved


def test_rollback_keeps_current_data_and_rejects_database_changed_after_update(tmp_path):
    s = session_at(tmp_path)
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False)
    s.deploy(req, Bundle(req.profile, version='v1', image='app:v1'), lambda _:None)
    with sqlite3.connect(s.ssh.local('/todo/data/team-todo.db')) as db:
        db.execute('CREATE TABLE tasks(title TEXT)')
        db.execute("INSERT INTO tasks VALUES ('latest-user-data')")
    current_data = s.ssh.read_file('/todo/data/team-todo.db')
    s.deploy(req, Bundle(req.profile, version='v2', image='app:v2'), lambda _:None)
    s.ssh.schema = 'schema-2'
    with pytest.raises(ValueError): s.maintain('rollback','/todo',lambda _:None,profile_id='team-todo')
    s.ssh.schema = 'schema-1'
    receipt = s.maintain('rollback','/todo',lambda _:None,profile_id='team-todo')
    assert receipt['state'] == 'healthy'
    assert json.loads(s.ssh.read_file('/todo/compose.yaml'))['services']['app']['image'] == 'app:v1'
    assert s.ssh.read_file('/todo/data/team-todo.db') == current_data


def test_failed_initial_deployment_leaves_no_success_receipt(tmp_path):
    s = session_at(tmp_path)
    s.ssh.fail_health = True
    req = DeployRequest(PROFILES['team-todo'], "/todo's $(touch PWN)", 'example.com', https=False)
    messages = []
    with pytest.raises(RuntimeError) as exc:
        s.deploy(req, Bundle(req.profile, image='app:v1'), messages.append)
    assert 'leak' not in str(exc.value)
    manifest = json.loads(s.ssh.read_file(req.directory + '/.huiyang-installer.json'))
    assert manifest['state'] == 'failed'
    assert 'url' not in manifest
    assert s.ssh.kind(req.directory + '/installation-receipt.json') == 'missing'


def test_source_bundle_rejects_traversal_before_upload(tmp_path):
    import hashlib
    import io
    payload = tmp_path / 'source.tar.gz'
    with tarfile.open(payload, 'w:gz') as archive:
        info = tarfile.TarInfo('../escape'); info.size = 1
        archive.addfile(info, io.BytesIO(b'x'))
    s = session_at(tmp_path / 'server')
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False)
    bundle = Bundle(req.profile, payload=payload, sha256=hashlib.sha256(payload.read_bytes()).hexdigest())
    with pytest.raises(RuntimeError): s.deploy(req,bundle,lambda _:None)
    assert not any('docker build' in c for c in s.ssh.commands)


def test_unverified_public_certificate_keeps_partial_install_without_success_url(tmp_path):
    s = session_at(tmp_path)
    s.ssh.public_https = False
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com')
    with pytest.raises(RuntimeError): s.deploy(req,Bundle(req.profile,image='app:v1'),lambda _:None)
    manifest = json.loads(s.ssh.read_file('/todo/.huiyang-installer.json'))
    assert manifest['state'] == 'certificate_pending'
    assert 'url' not in manifest
    assert s.ssh.kind('/todo/installation-receipt.json') == 'missing'
    assert json.loads(s.ssh.read_file('/var/lib/huiyang-installer/.owner.json'))['routes'][0]['directory'] == '/todo'


def test_stopped_todo_retry_preserves_committed_wal_data_in_consistent_backup(tmp_path):
    s = session_at(tmp_path)
    req = DeployRequest(PROFILES['team-todo'], "/todo's $data,archive", 'example.com', https=False)
    s.deploy(req, Bundle(req.profile, version='v1', image='app:v1'), lambda _:None)
    db = sqlite3.connect(s.ssh.local(req.directory + '/data/team-todo.db'))
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute('CREATE TABLE tasks(title TEXT)')
        db.execute("INSERT INTO tasks VALUES ('committed WAL task')")
        db.commit()
        s.ssh.app_running = False
        receipt = s.deploy(req, Bundle(req.profile, version='v2', image='app:v2'), lambda _:None)
        assert receipt['state'] == 'healthy'
        with sqlite3.connect(s.ssh.local(receipt['backup_path'] + '/database.sqlite')) as copy:
            assert copy.execute('SELECT title FROM tasks').fetchall() == [('committed WAL task',)]
        assert db.execute('SELECT title FROM tasks').fetchall() == [('committed WAL task',)]
    finally:
        db.close()


def test_failed_uninitialized_todo_can_retry_without_database_or_env(tmp_path):
    s = session_at(tmp_path)
    s.ssh.mkdir('/todo')
    s.ssh.write_file('/todo/.huiyang-installer.json', json.dumps({
        'owner':'huiyang-installer','schema':1,'profile':'team-todo','directory':'/todo','state':'failed','version':'local','image':''}).encode())
    s.ssh.app_running = False
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False)
    receipt = s.deploy(req, Bundle(req.profile,image='app:v1'),lambda _:None)
    assert receipt['state'] == 'healthy'
    assert s.ssh.kind(receipt['backup_path'] + '/database.sqlite') == 'missing'


@pytest.mark.parametrize('failure', ['fail_build','fail_upload'])
def test_source_failure_is_marked_owned_and_retryable(tmp_path, failure):
    import hashlib
    import io
    payload = tmp_path / 'source.tar.gz'
    with tarfile.open(payload,'w:gz') as archive:
        info = tarfile.TarInfo('Dockerfile'); info.size = 12
        archive.addfile(info, io.BytesIO(b'FROM scratch'))
    s = session_at(tmp_path / 'server')
    setattr(s.ssh, failure, True)
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False)
    bundle = Bundle(req.profile,payload=payload,sha256=hashlib.sha256(payload.read_bytes()).hexdigest())
    with pytest.raises(RuntimeError): s.deploy(req,bundle,lambda _:None)
    assert json.loads(s.ssh.read_file('/todo/.huiyang-installer.json'))['state'] == 'failed'
    setattr(s.ssh,failure,False)
    s.ssh.app_running = False
    assert s.deploy(req,bundle,lambda _:None)['state'] == 'healthy'


def test_update_reads_credentials_after_acquiring_server_lock(tmp_path):
    s = session_at(tmp_path)
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com', https=False)
    s.deploy(req,Bundle(req.profile,image='app:v1'),lambda _:None)
    # Another installer finishes an update immediately before this one acquires
    # the server lock. Empty wizard fields must preserve its latest credentials.
    s.ssh.on_lock = lambda: s.ssh.write_file('/todo/.env',b'PRIVATE_SECRET="new-concurrent-secret"\n')
    s.deploy(req,Bundle(req.profile,image='app:v2'),lambda _:None)
    assert parse_env(s.ssh.read_file('/todo/.env').decode())['PRIVATE_SECRET'] == 'new-concurrent-secret'


def test_stopped_unrelated_gateway_container_is_never_adopted(tmp_path):
    s = session_at(tmp_path)
    s.ssh.stopped_gateway = True
    req = DeployRequest(PROFILES['team-todo'], '/todo', 'example.com')
    with pytest.raises(RuntimeError): s.deploy(req,Bundle(req.profile,image='app:v1'),lambda _:None)
    assert s.ssh.kind('/var/lib/huiyang-installer/.owner.json') == 'missing'


def test_selected_filesystem_and_docker_data_space_checked_before_target_mutation(tmp_path):
    s = session_at(tmp_path)
    s.ssh.disk_mb = (100,8192)
    req = DeployRequest(PROFILES['team-todo'], '/different-filesystem/todo', 'example.com', https=False)
    with pytest.raises(RuntimeError): s.deploy(req,Bundle(req.profile,image='app:v1'),lambda _:None)
    assert s.ssh.kind(req.directory) == 'missing'
    s.ssh.disk_mb = (4096,100)
    with pytest.raises(RuntimeError): s.deploy(req,Bundle(req.profile,image='app:v1'),lambda _:None)
    assert s.ssh.kind(req.directory) == 'missing'


def test_huiyang_repair_backup_starts_database_service_without_old_app(tmp_path):
    s = session_at(tmp_path)
    req = DeployRequest(PROFILES['huiyang'], '/huiyang', 'example.com', values={
        'FEISHU_APP_ID':'app', 'FEISHU_APP_SECRET':'secret', 'LLM_API_BASE_URL':'https://model.example/v1',
        'LLM_API_KEY':'key', 'LLM_MODEL':'model'})
    s.deploy(req,Bundle(req.profile,image='app:v1'),lambda _:None)
    s.ssh.mkdir('/huiyang/postgres_data')
    s.ssh.write_file('/huiyang/postgres_data/PG_VERSION', b'16')
    s.ssh.app_running = False
    s.ssh.commands.clear()
    receipt = s.maintain('backup','/huiyang',lambda _:None,profile_id='huiyang')
    assert receipt['state'] == 'backed_up'
    # Starting the database must not invoke the old app's migrations.
    assert s.ssh.app_running is False
    assert any(command.rstrip().endswith('up -d --wait --wait-timeout 120 db') for command in s.ssh.commands)
