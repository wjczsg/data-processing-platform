"""新增处理任务表，关联上传文件和所属用户。

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 15:13:12.884829

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """仅新增任务表和索引，不插入任务或修改已有业务数据。"""
    op.create_table('processing_tasks',
    sa.Column('id', sa.String(length=32, collation='utf8mb4_bin'), nullable=False),
    sa.Column('file_id', sa.String(length=32, collation='utf8mb4_bin'), nullable=False),
    sa.Column('owner_id', mysql.BIGINT(unsigned=True), nullable=False),
    sa.Column('status', sa.String(length=16, collation='utf8mb4_bin'), server_default=sa.text("'pending'"), nullable=False),
    sa.Column('created_at', mysql.DATETIME(fsp=6), nullable=False),
    sa.Column('updated_at', mysql.DATETIME(fsp=6), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'running', 'succeeded', 'failed')", name=op.f('ck_processing_tasks_status')),
    sa.ForeignKeyConstraint(['file_id'], ['uploaded_files.id'], name=op.f('fk_processing_tasks_file_id_uploaded_files'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_processing_tasks_owner_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_processing_tasks')),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_0900_ai_ci',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_processing_tasks_file_id'), 'processing_tasks', ['file_id'], unique=False)
    op.create_index(op.f('ix_processing_tasks_owner_id'), 'processing_tasks', ['owner_id'], unique=False)


def downgrade() -> None:
    """删除任务表及其数据，保留已有文件、用户和登录会话。"""
    op.drop_index(op.f('ix_processing_tasks_owner_id'), table_name='processing_tasks')
    op.drop_index(op.f('ix_processing_tasks_file_id'), table_name='processing_tasks')
    op.drop_table('processing_tasks')
