from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b409f9eff099'
down_revision: Union[str, None] = '000dd4ff52a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    provider_mode_enum = postgresql.ENUM('RAZORPAY_TEST_MODE', 'SIMULATION_MODE', name='provider_mode')
    provider_mode_enum.create(op.get_bind(), checkfirst=True)
    verification_outcome_enum = postgresql.ENUM(
        'RECOVERED', 'FAILED', 'STILL_PENDING', 'ESCALATED', 'ERROR', name='verification_outcome'
    )
    verification_outcome_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('payment_verifications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('payment_id', sa.String(), nullable=False),
    sa.Column('mode', postgresql.ENUM('RAZORPAY_TEST_MODE', 'SIMULATION_MODE', name='provider_mode', create_type=False), nullable=False),
    sa.Column('provider_status', sa.String(), nullable=True),
    sa.Column('outcome', postgresql.ENUM('RECOVERED', 'FAILED', 'STILL_PENDING', 'ESCALATED', 'ERROR', name='verification_outcome', create_type=False), nullable=False),
    sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('resulting_transition_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.ForeignKeyConstraint(['resulting_transition_id'], ['case_state_transitions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payment_verifications_case_id'), 'payment_verifications', ['case_id'], unique=False)
    op.create_index(op.f('ix_payment_verifications_correlation_id'), 'payment_verifications', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_payment_verifications_created_at'), 'payment_verifications', ['created_at'], unique=False)
    op.create_index(op.f('ix_payment_verifications_payment_id'), 'payment_verifications', ['payment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payment_verifications_payment_id'), table_name='payment_verifications')
    op.drop_index(op.f('ix_payment_verifications_created_at'), table_name='payment_verifications')
    op.drop_index(op.f('ix_payment_verifications_correlation_id'), table_name='payment_verifications')
    op.drop_index(op.f('ix_payment_verifications_case_id'), table_name='payment_verifications')
    op.drop_table('payment_verifications')

    postgresql.ENUM(name="provider_mode").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="verification_outcome").drop(op.get_bind(), checkfirst=True)
