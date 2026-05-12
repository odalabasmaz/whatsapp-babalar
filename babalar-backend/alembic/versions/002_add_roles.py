"""add role and daily_limit_override to users

Revision ID: 002
Revises: 001
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="member"))
    op.add_column("users", sa.Column("daily_limit_override", sa.Integer(), nullable=True))

    # Migrate existing is_admin → role
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin = true")
    # Promote the first registered user to owner — adjust username via CLI after migration:
    #   docker compose exec backend python -m app.cli setup
    op.execute("UPDATE users SET role = 'owner' WHERE id = (SELECT id FROM users ORDER BY created_at LIMIT 1)")

    op.drop_column("users", "is_admin")


def downgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"))
    op.execute("UPDATE users SET is_admin = true WHERE role IN ('admin', 'owner')")
    op.drop_column("users", "daily_limit_override")
    op.drop_column("users", "role")
