"""add_genealogy_and_alias

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-01-05

Adds:
- AssemblyComponent table for tracking component genealogy
- produced_opal_number to InventoryProduction
- alias field to InventoryRecord for sensor/equipment naming
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ Create AssemblyComponent Table ============
    op.create_table(
        'assembly_component',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('production_id', sa.Integer(), nullable=False,
                  comment='The production record (assembly being built)'),
        sa.Column('consumption_id', sa.Integer(), nullable=False,
                  comment='The consumption record (component used)'),
        sa.Column('component_opal_number', sa.String(20), nullable=False,
                  comment='OPAL number of the consumed component (denormalized)'),
        sa.Column('quantity_used', sa.Numeric(precision=15, scale=4), nullable=False,
                  comment='Quantity of this component used'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['production_id'], ['inventory_production.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['consumption_id'], ['inventory_consumption.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_assembly_component_production_id', 'assembly_component', ['production_id'])
    op.create_index('ix_assembly_component_consumption_id', 'assembly_component', ['consumption_id'])
    op.create_index('ix_assembly_component_component_opal_number', 'assembly_component', ['component_opal_number'])

    # ============ Add produced_opal_number to InventoryProduction ============
    with op.batch_alter_table('inventory_production', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'produced_opal_number', sa.String(20), nullable=True,
            comment='OPAL number assigned to the produced assembly'
        ))
        batch_op.create_index('ix_inventory_production_produced_opal_number', ['produced_opal_number'])

    # ============ Add alias to InventoryRecord ============
    with op.batch_alter_table('inventory_record', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'alias', sa.String(100), nullable=True,
            comment="Human-readable name like 'Coolant Temp Sensor #1'"
        ))
        batch_op.create_index('ix_inventory_record_alias', ['alias'])


def downgrade() -> None:
    # ============ Remove alias from InventoryRecord ============
    with op.batch_alter_table('inventory_record', schema=None) as batch_op:
        batch_op.drop_index('ix_inventory_record_alias')
        batch_op.drop_column('alias')

    # ============ Remove produced_opal_number from InventoryProduction ============
    with op.batch_alter_table('inventory_production', schema=None) as batch_op:
        batch_op.drop_index('ix_inventory_production_produced_opal_number')
        batch_op.drop_column('produced_opal_number')

    # ============ Drop AssemblyComponent Table ============
    op.drop_index('ix_assembly_component_component_opal_number', table_name='assembly_component')
    op.drop_index('ix_assembly_component_consumption_id', table_name='assembly_component')
    op.drop_index('ix_assembly_component_production_id', table_name='assembly_component')
    op.drop_table('assembly_component')
