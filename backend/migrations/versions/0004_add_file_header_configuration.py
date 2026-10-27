"""为已上传文件增加表头选择和列信息，既有记录保持未确认状态。

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27 19:16:04.930308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """只增加两个可空字段，不修改原文件信息或填入推测的表头。"""
    op.add_column('uploaded_files', sa.Column('has_header', sa.Boolean(), nullable=True))
    op.add_column('uploaded_files', sa.Column('columns', sa.JSON(none_as_null=True), nullable=True))


def downgrade() -> None:
    """删除新增字段及其中的表头设置，保留上传文件记录。"""
    op.drop_column('uploaded_files', 'columns')
    op.drop_column('uploaded_files', 'has_header')
