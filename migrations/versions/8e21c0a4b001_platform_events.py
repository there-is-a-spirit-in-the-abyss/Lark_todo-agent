"""Durable Feishu inbox, context observations and one-time enrollment."""
from alembic import op
import sqlalchemy as sa

revision = "8e21c0a4b001"
down_revision = "d25ffcab2220"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("feishu_inbox",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feishu_inbox_state", "feishu_inbox", ["state"])
    op.create_table("chat_observations",
        sa.Column("message_id", sa.String(255), primary_key=True),
        sa.Column("chat_id", sa.String(255), nullable=False),
        sa.Column("chat_type", sa.String(20), nullable=False),
        sa.Column("sender_user_id", sa.String(255), nullable=False),
        sa.Column("sender_open_id", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_observations_chat_id", "chat_observations", ["chat_id"])
    op.create_index("ix_chat_observations_created_at", "chat_observations", ["created_at"])
    op.create_table("platform_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade():
    op.drop_table("platform_settings")
    op.drop_table("chat_observations")
    op.drop_table("feishu_inbox")
