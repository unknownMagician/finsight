"""Stateless calculators exposing the domain engine. Inputs are validated by the domain models;
cross-object rule violations (ValueError) become 422 ``invalid_assumptions``."""

from collections.abc import Callable

from fastapi import APIRouter

from app.api.deps import ComputeRateLimit, CurrentUser
from app.core.errors import AppError
from app.domain.comps import CompsResult, analyze_comps
from app.domain.dcf import DCFInputs, DCFResult, SensitivityTable, run_dcf, sensitivity
from app.domain.forecast import ScenarioSetResult, run_scenarios
from app.domain.wacc import WACCInputs, WACCResult, compute_wacc
from app.schemas import CompsRequest, ForecastRequest, SensitivityRequest

router = APIRouter(prefix="/calculations", tags=["calculations"], dependencies=[ComputeRateLimit])


def _domain[T](fn: Callable[[], T]) -> T:
    try:
        return fn()
    except ValueError as exc:
        raise AppError("invalid_assumptions", str(exc), 422) from None


@router.post("/wacc", response_model=WACCResult)
def wacc(_: CurrentUser, body: WACCInputs) -> WACCResult:
    return _domain(lambda: compute_wacc(body))


@router.post("/dcf", response_model=DCFResult)
def dcf(_: CurrentUser, body: DCFInputs) -> DCFResult:
    return _domain(lambda: run_dcf(body))


@router.post("/dcf/sensitivity", response_model=SensitivityTable)
def dcf_sensitivity(_: CurrentUser, body: SensitivityRequest) -> SensitivityTable:
    return _domain(
        lambda: sensitivity(body.inputs, body.wacc_values, body.column_values, body.output)
    )


@router.post("/forecast", response_model=ScenarioSetResult)
def forecast(_: CurrentUser, body: ForecastRequest) -> ScenarioSetResult:
    return _domain(lambda: run_scenarios(body.base, body.scenarios))


@router.post("/comps", response_model=CompsResult)
def comps(_: CurrentUser, body: CompsRequest) -> CompsResult:
    return _domain(lambda: analyze_comps(body.target, body.peers, body.multiples))
