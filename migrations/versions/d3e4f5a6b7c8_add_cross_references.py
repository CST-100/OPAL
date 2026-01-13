"""add_cross_references

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-01-05

Adds:
- IssueReference table for linking issues to OPAL/WO numbers
- RiskReference table for linking risks to OPAL/WO numbers
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ Create IssueReference Table ============
    op.create_table(
        'issue_reference',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('issue_id', sa.Integer(), nullable=False),
        sa.Column('reference_type', sa.String(20), nullable=False, comment='opal or work_order'),
        sa.Column('reference_value', sa.String(20), nullable=False, comment='The OPAL-XXXXX or WO-XXXXX value'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['issue_id'], ['issue.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('issue_id', 'reference_type', 'reference_value', name='uq_issue_reference_unique'),
    )
    op.create_index('ix_issue_reference_issue_id', 'issue_reference', ['issue_id'])
    op.create_index('ix_issue_reference_reference_value', 'issue_reference', ['reference_value'])

    # ============ Create RiskReference Table ============
    op.create_table(
        'risk_reference',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('risk_id', sa.Integer(), nullable=False),
        sa.Column('reference_type', sa.String(20), nullable=False, comment='opal or work_order'),
        sa.Column('reference_value', sa.String(20), nullable=False, comment='The OPAL-XXXXX or WO-XXXXX value'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['risk_id'], ['risk.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('risk_id', 'reference_type', 'reference_value', name='uq_risk_reference_unique'),
    )
    op.create_index('ix_risk_reference_risk_id', 'risk_reference', ['risk_id'])
    op.create_index('ix_risk_reference_reference_value', 'risk_reference', ['reference_value'])


def downgrade() -> None:
    # ============ Drop RiskReference Table ============
    op.drop_index('ix_risk_reference_reference_value', table_name='risk_reference')
    op.drop_index('ix_risk_reference_risk_id', table_name='risk_reference')
    op.drop_table('risk_reference')

    # ============ Drop IssueReference Table ============
    op.drop_index('ix_issue_reference_reference_value', table_name='issue_reference')
    op.drop_index('ix_issue_reference_issue_id', table_name='issue_reference')
    op.drop_table('issue_reference')
