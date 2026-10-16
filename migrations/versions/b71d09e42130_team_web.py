"""Independent team web state; existing personal/legacy records stay intact."""
from alembic import op
import sqlalchemy as sa

revision = "b71d09e42130"
down_revision = "a471b85c2190"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("team_spaces",
        sa.Column("chat_id", sa.String(255), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("board", sa.JSON(), nullable=False),
        sa.Column("people", sa.JSON(), nullable=False))
    op.create_table("team_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("csrf", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False))
    op.create_index("ix_team_sessions_expires_at", "team_sessions", ["expires_at"])
    op.create_table("team_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("chat_id", sa.String(255), nullable=False),
        sa.Column("verifier", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False))
    op.create_index("ix_team_oauth_states_expires_at", "team_oauth_states", ["expires_at"])


def downgrade():
    op.drop_table("team_oauth_states")
    op.drop_table("team_sessions")
    op.drop_table("team_spaces")
