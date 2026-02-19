"""add production status and widen designator type

Revision ID: a1b2c3d4e5f6
Revises: 74ae45c61c41
Create Date: 2026-02-19 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '74ae45c61c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add status column to inventory_production
    op.add_column(
        'inventory_production',
        sa.Column('status', sa.String(20), nullable=False, server_default='planned',
                  comment='planned = allocated, wip = execution started, completed = finalized'),
    )

    # Widen designator_sequence.designator_type from String(10) to String(50)
    # to support per-part serial number keys like "SN-PO/1-001"
    with op.batch_alter_table('designator_sequence') as batch_op:
        batch_op.alter_column(
            'designator_type',
            existing_type=sa.String(10),
            type_=sa.String(50),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('designator_sequence') as batch_op:
        batch_op.alter_column(
            'designator_type',
            existing_type=sa.String(50),
            type_=sa.String(10),
            existing_nullable=False,
        )

    op.drop_column('inventory_production', 'status')
