from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2141700ff4f9'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('cases',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('case_type', sa.Enum('PAYMENT_FAILURE', 'CHECKOUT_ABANDONMENT', name='case_type'), nullable=False),
    sa.Column('merchant_id', sa.String(), nullable=False),
    sa.Column('customer_id', sa.String(), nullable=True),
    sa.Column('payment_id', sa.String(), nullable=True),
    sa.Column('order_id', sa.String(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('payment_method', sa.String(), nullable=True),
    sa.Column('failure_code', sa.String(), nullable=True),
    sa.Column('failure_reason', sa.String(), nullable=True),
    sa.Column('current_state', sa.Enum('RECEIVED', 'SCREENING', 'DIAGNOSING', 'ELIGIBILITY_CHECK', 'DECISION', 'ACTION_PENDING', 'ACTION_EXECUTED', 'VERIFICATION_PENDING', 'RECOVERED', 'FAILED', 'ESCALATED', 'STOPPED', name='case_state'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cases_correlation_id'), 'cases', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_cases_current_state'), 'cases', ['current_state'], unique=False)
    op.create_index(op.f('ix_cases_customer_id'), 'cases', ['customer_id'], unique=False)
    op.create_index(op.f('ix_cases_merchant_id'), 'cases', ['merchant_id'], unique=False)
    op.create_index(op.f('ix_cases_order_id'), 'cases', ['order_id'], unique=False)
    op.create_index(op.f('ix_cases_payment_id'), 'cases', ['payment_id'], unique=False)
    op.create_table('raw_webhook_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('razorpay_event_id', sa.String(), nullable=False),
    sa.Column('event_type', sa.String(), nullable=False),
    sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('signature_valid', sa.Boolean(), nullable=False),
    sa.Column('processing_status', sa.Enum('RECEIVED', 'PROCESSED', 'DUPLICATE', 'FAILED', name='processing_status'), nullable=False),
    sa.Column('matched_case_id', sa.UUID(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['matched_case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('razorpay_event_id')
    )
    op.create_index(op.f('ix_raw_webhook_events_correlation_id'), 'raw_webhook_events', ['correlation_id'], unique=True)
    op.create_index(op.f('ix_raw_webhook_events_matched_case_id'), 'raw_webhook_events', ['matched_case_id'], unique=False)
    op.create_table('payment_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('payment_id', sa.String(), nullable=True),
    sa.Column('order_id', sa.String(), nullable=True),
    sa.Column('event_type', sa.Enum('PAYMENT_FAILED', 'PAYMENT_AUTHORIZED', 'PAYMENT_CAPTURED', 'ORDER_PAID', name='event_type'), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('payment_method', sa.String(), nullable=True),
    sa.Column('failure_code', sa.String(), nullable=True),
    sa.Column('failure_reason', sa.String(), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('raw_payload_reference', sa.UUID(), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('processing_status', sa.Enum('RECEIVED', 'PROCESSED', 'DUPLICATE', 'FAILED', name='processing_status'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.ForeignKeyConstraint(['raw_payload_reference'], ['raw_webhook_events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payment_events_case_id'), 'payment_events', ['case_id'], unique=False)
    op.create_index(op.f('ix_payment_events_correlation_id'), 'payment_events', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_payment_events_event_id'), 'payment_events', ['event_id'], unique=False)
    op.create_index(op.f('ix_payment_events_order_id'), 'payment_events', ['order_id'], unique=False)
    op.create_index(op.f('ix_payment_events_payment_id'), 'payment_events', ['payment_id'], unique=False)
    op.create_table('case_state_transitions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('from_state', sa.Enum('RECEIVED', 'SCREENING', 'DIAGNOSING', 'ELIGIBILITY_CHECK', 'DECISION', 'ACTION_PENDING', 'ACTION_EXECUTED', 'VERIFICATION_PENDING', 'RECOVERED', 'FAILED', 'ESCALATED', 'STOPPED', name='case_state'), nullable=True),
    sa.Column('to_state', sa.Enum('RECEIVED', 'SCREENING', 'DIAGNOSING', 'ELIGIBILITY_CHECK', 'DECISION', 'ACTION_PENDING', 'ACTION_EXECUTED', 'VERIFICATION_PENDING', 'RECOVERED', 'FAILED', 'ESCALATED', 'STOPPED', name='case_state'), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('actor', sa.String(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('triggering_payment_event_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.ForeignKeyConstraint(['triggering_payment_event_id'], ['payment_events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_state_transitions_case_id'), 'case_state_transitions', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_state_transitions_correlation_id'), 'case_state_transitions', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_case_state_transitions_created_at'), 'case_state_transitions', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_case_state_transitions_created_at'), table_name='case_state_transitions')
    op.drop_index(op.f('ix_case_state_transitions_correlation_id'), table_name='case_state_transitions')
    op.drop_index(op.f('ix_case_state_transitions_case_id'), table_name='case_state_transitions')
    op.drop_table('case_state_transitions')
    op.drop_index(op.f('ix_payment_events_payment_id'), table_name='payment_events')
    op.drop_index(op.f('ix_payment_events_order_id'), table_name='payment_events')
    op.drop_index(op.f('ix_payment_events_event_id'), table_name='payment_events')
    op.drop_index(op.f('ix_payment_events_correlation_id'), table_name='payment_events')
    op.drop_index(op.f('ix_payment_events_case_id'), table_name='payment_events')
    op.drop_table('payment_events')
    op.drop_index(op.f('ix_raw_webhook_events_matched_case_id'), table_name='raw_webhook_events')
    op.drop_index(op.f('ix_raw_webhook_events_correlation_id'), table_name='raw_webhook_events')
    op.drop_table('raw_webhook_events')
    op.drop_index(op.f('ix_cases_payment_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_order_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_merchant_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_customer_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_current_state'), table_name='cases')
    op.drop_index(op.f('ix_cases_correlation_id'), table_name='cases')
    op.drop_table('cases')

    postgresql.ENUM(name="case_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="case_state").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="event_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="processing_status").drop(op.get_bind(), checkfirst=True)
