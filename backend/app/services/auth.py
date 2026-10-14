import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.models import User

logger = logging.getLogger("app.auth")


def register(db: Session, email: str, password: str, display_name: str | None) -> User:
    normalized = email.strip().lower()
    if db.scalar(select(User.id).where(User.email == normalized)) is not None:
        raise AppError("email_already_registered", "An account with this email already exists", 409)
    user = User(email=normalized, password_hash=hash_password(password), display_name=display_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # concurrent registration with the same email
        db.rollback()
        raise AppError(
            "email_already_registered", "An account with this email already exists", 409
        ) from None
    db.refresh(user)
    logger.info("user_registered", extra={"user_id": str(user.id)})
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    # verify_password always runs (against a dummy hash if needed) to keep timing uniform.
    valid = verify_password(user.password_hash if user else None, password)
    if user is None or not valid or not user.is_active:
        logger.info("login_failed")
        raise AppError("invalid_credentials", "Invalid email or password", 401)
    logger.info("login_succeeded", extra={"user_id": str(user.id)})
    return user
