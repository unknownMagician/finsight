from fastapi import APIRouter, status

from app.api.deps import AuthRateLimit, CurrentUser, DbSession
from app.core.security import create_access_token
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AuthRateLimit],
)
def register(body: RegisterRequest, db: DbSession) -> UserOut:
    user = auth_service.register(db, body.email, body.password, body.display_name)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse, dependencies=[AuthRateLimit])
def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    user = auth_service.authenticate(db, body.email, body.password)
    token, expires_in = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
