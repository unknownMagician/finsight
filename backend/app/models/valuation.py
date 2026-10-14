import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.company import Company
from app.models.mixins import TimestampMixin


class SavedValuation(TimestampMixin, Base):
    """A user's saved DCF run: the exact inputs and the result computed from them."""

    __tablename__ = "saved_valuations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)  # "dcf"
    # Stored as JSON with Decimals serialized as strings, so no precision is lost.
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)

    company: Mapped[Company | None] = relationship()
