from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'acc43eee8859'
down_revision: Union[str, None] = 'b409f9eff099'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('benchmark_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('case_count', sa.Integer(), nullable=False),
    sa.Column('naive_retry_metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('intelligent_recovery_metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('unnecessary_actions_avoided', sa.Integer(), nullable=False),
    sa.Column('incremental_verified_revenue', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_benchmark_runs_created_at'), 'benchmark_runs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_benchmark_runs_created_at'), table_name='benchmark_runs')
    op.drop_table('benchmark_runs')
