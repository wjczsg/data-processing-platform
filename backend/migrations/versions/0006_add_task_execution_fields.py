"""扩展任务执行字段和领取任务的联合索引。

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-29 14:18:38.079778

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """保留现有任务及状态；新增配置等字段为空，处理记录数默认为零。"""
    op.add_column('processing_tasks', sa.Column('input_config', sa.JSON(none_as_null=True), nullable=True))
    op.add_column('processing_tasks', sa.Column('processed_rows', mysql.BIGINT(unsigned=True), server_default=sa.text('0'), nullable=False))
    op.add_column('processing_tasks', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('processing_tasks', sa.Column('started_at', mysql.DATETIME(fsp=6), nullable=True))
    op.add_column('processing_tasks', sa.Column('finished_at', mysql.DATETIME(fsp=6), nullable=True))
    op.create_index('ix_processing_tasks_status_created_at_id', 'processing_tasks', ['status', 'created_at', 'id'], unique=False)


def downgrade() -> None:
    """删除本次字段及其中的数据和联合索引，保留任务原有字段与记录。"""
    op.drop_index('ix_processing_tasks_status_created_at_id', table_name='processing_tasks')
    op.drop_column('processing_tasks', 'finished_at')
    op.drop_column('processing_tasks', 'started_at')
    op.drop_column('processing_tasks', 'error_message')
    op.drop_column('processing_tasks', 'processed_rows')
    op.drop_column('processing_tasks', 'input_config')
