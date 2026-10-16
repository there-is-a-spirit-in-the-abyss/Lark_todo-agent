class PermissionDenied(PermissionError):
    """Raised when an actor attempts to manage another member's task."""


class PermissionService:
    """Authorize against the persisted admin ID, never a name or current group ownership."""
    def __init__(self, admin_feishu_user_id: str = "") -> None:
        self._admin_feishu_user_id = admin_feishu_user_id

    def is_admin(self, sender_user_id: str) -> bool:
        """Names are used by discovery only; permissions compare IDs."""
        return bool(self._admin_feishu_user_id) and sender_user_id == self._admin_feishu_user_id

    def assert_can_manage(
        self,
        *,
        actor_feishu_user_id: str,
        assignee_feishu_user_id: str,
    ) -> None:
        is_admin = self.is_admin(actor_feishu_user_id)
        if not is_admin and actor_feishu_user_id != assignee_feishu_user_id:
            raise PermissionDenied("只能管理自己负责的任务")
