from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '46d0452fa5a5'
down_revision: Union[str, None] = 'acc43eee8859'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RECOVERY_ACTION = postgresql.ENUM(
    'RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK',
    'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP',
    name='recovery_action',
)
HUMAN_REVIEW_DECISION = postgresql.ENUM(
    'APPROVE', 'REJECT', 'OVERRIDE', name='human_review_decision',
)


def upgrade() -> None:
    HUMAN_REVIEW_DECISION.create(op.get_bind(), checkfirst=True)

    op.create_table('ab_experiment_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('failure_code', sa.String(), nullable=False),
    sa.Column('payment_method', sa.String(), nullable=False),
    sa.Column('action_a', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=False),
    sa.Column('action_b', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=False),
    sa.Column('sample_size_a', sa.Integer(), nullable=False),
    sa.Column('sample_size_b', sa.Integer(), nullable=False),
    sa.Column('successes_a', sa.Integer(), nullable=False),
    sa.Column('successes_b', sa.Integer(), nullable=False),
    sa.Column('recovery_rate_a', sa.Float(), nullable=False),
    sa.Column('recovery_rate_b', sa.Float(), nullable=False),
    sa.Column('revenue_a', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('revenue_b', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('cost_per_recovered_rupee_a', sa.Float(), nullable=True),
    sa.Column('cost_per_recovered_rupee_b', sa.Float(), nullable=True),
    sa.Column('p_value', sa.Float(), nullable=True),
    sa.Column('min_sample_size', sa.Integer(), nullable=False),
    sa.Column('significance_level', sa.Float(), nullable=False),
    sa.Column('result', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ab_experiment_runs_created_at'), 'ab_experiment_runs', ['created_at'], unique=False)
    op.create_table('ml_model_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('train_size', sa.Integer(), nullable=False),
    sa.Column('validation_size', sa.Integer(), nullable=False),
    sa.Column('test_size', sa.Integer(), nullable=False),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('feature_importance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('categories', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('model_path', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ml_model_runs_created_at'), 'ml_model_runs', ['created_at'], unique=False)
    op.create_table('merchant_recovery_outcomes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('merchant_id', sa.String(), nullable=False),
    sa.Column('failure_code', sa.String(), nullable=False),
    sa.Column('payment_method', sa.String(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('action_taken', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=False),
    sa.Column('recovered', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_merchant_recovery_outcomes_case_id'), 'merchant_recovery_outcomes', ['case_id'], unique=False)
    op.create_index(op.f('ix_merchant_recovery_outcomes_created_at'), 'merchant_recovery_outcomes', ['created_at'], unique=False)
    op.create_index(op.f('ix_merchant_recovery_outcomes_failure_code'), 'merchant_recovery_outcomes', ['failure_code'], unique=False)
    op.create_index(op.f('ix_merchant_recovery_outcomes_merchant_id'), 'merchant_recovery_outcomes', ['merchant_id'], unique=False)
    op.create_index(op.f('ix_merchant_recovery_outcomes_payment_method'), 'merchant_recovery_outcomes', ['payment_method'], unique=False)
    op.create_table('human_review_actions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('reviewer', sa.String(), nullable=False),
    sa.Column('decision', postgresql.ENUM('APPROVE', 'REJECT', 'OVERRIDE', name='human_review_decision', create_type=False), nullable=False),
    sa.Column('original_proposed_action', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=True),
    sa.Column('final_action', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=True),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('resulting_transition_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.ForeignKeyConstraint(['resulting_transition_id'], ['case_state_transitions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_human_review_actions_case_id'), 'human_review_actions', ['case_id'], unique=False)
    op.create_index(op.f('ix_human_review_actions_correlation_id'), 'human_review_actions', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_human_review_actions_created_at'), 'human_review_actions', ['created_at'], unique=False)
    op.add_column('agent_decisions', sa.Column('llm_call_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('agent_decisions', sa.Column('total_latency_ms', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('agent_decisions', sa.Column('estimated_cost_usd', sa.Float(), nullable=False, server_default='0'))
    op.alter_column('agent_decisions', 'llm_call_count', server_default=None)
    op.alter_column('agent_decisions', 'total_latency_ms', server_default=None)
    op.alter_column('agent_decisions', 'estimated_cost_usd', server_default=None)


def downgrade() -> None:
    op.drop_column('agent_decisions', 'estimated_cost_usd')
    op.drop_column('agent_decisions', 'total_latency_ms')
    op.drop_column('agent_decisions', 'llm_call_count')
    op.drop_index(op.f('ix_human_review_actions_created_at'), table_name='human_review_actions')
    op.drop_index(op.f('ix_human_review_actions_correlation_id'), table_name='human_review_actions')
    op.drop_index(op.f('ix_human_review_actions_case_id'), table_name='human_review_actions')
    op.drop_table('human_review_actions')
    op.drop_index(op.f('ix_merchant_recovery_outcomes_payment_method'), table_name='merchant_recovery_outcomes')
    op.drop_index(op.f('ix_merchant_recovery_outcomes_merchant_id'), table_name='merchant_recovery_outcomes')
    op.drop_index(op.f('ix_merchant_recovery_outcomes_failure_code'), table_name='merchant_recovery_outcomes')
    op.drop_index(op.f('ix_merchant_recovery_outcomes_created_at'), table_name='merchant_recovery_outcomes')
    op.drop_index(op.f('ix_merchant_recovery_outcomes_case_id'), table_name='merchant_recovery_outcomes')
    op.drop_table('merchant_recovery_outcomes')
    op.drop_index(op.f('ix_ml_model_runs_created_at'), table_name='ml_model_runs')
    op.drop_table('ml_model_runs')
    op.drop_index(op.f('ix_ab_experiment_runs_created_at'), table_name='ab_experiment_runs')
    op.drop_table('ab_experiment_runs')

    HUMAN_REVIEW_DECISION.drop(op.get_bind(), checkfirst=True)
