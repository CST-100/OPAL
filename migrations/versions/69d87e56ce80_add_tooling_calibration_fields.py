"""add_tooling_calibration_fields

Revision ID: 69d87e56ce80
Revises: 6ef042183637
Create Date: 2026-02-17 00:52:17.803344

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69d87e56ce80'
down_revision: Union[str, None] = '6ef042183637'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    """Check if a column already exists (handles partial migration)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if not _has_column('inventory_record', 'last_calibrated_at'):
        with op.batch_alter_table('inventory_record', schema=None) as batch_op:
            batch_op.add_column(sa.Column('last_calibrated_at', sa.DateTime(timezone=True), nullable=True, comment='When this tool was last calibrated'))
            batch_op.add_column(sa.Column('calibration_due_at', sa.DateTime(timezone=True), nullable=True, comment='When next calibration is due'))
            batch_op.create_index(batch_op.f('ix_inventory_record_calibration_due_at'), ['calibration_due_at'], unique=False)

    if not _has_column('part', 'is_tooling'):
        with op.batch_alter_table('part', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_tooling', sa.Boolean(), nullable=False, server_default=sa.text('0'), comment='Whether this part is a tool requiring calibration tracking'))
            batch_op.add_column(sa.Column('calibration_interval_days', sa.Integer(), nullable=True, comment='Days between required calibrations (e.g., 365 for annual)'))
            batch_op.create_index(batch_op.f('ix_part_is_tooling'), ['is_tooling'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('part', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_part_is_tooling'))
        batch_op.drop_column('calibration_interval_days')
        batch_op.drop_column('is_tooling')

    with op.batch_alter_table('inventory_record', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inventory_record_calibration_due_at'))
        batch_op.drop_column('calibration_due_at')
        batch_op.drop_column('last_calibrated_at')
