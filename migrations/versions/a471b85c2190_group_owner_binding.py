"""Record group-owner bootstrap source without replacing existing administrators."""
from alembic import op
import sqlalchemy as sa

revision = "a471b85c2190"
down_revision = "91c702bb340a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admin_bindings", sa.Column("source_chat_id", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("admin_bindings", "source_chat_id")
