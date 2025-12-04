"""Add cascade delete to WebsiteStats and TaskRecord

Revision ID: 0656b3ec6c79
Revises: 
Create Date: 2025-11-27 09:33:06.858415

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0656b3ec6c79'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Supprimer anciennes contraintes
    op.drop_constraint(
        "website_stats_user_id_fkey",
        "website_stats",
        type_="foreignkey"
    )

    op.drop_constraint(
        "task_record_user_id_fkey",
        "task_record",
        type_="foreignkey"
    )

    # Recréer avec cascade
    op.create_foreign_key(
        "website_stats_user_id_fkey",
        "website_stats",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE"
    )

    op.create_foreign_key(
        "task_record_user_id_fkey",
        "task_record",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE"
    )


def downgrade():
    # Supprimer contraintes CASCADE
    op.drop_constraint(
        "website_stats_user_id_fkey",
        "website_stats",
        type_="foreignkey"
    )

    op.drop_constraint(
        "task_record_user_id_fkey",
        "task_record",
        type_="foreignkey"
    )

    # Recréer sans cascade
    op.create_foreign_key(
        "website_stats_user_id_fkey",
        "website_stats",
        "user",
        ["user_id"],
        ["id"]
    )

    op.create_foreign_key(
        "task_record_user_id_fkey",
        "task_record",
        "user",
        ["user_id"],
        ["id"]
    )
