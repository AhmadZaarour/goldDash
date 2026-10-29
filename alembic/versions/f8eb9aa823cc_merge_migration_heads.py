"""merge migration heads

Revision ID: f8eb9aa823cc
Revises: 6f08198a2d40, 84a8d77918be
Create Date: 2026-10-29 15:28:35.313980

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8eb9aa823cc'
down_revision: Union[str, Sequence[str], None] = ('6f08198a2d40', '84a8d77918be')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
