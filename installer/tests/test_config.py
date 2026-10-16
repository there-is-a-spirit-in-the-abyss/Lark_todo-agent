import pytest

from deployer.models import Connection, DeployRequest, get_profile
from deployer.config import import_env, normalize_directory, redact, validate_connection, validate_deployment


@pytest.mark.parametrize('value', ['/', '/etc', '/root', '/var/lib', '/var/lib/huiyang-installer', '/var/lib/huiyang-installer-operation-lock', '/var/lib/huiyang-installer-operation-lock/app', 'relative/app', '/opt/../etc/app', '/opt/app\nnext', '/opt/app\x00'])
def test_dangerous_install_destinations_are_rejected(value):
    with pytest.raises(ValueError):
        normalize_directory(value)


def test_custom_directory_keeps_spaces_unicode_and_literal_shell_characters():
    assert normalize_directory("/opt/团队's $board/") == "/opt/团队's $board"


def test_import_is_allowlisted_does_not_expand_variables_and_keeps_secret_hashes():
    values = import_env('export FEISHU_APP_ID=cli_example\nFEISHU_APP_SECRET="secret # value"\nLLM_API_KEY=abc#def\nLLM_MODEL=${OTHER}\nPATH=/malicious\nPOSTGRES_PASSWORD=old-db-password\n')
    assert values == {'FEISHU_APP_ID':'cli_example', 'FEISHU_APP_SECRET':'secret # value', 'LLM_API_KEY':'abc#def', 'LLM_MODEL':'${OTHER}'}


def test_import_does_not_execute_command_substitution(tmp_path):
    target = tmp_path / 'executed'
    values = import_env(f'LLM_API_KEY=$(touch {target})')
    assert values['LLM_API_KEY'] == f'$(touch {target})'
    assert not target.exists()


def test_secret_values_are_absent_from_repr_and_logs():
    connection = Connection(host='server.example', password='test-secret-password', passphrase='test-secret-phrase', sudo_password='test-sudo')
    request = DeployRequest(get_profile('huiyang'), '/huiyang', 'server.example', values={'FEISHU_APP_SECRET':'secret-feishu', 'LLM_API_KEY':'secret-model'})
    assert 'test-secret' not in repr(connection)
    assert 'secret-feishu' not in repr(request)
    assert redact('secret-feishu / secret-model / test-secret-password', [*request.values.values(), connection.password]) == '[REDACTED] / [REDACTED] / [REDACTED]'


@pytest.mark.parametrize('host', ['x;touch /tmp/x', '-oProxyCommand=bad', 'user@host', 'https://host', 'host\nnext'])
def test_connection_host_cannot_inject_commands_or_options(host):
    with pytest.raises(ValueError):
        validate_connection(Connection(host=host, password='some-password'))


def test_ipv6_host_and_nondefault_port_are_valid():
    assert validate_connection(Connection(host='2001:db8::7', port=2222, password='some-password')).port == 2222


def test_feishu_deployment_requires_application_and_model_credentials():
    request = DeployRequest(get_profile('huiyang'), '/huiyang', 'server.example')
    with pytest.raises(ValueError, match='App ID'):
        validate_deployment(request)
    request.values = {'FEISHU_APP_ID':'cli_example', 'FEISHU_APP_SECRET':'secret', 'LLM_API_BASE_URL':'http://model.example/v1', 'LLM_API_KEY':'secret', 'LLM_MODEL':'model'}
    with pytest.raises(ValueError, match='HTTPS'):
        validate_deployment(request)


def test_existing_feishu_credentials_can_be_preserved_on_update():
    existing = {'FEISHU_APP_ID':'cli_example', 'FEISHU_APP_SECRET':'secret', 'LLM_API_BASE_URL':'https://model.example/v1', 'LLM_API_KEY':'secret', 'LLM_MODEL':'model'}
    request = DeployRequest(get_profile('huiyang'), '/huiyang', 'server.example')
    assert validate_deployment(request, existing).directory == '/huiyang'


def test_standalone_todo_needs_no_external_credentials():
    request = DeployRequest(get_profile('team-todo'), '/team-todo', '203.0.113.4', https=False, port=8088)
    assert validate_deployment(request).url == 'http://203.0.113.4:8088/'


def test_http_is_not_allowed_for_feishu_oauth():
    with pytest.raises(ValueError, match='HTTPS'):
        validate_deployment(DeployRequest(get_profile('huiyang'), '/huiyang', 'server.example', https=False))


def test_compose_escaped_dollars_are_imported_as_literal_credentials():
    assert import_env('LLM_API_KEY="key\\$literal"\n') == {'LLM_API_KEY':'key$literal'}
