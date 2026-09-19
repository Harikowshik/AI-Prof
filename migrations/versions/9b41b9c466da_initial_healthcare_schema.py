"""initial_healthcare_schema

Revision ID: 9b41b9c466da
Revises:
Create Date: 2026-09-16 15:31:21.534528

"""

from typing import Sequence, Union

from alembic import op


# Revision identifiers, used by Alembic.
revision: str = "9b41b9c466da"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create all database tables defined by the SQLAlchemy models.
    """

    # Import models so all model classes are registered
    # in Base.metadata before create_all() runs.
    import backend.app.models

    from backend.app.core.database import Base

    bind = op.get_bind()

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """
    Drop all database tables defined by the SQLAlchemy models.
    """

    import backend.app.models

    from backend.app.core.database import Base

    bind = op.get_bind()

    Base.metadata.drop_all(bind=bind)
