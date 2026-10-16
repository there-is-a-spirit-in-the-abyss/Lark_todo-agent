from huiyang.i18n import t
from huiyang.agent.schemas import ActionType


class PersonalChatExecutor:
    """Keep the existing private workflow from reaching retired team records."""
    def __init__(self, delegate):
        self.delegate = delegate

    async def execute(self, action, message):
        if action.action_type == ActionType.WEEKLY_SUMMARY:
            raise ValueError(t("团队任务请在网页查看"))
        visibility = action.payload.get("visibility")
        if visibility is not None and visibility != "personal":
            raise ValueError(t("私聊仅维护个人任务"))
        return await self.delegate.execute(action, message)
