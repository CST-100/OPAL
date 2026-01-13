"""add_tiers_requirements_bom

Revision ID: 78a35eabd240
Revises: d3e4f5a6b7c8
Create Date: 2026-01-10 19:17:43.264124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78a35eabd240'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create bom_lines table
    op.create_table('bom_lines',
        sa.Column('assembly_id', sa.Integer(), nullable=False, comment='The assembly (parent part)'),
        sa.Column('component_id', sa.Integer(), nullable=False, comment='The component (child part)'),
        sa.Column('quantity', sa.Integer(), nullable=False, comment='Number of this component in the assembly'),
        sa.Column('reference_designator', sa.String(length=50), nullable=True, comment='Reference designator (e.g., R1, C3, U2)'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['assembly_id'], ['part.id'], name='fk_bom_lines_assembly_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['component_id'], ['part.id'], name='fk_bom_lines_component_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bom_lines_assembly_id', 'bom_lines', ['assembly_id'], unique=False)
    op.create_index('ix_bom_lines_component_id', 'bom_lines', ['component_id'], unique=False)

    # Create part_requirements table
    op.create_table('part_requirements',
        sa.Column('part_id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.String(length=50), nullable=False, comment='Requirement ID from project config (e.g., REQ-001)'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='open, verified, waived, not_applicable'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('verified_by_id', sa.Integer(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['part_id'], ['part.id'], name='fk_part_requirements_part_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['verified_by_id'], ['user.id'], name='fk_part_requirements_verified_by_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_part_requirements_part_id', 'part_requirements', ['part_id'], unique=False)
    op.create_index('ix_part_requirements_requirement_id', 'part_requirements', ['requirement_id'], unique=False)

    # Add tier and parent_id columns to part table
    with op.batch_alter_table('part', schema=None) as batch_op:
        # Add tier with server_default for existing rows (default to tier 1 = Flight)
        batch_op.add_column(sa.Column('tier', sa.Integer(), nullable=False, server_default='1', comment='Inventory tier level (1=Flight, 2=Ground, 3=Loose)'))
        batch_op.add_column(sa.Column('parent_id', sa.Integer(), nullable=True, comment='Parent assembly this part belongs to'))
        batch_op.create_index('ix_part_parent_id', ['parent_id'], unique=False)
        batch_op.create_index('ix_part_tier', ['tier'], unique=False)
        batch_op.create_foreign_key('fk_part_parent_id', 'part', ['parent_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('part', schema=None) as batch_op:
        batch_op.drop_constraint('fk_part_parent_id', type_='foreignkey')
        batch_op.drop_index('ix_part_tier')
        batch_op.drop_index('ix_part_parent_id')
        batch_op.drop_column('parent_id')
        batch_op.drop_column('tier')

    op.drop_index('ix_part_requirements_requirement_id', table_name='part_requirements')
    op.drop_index('ix_part_requirements_part_id', table_name='part_requirements')
    op.drop_table('part_requirements')

    op.drop_index('ix_bom_lines_component_id', table_name='bom_lines')
    op.drop_index('ix_bom_lines_assembly_id', table_name='bom_lines')
    op.drop_table('bom_lines')
