"""Group-owner discovery, immutable database binding, then ID-only authorization."""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from huiyang.domain.persistence import AdminBinding, User


def dialect_insert(session, model):
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError("Unsupported identity database")
    return insert(model)


async def upsert_sender(session, message):
    name = message.sender_display_name
    if not message.sender_id or not name.strip() or len(name) > 255:
        raise ValueError("A verified sender ID and display name are required")
    now = datetime.now(UTC)
    statement = dialect_insert(session, User).values(
        id=uuid4(), feishu_user_id=message.sender_id, display_name=name,
        identity_verified_at=now, created_at=now, updated_at=now,
    ).on_conflict_do_update(index_elements=["feishu_user_id"], set_={
        "display_name": name, "identity_verified_at": now, "updated_at": now,
    })
    await session.execute(statement)
    return await session.scalar(select(User).where(
        User.feishu_user_id == message.sender_id).execution_options(populate_existing=True))


async def bind_group_admin_if_unset(session, message, adapter):
    # V1 has one target group. Its first received group message supplies the chat ID.
    # Never query ownership again after binding, including after a group-owner transfer.
    if message.chat_type != "group" or await session.get(AdminBinding, 1) is not None:
        return
    from huiyang.adapters.feishu_api import FeishuAPIError
    owner = await adapter.get_chat_owner(message.chat_id)
    if (owner.chat_id != message.chat_id or not isinstance(owner.user_id, str)
            or not owner.user_id.strip() or len(owner.user_id) > 255):
        raise FeishuAPIError("Invalid group owner identity")
    now = datetime.now(UTC)
    # The owner need not have spoken or have a contact-profile permission grant.
    # Preserve an existing profile; an ID-only placeholder is updated on their first message.
    await session.execute(dialect_insert(session, User).values(
        id=uuid4(), feishu_user_id=owner.user_id, display_name=owner.user_id,
        created_at=now, updated_at=now,
    ).on_conflict_do_nothing(index_elements=["feishu_user_id"]))
    # The singleton key arbitrates concurrent discovery. No update path is allowed.
    await session.execute(dialect_insert(session, AdminBinding).values(
        singleton=1, feishu_user_id=owner.user_id, discovery_name="",
        source_chat_id=message.chat_id, bound_at=now,
    ).on_conflict_do_nothing(index_elements=["singleton"]))


async def effective_admin(session, settings=None):
    bound = await session.get(AdminBinding, 1)
    if bound is not None:
        return bound.feishu_user_id
    # Legacy optional fallback only. An existing DB binding always takes precedence.
    return getattr(settings, "admin_feishu_user_id", "") or ""
