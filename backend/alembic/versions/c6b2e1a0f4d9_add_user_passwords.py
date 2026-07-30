"""add user passwords

Revision ID: c6b2e1a0f4d9
Revises: b84f2a91c703
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa


revision: str = "c6b2e1a0f4d9"
down_revision: str | None = "b84f2a91c703"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_password" in inspector.get_table_names():
        return

    op.create_table(
        "user_password",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_password" in inspector.get_table_names():
        op.drop_table("user_password")
