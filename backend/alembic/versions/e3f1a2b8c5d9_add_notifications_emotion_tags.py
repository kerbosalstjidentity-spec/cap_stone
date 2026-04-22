"""Add notifications and emotion_tags tables.

Revision ID: e3f1a2b8c5d9
Revises: d7a6cc6009f9
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f1a2b8c5d9'
down_revision = 'd7a6cc6009f9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # notifications 테이블
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('body', sa.Text(), nullable=False, server_default=''),
        sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notif_user_created', 'notifications', ['user_id', 'created_at'])
    op.create_index('ix_notif_user_unread', 'notifications', ['user_id', 'is_read'])

    # emotion_tags 테이블
    op.create_table(
        'emotion_tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('transaction_id', sa.String(128), nullable=False),
        sa.Column('emotion', sa.String(16), nullable=False),
        sa.Column('intensity', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.transaction_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_emotion_user_tx', 'emotion_tags', ['user_id', 'transaction_id'], unique=True)
    op.create_index('ix_emotion_user_emotion', 'emotion_tags', ['user_id', 'emotion'])


def downgrade() -> None:
    op.drop_index('ix_emotion_user_emotion', table_name='emotion_tags')
    op.drop_index('ix_emotion_user_tx', table_name='emotion_tags')
    op.drop_table('emotion_tags')
    op.drop_index('ix_notif_user_unread', table_name='notifications')
    op.drop_index('ix_notif_user_created', table_name='notifications')
    op.drop_table('notifications')
