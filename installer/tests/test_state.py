import pytest

from deployer.state import WizardState


def test_deploy_cannot_start_without_a_live_connection():
    state = WizardState()
    with pytest.raises(ValueError):
        state.begin('deploy')
    assert not state.busy


def test_only_one_remote_operation_can_run_at_a_time():
    state = WizardState(connected=True)
    state.begin('browse')
    with pytest.raises(ValueError):
        state.begin('deploy')
    state.finish()
    state.begin('deploy')
    assert state.busy


def test_failed_deploy_does_not_leave_a_previous_success_link():
    state = WizardState(connected=True, url='https://old.example/')
    state.begin('deploy')
    state.finish(error='failed')
    assert not state.url
    assert state.error == 'failed'
    assert state.connected


def test_editing_connection_invalidates_old_server_receipt():
    state = WizardState(connected=True, url='https://old.example/')
    state.disconnect()
    assert not state.connected
    assert not state.url


def test_receipt_cannot_open_a_non_web_url():
    state = WizardState(connected=True)
    state.begin('deploy')
    with pytest.raises(ValueError):
        state.finish(url='file:///etc/passwd')
    assert not state.url


def test_config_import_supports_escaped_quotes_without_expanding_dollars():
    from deployer.config import import_env
    assert import_env("FEISHU_APP_SECRET='team\\'s $secret'\n") == {'FEISHU_APP_SECRET':"team's $secret"}
