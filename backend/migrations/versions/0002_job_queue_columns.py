"""job queue columns

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=16), server_default='format', nullable=False))
        batch_op.add_column(sa.Column('params_json', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('attempts', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('started_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_jobs_status_created', ['status', 'created_at'], unique=False)



def downgrade():
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_jobs_status_created')
        batch_op.drop_column('started_at')
        batch_op.drop_column('attempts')
        batch_op.drop_column('params_json')
        batch_op.drop_column('kind')

