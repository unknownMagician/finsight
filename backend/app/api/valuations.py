from fastapi import APIRouter, Response, status

from app.api.deps import ComputeRateLimit, CurrentUser, DbSession, parse_uuid, resolve_market
from app.domain.dcf import DCFInputs
from app.models import SavedValuation
from app.schemas import SavedValuationCreate, SavedValuationOut
from app.services import valuations as service

router = APIRouter(prefix="/valuations", tags=["valuations"])


def _out(valuation: SavedValuation) -> SavedValuationOut:
    return SavedValuationOut(
        id=valuation.id,
        name=valuation.name,
        ticker=valuation.company.ticker if valuation.company else None,
        market=valuation.company.market if valuation.company else None,
        method=valuation.method,
        engine_version=valuation.engine_version,
        inputs=DCFInputs.model_validate(valuation.inputs),
        result=valuation.result,
        created_at=valuation.created_at,
    )


@router.get("", response_model=list[SavedValuationOut])
def list_valuations(user: CurrentUser, db: DbSession) -> list[SavedValuationOut]:
    return [_out(v) for v in service.list_for(db, user)]


@router.post(
    "",
    response_model=SavedValuationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ComputeRateLimit],
)
def save_valuation(
    user: CurrentUser, db: DbSession, body: SavedValuationCreate
) -> SavedValuationOut:
    return _out(
        service.save(db, user, body.name, body.ticker, body.inputs, resolve_market(body.market))
    )


@router.get("/{valuation_id}", response_model=SavedValuationOut)
def get_valuation(user: CurrentUser, db: DbSession, valuation_id: str) -> SavedValuationOut:
    return _out(service.get_owned(db, user, parse_uuid(valuation_id, "Saved valuation")))


@router.delete("/{valuation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_valuation(user: CurrentUser, db: DbSession, valuation_id: str) -> Response:
    service.delete(db, user, parse_uuid(valuation_id, "Saved valuation"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
