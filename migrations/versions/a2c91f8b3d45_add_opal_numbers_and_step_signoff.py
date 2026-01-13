"""add_opal_numbers_and_step_signoff

Revision ID: a2c91f8b3d45
Revises: 93b2946223cb
Create Date: 2025-12-30

Adds:
- OPAL numbers for inventory traceability
- Source tracking for inventory (PO link)
- Tracking type for parts (bulk vs serialized)
- Step hierarchy and sign-off fields for procedure execution
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2c91f8b3d45'
down_revision: Union[str, None] = '93b2946223cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ OPAL Numbers & Traceability ============

    # Add tracking_type to part
    with op.batch_alter_table('part', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'tracking_type', sa.String(20), nullable=False,
            server_default='bulk',
            comment='bulk = one OPAL per batch, serialized = one OPAL per unit'
        ))

    # Add OPAL fields to inventory_record
    with op.batch_alter_table('inventory_record', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'opal_number', sa.String(20), nullable=True,
            comment='Unique identifier like OPAL-00001'
        ))
        batch_op.add_column(sa.Column(
            'source_type', sa.String(20), nullable=True,
            comment='purchase, production, manual, transfer'
        ))
        batch_op.add_column(sa.Column(
            'source_purchase_line_id', sa.Integer(), nullable=True,
            comment='Link to PO line if from purchase'
        ))
        batch_op.add_column(sa.Column(
            'source_production_id', sa.Integer(), nullable=True,
            comment='Link to production record if produced'
        ))
        batch_op.create_unique_constraint('uq_inventory_record_opal_number', ['opal_number'])
        batch_op.create_index('ix_inventory_record_opal_number', ['opal_number'])
        batch_op.create_index('ix_inventory_record_source_purchase_line_id', ['source_purchase_line_id'])
        batch_op.create_index('ix_inventory_record_source_production_id', ['source_production_id'])
        batch_op.create_foreign_key(
            'fk_inventory_record_source_purchase_line',
            'purchase_line', ['source_purchase_line_id'], ['id'],
            ondelete='SET NULL'
        )
        batch_op.create_foreign_key(
            'fk_inventory_record_source_production',
            'inventory_production', ['source_production_id'], ['id'],
            ondelete='SET NULL'
        )

    # Backfill existing inventory records with OPAL numbers
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT id FROM inventory_record ORDER BY id"
    ))
    rows = result.fetchall()
    for i, row in enumerate(rows, start=1):
        opal_number = f"OPAL-{i:05d}"
        conn.execute(sa.text(
            "UPDATE inventory_record SET opal_number = :opal, source_type = 'manual' WHERE id = :id"
        ), {"opal": opal_number, "id": row[0]})

    # ============ Step Hierarchy & Sign-off ============

    with op.batch_alter_table('step_execution', schema=None) as batch_op:
        # Hierarchy tracking
        batch_op.add_column(sa.Column(
            'step_number_str', sa.String(20), nullable=False,
            server_default='1',
            comment='Display number like 1, 1.1, C1'
        ))
        batch_op.add_column(sa.Column(
            'level', sa.Integer(), nullable=False,
            server_default='0',
            comment='0=parent OP, 1+=sub-step'
        ))
        batch_op.add_column(sa.Column(
            'parent_step_order', sa.Integer(), nullable=True,
            comment='Order of parent step (for sub-steps)'
        ))
        # Sign-off fields
        batch_op.add_column(sa.Column(
            'signed_off_at', sa.DateTime(timezone=True), nullable=True,
            comment='When OP was signed off'
        ))
        batch_op.add_column(sa.Column(
            'signed_off_by_id', sa.Integer(), nullable=True
        ))
        batch_op.create_foreign_key(
            'fk_step_execution_signed_off_by',
            'user', ['signed_off_by_id'], ['id'],
            ondelete='SET NULL'
        )

    # Backfill step_number_str from step_number for existing executions
    conn.execute(sa.text(
        "UPDATE step_execution SET step_number_str = CAST(step_number AS TEXT)"
    ))


def downgrade() -> None:
    # ============ Remove Step Hierarchy & Sign-off ============

    with op.batch_alter_table('step_execution', schema=None) as batch_op:
        batch_op.drop_constraint('fk_step_execution_signed_off_by', type_='foreignkey')
        batch_op.drop_column('signed_off_by_id')
        batch_op.drop_column('signed_off_at')
        batch_op.drop_column('parent_step_order')
        batch_op.drop_column('level')
        batch_op.drop_column('step_number_str')

    # ============ Remove OPAL Numbers & Traceability ============

    with op.batch_alter_table('inventory_record', schema=None) as batch_op:
        batch_op.drop_constraint('fk_inventory_record_source_production', type_='foreignkey')
        batch_op.drop_constraint('fk_inventory_record_source_purchase_line', type_='foreignkey')
        batch_op.drop_index('ix_inventory_record_source_production_id')
        batch_op.drop_index('ix_inventory_record_source_purchase_line_id')
        batch_op.drop_index('ix_inventory_record_opal_number')
        batch_op.drop_constraint('uq_inventory_record_opal_number', type_='unique')
        batch_op.drop_column('source_production_id')
        batch_op.drop_column('source_purchase_line_id')
        batch_op.drop_column('source_type')
        batch_op.drop_column('opal_number')

    with op.batch_alter_table('part', schema=None) as batch_op:
        batch_op.drop_column('tracking_type')
