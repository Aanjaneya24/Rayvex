from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e8a3c03ce3ae'
down_revision: Union[str, None] = '2141700ff4f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    recovery_action_enum = postgresql.ENUM(
        'RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK',
        'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP',
        name='recovery_action',
    )
    recovery_action_enum.create(op.get_bind(), checkfirst=True)
    policy_verdict_type_enum = postgresql.ENUM(
        'ALLOW', 'DENY', 'FORCE_ACTION', name='policy_verdict_type',
    )
    policy_verdict_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('policy_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('merchant_id', sa.String(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('max_retry_count', sa.Integer(), nullable=False),
    sa.Column('cooldown_seconds', sa.Integer(), nullable=False),
    sa.Column('max_automated_recovery_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('max_daily_attempts_per_customer', sa.Integer(), nullable=False),
    sa.Column('prohibited_retry_failure_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('suspicious_velocity_threshold', sa.Integer(), nullable=False),
    sa.Column('suspicious_velocity_window_seconds', sa.Integer(), nullable=False),
    sa.Column('high_value_threshold', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('allowed_actions_by_failure_code', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('allowed_communication_hours_start', sa.Integer(), nullable=False),
    sa.Column('allowed_communication_hours_end', sa.Integer(), nullable=False),
    sa.Column('max_interventions_per_case', sa.Integer(), nullable=False),
    sa.Column('risk_score_threshold', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_policy_configs_merchant_id'), 'policy_configs', ['merchant_id'], unique=False)
    op.create_index('uq_policy_configs_active_per_merchant', 'policy_configs', ['merchant_id'], unique=True, postgresql_where=sa.text('is_active'), postgresql_nulls_not_distinct=True)
    op.create_table('policy_decisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('policy_config_id', sa.UUID(), nullable=False),
    sa.Column('policy_config_version', sa.Integer(), nullable=False),
    sa.Column('proposed_action', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=False),
    sa.Column('verdict_type', postgresql.ENUM('ALLOW', 'DENY', 'FORCE_ACTION', name='policy_verdict_type', create_type=False), nullable=False),
    sa.Column('resulting_action', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=True),
    sa.Column('rule_id', sa.String(), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('requires_escalation', sa.Boolean(), nullable=False),
    sa.Column('context_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.ForeignKeyConstraint(['policy_config_id'], ['policy_configs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_policy_decisions_case_id'), 'policy_decisions', ['case_id'], unique=False)
    op.create_index(op.f('ix_policy_decisions_correlation_id'), 'policy_decisions', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_policy_decisions_created_at'), 'policy_decisions', ['created_at'], unique=False)
    op.add_column('case_state_transitions', sa.Column('policy_decision_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'case_state_transitions_policy_decision_id_fkey',
        'case_state_transitions', 'policy_decisions', ['policy_decision_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint(
        'case_state_transitions_policy_decision_id_fkey',
        'case_state_transitions', type_='foreignkey'
    )
    op.drop_column('case_state_transitions', 'policy_decision_id')
    op.drop_index(op.f('ix_policy_decisions_created_at'), table_name='policy_decisions')
    op.drop_index(op.f('ix_policy_decisions_correlation_id'), table_name='policy_decisions')
    op.drop_index(op.f('ix_policy_decisions_case_id'), table_name='policy_decisions')
    op.drop_table('policy_decisions')
    op.drop_index('uq_policy_configs_active_per_merchant', table_name='policy_configs', postgresql_where=sa.text('is_active'), postgresql_nulls_not_distinct=True)
    op.drop_index(op.f('ix_policy_configs_merchant_id'), table_name='policy_configs')
    op.drop_table('policy_configs')

    postgresql.ENUM(name="recovery_action").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="policy_verdict_type").drop(op.get_bind(), checkfirst=True)
