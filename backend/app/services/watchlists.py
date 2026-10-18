"""Watchlists. Every query is scoped to the owner; another user's watchlist is a 404."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models import User, Watchlist, WatchlistItem
from app.services.companies import Market, get_company

MAX_WATCHLISTS_PER_USER = 20
MAX_ITEMS_PER_WATCHLIST = 100


def _not_found() -> AppError:
    return AppError("not_found", "Watchlist not found", 404)


def list_for(db: Session, owner: User) -> list[Watchlist]:
    stmt = (
        select(Watchlist)
        .where(Watchlist.owner_id == owner.id)
        .options(selectinload(Watchlist.items).selectinload(WatchlistItem.company))
        .order_by(Watchlist.created_at, Watchlist.name)
    )
    return list(db.scalars(stmt))


def get_owned(db: Session, owner: User, watchlist_id: uuid.UUID) -> Watchlist:
    watchlist = db.scalar(
        select(Watchlist)
        .where(Watchlist.id == watchlist_id, Watchlist.owner_id == owner.id)
        .options(selectinload(Watchlist.items).selectinload(WatchlistItem.company))
    )
    if watchlist is None:
        raise _not_found()
    return watchlist


def _ensure_unique_name(
    db: Session, owner: User, name: str, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(Watchlist.id).where(Watchlist.owner_id == owner.id, Watchlist.name == name)
    if exclude is not None:
        stmt = stmt.where(Watchlist.id != exclude)
    if db.scalar(stmt) is not None:
        raise AppError("watchlist_name_taken", "You already have a watchlist with this name", 409)


def create(db: Session, owner: User, name: str) -> Watchlist:
    count = db.scalar(select(func.count()).where(Watchlist.owner_id == owner.id)) or 0
    if count >= MAX_WATCHLISTS_PER_USER:
        raise AppError("limit_exceeded", f"At most {MAX_WATCHLISTS_PER_USER} watchlists", 409)
    _ensure_unique_name(db, owner, name)
    watchlist = Watchlist(owner_id=owner.id, name=name)
    db.add(watchlist)
    db.commit()
    return get_owned(db, owner, watchlist.id)


def rename(db: Session, owner: User, watchlist_id: uuid.UUID, name: str) -> Watchlist:
    watchlist = get_owned(db, owner, watchlist_id)
    _ensure_unique_name(db, owner, name, exclude=watchlist.id)
    watchlist.name = name
    db.commit()
    return get_owned(db, owner, watchlist_id)


def delete(db: Session, owner: User, watchlist_id: uuid.UUID) -> None:
    db.delete(get_owned(db, owner, watchlist_id))
    db.commit()


def add_company(
    db: Session, owner: User, watchlist_id: uuid.UUID, ticker: str, market: Market = "US"
) -> Watchlist:
    watchlist = get_owned(db, owner, watchlist_id)
    company = get_company(db, ticker, market)
    if any(item.company_id == company.id for item in watchlist.items):
        return watchlist  # idempotent
    if len(watchlist.items) >= MAX_ITEMS_PER_WATCHLIST:
        raise AppError("limit_exceeded", f"At most {MAX_ITEMS_PER_WATCHLIST} companies", 409)
    watchlist.items.append(WatchlistItem(company_id=company.id))
    db.commit()
    db.expire_all()
    return get_owned(db, owner, watchlist_id)


def remove_company(
    db: Session, owner: User, watchlist_id: uuid.UUID, ticker: str, market: Market = "US"
) -> Watchlist:
    watchlist = get_owned(db, owner, watchlist_id)
    remaining = [
        i
        for i in watchlist.items
        if not (i.company.ticker == ticker.upper() and i.company.market == market)
    ]
    if len(remaining) == len(watchlist.items):
        raise AppError("not_found", f"{ticker.upper()} is not in this watchlist", 404)
    watchlist.items = remaining
    db.commit()
    db.expire_all()
    return get_owned(db, owner, watchlist_id)
