"""add_designator_sequences

Revision ID: b1c2d3e4f5a6
Revises: a2c91f8b3d45
Create Date: 2026-01-05

Adds:
- DesignatorSequence table for tracking sequential designator numbers
- issue_number field to Issue (IT-XXXXX format)
- risk_number field to Risk (RISK-XXXXX format)
- Initializes sequences from existing data
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a2c91f8b3d45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ Create DesignatorSequence Table ============
    op.create_table(
        'designator_sequence',
        sa.Column('designator_type', sa.String(10), nullable=False, comment='OPAL, WO, IT, RISK'),
        sa.Column('last_value', sa.Integer(), nullable=False, default=0, comment='Last assigned sequence number'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('designator_type')
    )

    # ============ Initialize Sequences from Existing Data ============
    conn = op.get_bind()

    # Get current max OPAL number
    result = conn.execute(sa.text(
        "SELECT MAX(CAST(SUBSTR(opal_number, 6) AS INTEGER)) FROM inventory_record WHERE opal_number IS NOT NULL"
    ))
    max_opal = result.scalar() or 0

    # Get current max issue ID (for initial IT sequence)
    result = conn.execute(sa.text("SELECT MAX(id) FROM issue"))
    max_issue = result.scalar() or 0

    # Get current max risk ID (for initial RISK sequence)
    result = conn.execute(sa.text("SELECT MAX(id) FROM risk"))
    max_risk = result.scalar() or 0

    # Get current max work order number if any follow WO-XXXXX format
    result = conn.execute(sa.text(
        "SELECT MAX(CAST(SUBSTR(work_order_number, 4) AS INTEGER)) "
        "FROM procedure_instance "
        "WHERE work_order_number LIKE 'WO-%'"
    ))
    max_wo = result.scalar() or 0

    # Insert sequence records using SQL's CURRENT_TIMESTAMP
    conn.execute(sa.text(
        "INSERT INTO designator_sequence (designator_type, last_value, created_at, updated_at) VALUES "
        "('OPAL', :opal, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
        "('WO', :wo, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
        "('IT', :it, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
        "('RISK', :risk, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ), {"opal": max_opal, "wo": max_wo, "it": max_issue, "risk": max_risk})

    # ============ Add issue_number to Issue ============
    with op.batch_alter_table('issue', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'issue_number', sa.String(20), nullable=True,
            comment='Unique identifier like IT-00001'
        ))
        batch_op.create_unique_constraint('uq_issue_issue_number', ['issue_number'])
        batch_op.create_index('ix_issue_issue_number', ['issue_number'])

    # Backfill existing issues with IT numbers
    result = conn.execute(sa.text("SELECT id FROM issue ORDER BY id"))
    rows = result.fetchall()
    for i, row in enumerate(rows, start=1):
        issue_number = f"IT-{i:05d}"
        conn.execute(sa.text(
            "UPDATE issue SET issue_number = :num WHERE id = :id"
        ), {"num": issue_number, "id": row[0]})

    # ============ Add risk_number to Risk ============
    with op.batch_alter_table('risk', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'risk_number', sa.String(20), nullable=True,
            comment='Unique identifier like RISK-00001'
        ))
        batch_op.create_unique_constraint('uq_risk_risk_number', ['risk_number'])
        batch_op.create_index('ix_risk_risk_number', ['risk_number'])

    # Backfill existing risks with RISK numbers
    result = conn.execute(sa.text("SELECT id FROM risk ORDER BY id"))
    rows = result.fetchall()
    for i, row in enumerate(rows, start=1):
        risk_number = f"RISK-{i:05d}"
        conn.execute(sa.text(
            "UPDATE risk SET risk_number = :num WHERE id = :id"
        ), {"num": risk_number, "id": row[0]})


def downgrade() -> None:
    # ============ Remove risk_number from Risk ============
    with op.batch_alter_table('risk', schema=None) as batch_op:
        batch_op.drop_index('ix_risk_risk_number')
        batch_op.drop_constraint('uq_risk_risk_number', type_='unique')
        batch_op.drop_column('risk_number')

    # ============ Remove issue_number from Issue ============
    with op.batch_alter_table('issue', schema=None) as batch_op:
        batch_op.drop_index('ix_issue_issue_number')
        batch_op.drop_constraint('uq_issue_issue_number', type_='unique')
        batch_op.drop_column('issue_number')

    # ============ Drop DesignatorSequence Table ============
    op.drop_table('designator_sequence')
