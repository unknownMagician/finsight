"""ORM models. Import every model module here so Alembic autogenerate can see it.

Phase 1 ships no domain tables yet; they arrive with Phases 2-3.
"""

from app.db.base import Base

__all__ = ["Base"]
