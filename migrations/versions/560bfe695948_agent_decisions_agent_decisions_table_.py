from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '560bfe695948'
down_revision: Union[str, None] = 'd7b5a37affd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    risk_level_enum = postgresql.ENUM('LOW', 'MEDIUM', 'HIGH', name='risk_level')
    risk_level_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('agent_decisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('proposed_action', postgresql.ENUM('RETRY', 'SEND_RECOVERY_REMINDER', 'SEND_RECOVERY_LINK', 'SUGGEST_ALTERNATIVE_PAYMENT_METHOD', 'ESCALATE_TO_HUMAN', 'STOP', name='recovery_action', create_type=False), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('expected_recovery_value', sa.Float(), nullable=False),
    sa.Column('risk_level', postgresql.ENUM('LOW', 'MEDIUM', 'HIGH', name='risk_level', create_type=False), nullable=False),
    sa.Column('model_backend', sa.String(), nullable=False),
    sa.Column('tool_trace', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_decisions_case_id'), 'agent_decisions', ['case_id'], unique=False)
    op.create_index(op.f('ix_agent_decisions_correlation_id'), 'agent_decisions', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_agent_decisions_created_at'), 'agent_decisions', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_decisions_created_at'), table_name='agent_decisions')
    op.drop_index(op.f('ix_agent_decisions_correlation_id'), table_name='agent_decisions')
    op.drop_index(op.f('ix_agent_decisions_case_id'), table_name='agent_decisions')
    op.drop_table('agent_decisions')

    postgresql.ENUM(name="risk_level").drop(op.get_bind(), checkfirst=True)
