"""Phase 3: webhook receipts, invitations and job workspace."""
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None

def upgrade():
    op.add_column("users", sa.Column("checkout_session_id", sa.String(100)))
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("team_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_jobs_team", "teams", ["team_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_jobs_team_id", ["team_id"])
    op.create_table("billing_events", sa.Column("id", sa.String(100), primary_key=True), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("team_invites", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False), sa.Column("accepted_at", sa.DateTime()))
    op.create_index("ix_team_invites_team_id", "team_invites", ["team_id"])

def downgrade():
    op.drop_column("users", "checkout_session_id")
    op.drop_table("team_invites")
    op.drop_table("billing_events")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_index("ix_jobs_team_id")
        batch.drop_constraint("fk_jobs_team", type_="foreignkey")
        batch.drop_column("team_id")
