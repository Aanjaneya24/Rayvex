from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd7b5a37affd7'
down_revision: Union[str, None] = 'e8a3c03ce3ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table('recovery_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('merchant_id', sa.String(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('default_probability_by_action', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('action_cost_by_action', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('risk_cost_multiplier', sa.Float(), nullable=False),
    sa.Column('min_sample_size', sa.Integer(), nullable=False),
    sa.Column('smoothing_alpha', sa.Float(), nullable=False),
    sa.Column('smoothing_beta', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recovery_configs_merchant_id'), 'recovery_configs', ['merchant_id'], unique=False)
    op.create_index('uq_recovery_configs_active_per_merchant', 'recovery_configs', ['merchant_id'], unique=True, postgresql_where=sa.text('is_active'), postgresql_nulls_not_distinct=True)
    op.create_table('synthetic_recovery_outcomes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('merchant_id', sa.String(), nullable=False),
    sa.Column('customer_id', sa.String(), nullable=False),
    sa.Column('payment_method', sa.String(), nullable=False),
    sa.Column('failure_category', sa.String(), nullable=False),
    sa.Column('failure_code', sa.String(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('retry_count_at_action_time', sa.Integer(), nullable=False),
    sa.Column('risk_score', sa.Float(), nullable=False),
    sa.Column('action_taken', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=False),
    sa.Column('recovered', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_synthetic_recovery_outcomes_customer_id'), 'synthetic_recovery_outcomes', ['customer_id'], unique=False)
    op.create_index(op.f('ix_synthetic_recovery_outcomes_failure_category'), 'synthetic_recovery_outcomes', ['failure_category'], unique=False)
    op.create_index(op.f('ix_synthetic_recovery_outcomes_failure_code'), 'synthetic_recovery_outcomes', ['failure_code'], unique=False)
    op.create_index(op.f('ix_synthetic_recovery_outcomes_merchant_id'), 'synthetic_recovery_outcomes', ['merchant_id'], unique=False)
    op.create_index(op.f('ix_synthetic_recovery_outcomes_payment_method'), 'synthetic_recovery_outcomes', ['payment_method'], unique=False)
    op.create_index(op.f('ix_synthetic_recovery_outcomes_seed'), 'synthetic_recovery_outcomes', ['seed'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_synthetic_recovery_outcomes_seed'), table_name='synthetic_recovery_outcomes')
    op.drop_index(op.f('ix_synthetic_recovery_outcomes_payment_method'), table_name='synthetic_recovery_outcomes')
    op.drop_index(op.f('ix_synthetic_recovery_outcomes_merchant_id'), table_name='synthetic_recovery_outcomes')
    op.drop_index(op.f('ix_synthetic_recovery_outcomes_failure_code'), table_name='synthetic_recovery_outcomes')
    op.drop_index(op.f('ix_synthetic_recovery_outcomes_failure_category'), table_name='synthetic_recovery_outcomes')
    op.drop_index(op.f('ix_synthetic_recovery_outcomes_customer_id'), table_name='synthetic_recovery_outcomes')
    op.drop_table('synthetic_recovery_outcomes')
    op.drop_index('uq_recovery_configs_active_per_merchant', table_name='recovery_configs', postgresql_where=sa.text('is_active'), postgresql_nulls_not_distinct=True)
    op.drop_index(op.f('ix_recovery_configs_merchant_id'), table_name='recovery_configs')
    op.drop_table('recovery_configs')
