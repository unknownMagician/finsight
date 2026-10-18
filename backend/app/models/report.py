import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.company import Company
from app.models.mixins import TimestampMixin


class ResearchReport(TimestampMixin, Base):
    """An immutable snapshot of a company report as generated (figures + provenance as JSON)."""

    __tablename__ = "research_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)  # as of generation
    includes_ai: Mapped[bool] = mapped_column(Boolean, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)

    company: Mapped[Company | None] = relationship()
