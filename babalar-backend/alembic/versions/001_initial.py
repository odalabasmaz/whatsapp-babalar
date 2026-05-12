"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID, primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("invite_code", sa.String(50)),
        sa.Column("is_admin", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.UUID, primary_key=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("max_uses", sa.Integer, default=10),
        sa.Column("use_count", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "wa_groups",
        sa.Column("id", sa.UUID, primary_key=True),
        sa.Column("wa_group_id", sa.String(255), unique=True, nullable=False),
        sa.Column("group_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID, primary_key=True),
        sa.Column("group_id", sa.UUID, sa.ForeignKey("wa_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_name", sa.String(255)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("category", sa.String(100)),
        sa.Column("embedding", Vector(1536)),
    )
    op.create_index("messages_embedding_hnsw", "messages", ["embedding"], postgresql_using="hnsw",
                    postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"})
    op.create_index("messages_category_idx", "messages", ["category"])
    op.create_index("messages_sent_at_idx", "messages", ["sent_at"])

    op.create_table(
        "user_daily_usage",
        sa.Column("user_id", sa.UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("usage_date", sa.Date, primary_key=True),
        sa.Column("count", sa.Integer, default=0),
    )

    op.create_table(
        "daily_total_usage",
        sa.Column("usage_date", sa.Date, primary_key=True),
        sa.Column("count", sa.Integer, default=0),
    )

    op.create_table(
        "admin_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.bulk_insert(
        sa.table("admin_config", sa.column("key", sa.String), sa.column("value", sa.String)),
        [
            {"key": "user_daily_limit", "value": "5"},
            {"key": "total_daily_limit", "value": "5000"},
            {"key": "rag_top_k", "value": "10"},
            {"key": "ingestion_lookback_days", "value": "30"},
        ],
    )


def downgrade():
    op.drop_table("admin_config")
    op.drop_table("daily_total_usage")
    op.drop_table("user_daily_usage")
    op.drop_table("messages")
    op.drop_table("wa_groups")
    op.drop_table("invite_codes")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
