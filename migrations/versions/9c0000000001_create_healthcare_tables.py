"""create healthcare tables

Revision ID: 9c0000000001
Revises: 9b41b9c466da
Create Date: 2026-09-19
"""

from typing import Sequence, Union

from alembic import op


# Revision identifiers, used by Alembic.
revision: str = "9c0000000001"
down_revision: Union[str, Sequence[str], None] = "9b41b9c466da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all SQLAlchemy model tables."""

    # Import the models so they are registered in Base.metadata.
    import backend.app.models

    from backend.app.core.database import Base

    bind = op.get_bind()

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop all SQLAlchemy model tables."""

    import backend.app.models

    from backend.app.core.database import Base

    bind = op.get_bind()

    Base.metadata.drop_all(bind=bind)
