"""Add risk_number to Risk model

Revision ID: 8c28773a540e
Revises: 9d685df5636f
Create Date: 2026-01-13 23:41:24.744572

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c28773a540e'
down_revision: Union[str, None] = '9d685df5636f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update any existing rows with null risk_number
    op.execute("UPDATE risk SET risk_number = 'RISK-' || printf('%03d', id) WHERE risk_number IS NULL")

    # Make risk_number NOT NULL (SQLite requires batch mode for this)
    with op.batch_alter_table('risk', schema=None) as batch_op:
        batch_op.alter_column('risk_number', nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('risk', schema=None) as batch_op:
        batch_op.alter_column('risk_number', nullable=True)
