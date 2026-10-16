"""Persistent first-discovered admin and verified Feishu names."""
from alembic import op
import sqlalchemy as sa

revision = "91c702bb340a"
down_revision = "8e21c0a4b001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("identity_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "admin_bindings",
        sa.Column("singleton", sa.Integer(), primary_key=True),
        sa.Column("feishu_user_id", sa.String(255), sa.ForeignKey("users.feishu_user_id"), nullable=False, unique=True),
        sa.Column("discovery_name", sa.String(255), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("singleton = 1", name="ck_admin_singleton"),
    )
    # Preserve a previously verified one-time binding, if this installation has one.
    op.execute(sa.text("""
        INSERT INTO admin_bindings (singleton, feishu_user_id, discovery_name, bound_at)
        SELECT 1, users.feishu_user_id, users.display_name, CURRENT_TIMESTAMP
        FROM users JOIN platform_settings ON platform_settings.value = users.feishu_user_id
        WHERE platform_settings.key = 'verified_admin_user_id'
    """))


def downgrade():
    op.drop_table("admin_bindings")
    op.drop_column("users", "identity_verified_at")
