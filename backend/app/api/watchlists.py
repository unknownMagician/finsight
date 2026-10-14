from typing import Annotated

from fastapi import APIRouter, Path, Response, status

from app.api.deps import CurrentUser, DbSession, parse_uuid
from app.models import Watchlist
from app.schemas import (
    CompanyOut,
    WatchlistCreate,
    WatchlistItemAdd,
    WatchlistOut,
    WatchlistUpdate,
)
from app.services import watchlists as service

router = APIRouter(prefix="/watchlists", tags=["watchlists"])

TickerPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9.\-]{1,20}$")]


def _out(watchlist: Watchlist) -> WatchlistOut:
    return WatchlistOut(
        id=watchlist.id,
        name=watchlist.name,
        companies=[CompanyOut.model_validate(i.company) for i in watchlist.items],
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.get("", response_model=list[WatchlistOut])
def list_watchlists(user: CurrentUser, db: DbSession) -> list[WatchlistOut]:
    return [_out(w) for w in service.list_for(db, user)]


@router.post("", response_model=WatchlistOut, status_code=status.HTTP_201_CREATED)
def create_watchlist(user: CurrentUser, db: DbSession, body: WatchlistCreate) -> WatchlistOut:
    return _out(service.create(db, user, body.name))


@router.get("/{watchlist_id}", response_model=WatchlistOut)
def get_watchlist(user: CurrentUser, db: DbSession, watchlist_id: str) -> WatchlistOut:
    return _out(service.get_owned(db, user, parse_uuid(watchlist_id, "Watchlist")))


@router.patch("/{watchlist_id}", response_model=WatchlistOut)
def rename_watchlist(
    user: CurrentUser, db: DbSession, watchlist_id: str, body: WatchlistUpdate
) -> WatchlistOut:
    return _out(service.rename(db, user, parse_uuid(watchlist_id, "Watchlist"), body.name))


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(user: CurrentUser, db: DbSession, watchlist_id: str) -> Response:
    service.delete(db, user, parse_uuid(watchlist_id, "Watchlist"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{watchlist_id}/items", response_model=WatchlistOut)
def add_item(
    user: CurrentUser, db: DbSession, watchlist_id: str, body: WatchlistItemAdd
) -> WatchlistOut:
    return _out(service.add_company(db, user, parse_uuid(watchlist_id, "Watchlist"), body.ticker))


@router.delete("/{watchlist_id}/items/{ticker}", response_model=WatchlistOut)
def remove_item(
    user: CurrentUser, db: DbSession, watchlist_id: str, ticker: TickerPath
) -> WatchlistOut:
    return _out(service.remove_company(db, user, parse_uuid(watchlist_id, "Watchlist"), ticker))
