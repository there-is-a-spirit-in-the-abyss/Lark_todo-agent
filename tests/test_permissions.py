from importlib import import_module

import pytest


def load_permissions():
    try:
        return import_module("huiyang.services.permissions")
    except ModuleNotFoundError:
        pytest.fail("permission service is missing")


def test_admin_can_manage_any_assignee_by_feishu_user_id() -> None:
    permissions = load_permissions()
    service = permissions.PermissionService(admin_feishu_user_id="ou_admin")

    service.assert_can_manage(actor_feishu_user_id="ou_admin", assignee_feishu_user_id="ou_xiao")


def test_member_can_manage_self_but_not_another_member() -> None:
    permissions = load_permissions()
    service = permissions.PermissionService(admin_feishu_user_id="ou_admin")

    service.assert_can_manage(actor_feishu_user_id="ou_xiao", assignee_feishu_user_id="ou_xiao")

    with pytest.raises(permissions.PermissionDenied):
        service.assert_can_manage(
            actor_feishu_user_id="ou_xiao",
            assignee_feishu_user_id="ou_other",
        )


def test_display_name_does_not_grant_admin_permission() -> None:
    permissions = load_permissions()
    service = permissions.PermissionService(admin_feishu_user_id="ou_admin")

    with pytest.raises(permissions.PermissionDenied):
        service.assert_can_manage(
            actor_feishu_user_id="张宇宙",
            assignee_feishu_user_id="ou_other",
        )
