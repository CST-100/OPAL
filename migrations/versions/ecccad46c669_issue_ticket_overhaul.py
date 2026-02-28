"""Issue ticket overhaul

Revision ID: ecccad46c669
Revises: de85a4fdcd2a
Create Date: 2026-02-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ecccad46c669"
down_revision: Union[str, None] = "de85a4fdcd2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create issue_comment table
    op.create_table(
        "issue_comment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issue.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issue_comment_issue_id", "issue_comment", ["issue_id"])

    # 2. Add new columns to issue table
    with op.batch_alter_table("issue") as batch_op:
        batch_op.add_column(sa.Column("root_cause", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("corrective_action", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("disposition_type", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("disposition_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("assigned_to_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("disposition_approved_by_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_issue_assigned_to", "user", ["assigned_to_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_foreign_key(
            "fk_issue_disposition_approved_by",
            "user",
            ["disposition_approved_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_issue_assigned_to_id", ["assigned_to_id"])

    # 3. Add issue_id to attachment table
    with op.batch_alter_table("attachment") as batch_op:
        batch_op.add_column(sa.Column("issue_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_attachment_issue", "issue", ["issue_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_index("ix_attachment_issue_id", ["issue_id"])

    # 4. Data migration: remap old status values
    op.execute("UPDATE issue SET status = 'investigating' WHERE status = 'in_progress'")
    op.execute("UPDATE issue SET status = 'disposition_approved' WHERE status = 'resolved'")


def downgrade() -> None:
    # Reverse data migration
    op.execute("UPDATE issue SET status = 'in_progress' WHERE status = 'investigating'")
    op.execute(
        "UPDATE issue SET status = 'resolved' WHERE status = 'disposition_approved'"
    )
    op.execute(
        "UPDATE issue SET status = 'open' WHERE status = 'disposition_pending'"
    )

    # Remove issue_id from attachment
    with op.batch_alter_table("attachment") as batch_op:
        batch_op.drop_index("ix_attachment_issue_id")
        batch_op.drop_constraint("fk_attachment_issue", type_="foreignkey")
        batch_op.drop_column("issue_id")

    # Remove new columns from issue
    with op.batch_alter_table("issue") as batch_op:
        batch_op.drop_index("ix_issue_assigned_to_id")
        batch_op.drop_constraint("fk_issue_disposition_approved_by", type_="foreignkey")
        batch_op.drop_constraint("fk_issue_assigned_to", type_="foreignkey")
        batch_op.drop_column("disposition_approved_by_id")
        batch_op.drop_column("assigned_to_id")
        batch_op.drop_column("disposition_notes")
        batch_op.drop_column("disposition_type")
        batch_op.drop_column("corrective_action")
        batch_op.drop_column("root_cause")

    # Drop issue_comment table
    op.drop_index("ix_issue_comment_issue_id", table_name="issue_comment")
    op.drop_table("issue_comment")
