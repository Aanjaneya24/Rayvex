from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '000dd4ff52a2'
down_revision: Union[str, None] = '560bfe695948'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_decisions', sa.Column('model_name', sa.String(), nullable=False))
    op.add_column('agent_decisions', sa.Column('prompt_version', sa.String(), nullable=False))
    op.add_column('agent_decisions', sa.Column('schema_version', sa.String(), nullable=False))


def downgrade() -> None:
    op.drop_column('agent_decisions', 'schema_version')
    op.drop_column('agent_decisions', 'prompt_version')
    op.drop_column('agent_decisions', 'model_name')
