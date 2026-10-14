"""Saved DCF valuations. The result is always recomputed server-side from the inputs; a client
never supplies results. Queries are owner-scoped; another user's valuation is a 404."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import __version__
from app.core.errors import AppError
from app.domain.dcf import DCFInputs, run_dcf
from app.models import SavedValuation, User
from app.services.companies import get_by_ticker

MAX_SAVED_PER_USER = 200


def save(
    db: Session, owner: User, name: str, ticker: str | None, inputs: DCFInputs
) -> SavedValuation:
    count = db.scalar(select(func.count()).where(SavedValuation.owner_id == owner.id)) or 0
    if count >= MAX_SAVED_PER_USER:
        raise AppError("limit_exceeded", f"At most {MAX_SAVED_PER_USER} saved valuations", 409)
    company = get_by_ticker(db, ticker) if ticker else None
    result = run_dcf(inputs)
    valuation = SavedValuation(
        owner_id=owner.id,
        company_id=company.id if company else None,
        name=name,
        method="dcf",
        inputs=inputs.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        engine_version=__version__,
    )
    db.add(valuation)
    db.commit()
    return get_owned(db, owner, valuation.id)


def list_for(db: Session, owner: User) -> list[SavedValuation]:
    stmt = (
        select(SavedValuation)
        .where(SavedValuation.owner_id == owner.id)
        .options(selectinload(SavedValuation.company))
        .order_by(SavedValuation.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_owned(db: Session, owner: User, valuation_id: uuid.UUID) -> SavedValuation:
    valuation = db.scalar(
        select(SavedValuation)
        .where(SavedValuation.id == valuation_id, SavedValuation.owner_id == owner.id)
        .options(selectinload(SavedValuation.company))
    )
    if valuation is None:
        raise AppError("not_found", "Saved valuation not found", 404)
    return valuation


def delete(db: Session, owner: User, valuation_id: uuid.UUID) -> None:
    db.delete(get_owned(db, owner, valuation_id))
    db.commit()
