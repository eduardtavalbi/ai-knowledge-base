import asyncio
import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.user_session import UserSession, SessionRefreshToken
from app.models.account_action_token import AccountActionToken
from app.services.email import send_account_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
password_hasher = PasswordHash.recommended()
ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 30
REFRESH_TOKEN_REUSE_GRACE_SECONDS = 10
REFRESH_COOKIE_NAME = "mindbase_refresh"
EMAIL_VERIFICATION_TOKEN_HOURS = 24
PASSWORD_RESET_TOKEN_MINUTES = 60


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("A valid email address is required")
        return normalized


class UserResponse(BaseModel):
    id: int
    email: str
    email_verified: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SessionResponse(BaseModel):
    id: int
    created_at: datetime
    expires_at: datetime


class EmailTokenRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


def _secret_key() -> str:
    secret = settings.auth_secret_key
    if len(secret) < 32 or secret == "CHANGE_ME_USE_A_RANDOM_SECRET_AT_LEAST_32_CHARACTERS":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    return secret


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _new_action_token() -> str:
    return secrets.token_urlsafe(32)


def _email_delivery_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


async def _create_action_token(
    user: User,
    db: AsyncSession,
    purpose: str,
    expires_in: timedelta,
) -> str:
    existing = await db.execute(
        select(AccountActionToken).where(
            AccountActionToken.user_id == user.id,
            AccountActionToken.purpose == purpose,
            AccountActionToken.used_at.is_(None),
        )
        .with_for_update()
    )
    now = _now()
    for record in existing.scalars().all():
        record.used_at = now
    raw_token = _new_action_token()
    db.add(AccountActionToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=_hash_refresh_token(raw_token),
        expires_at=now + expires_in,
    ))
    await db.commit()
    return raw_token


async def _send_action_email(user: User, token: str, purpose: str) -> None:
    base_url = settings.frontend_public_url.rstrip("/")
    if purpose == "email_verification":
        subject = "Подтвердите email в Mindbase"
        link = f"{base_url}/?verify={token}"
        message = (
            "Чтобы подтвердить адрес электронной почты в Mindbase, откройте ссылку:\n\n"
            f"{link}\n\nСсылка действительна 24 часа. Если вы не создавали аккаунт, "
            "просто проигнорируйте это письмо."
        )
    else:
        subject = "Восстановление пароля Mindbase"
        link = f"{base_url}/?reset={token}"
        message = (
            "Чтобы установить новый пароль Mindbase, откройте ссылку:\n\n"
            f"{link}\n\nСсылка действительна 60 минут. Если вы не запрашивали "
            "сброс пароля, просто проигнорируйте это письмо."
        )
    await send_account_email(user.email, subject, message)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_token_cookie_secure,
        samesite="lax",
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/auth",
        httponly=True,
        secure=settings.refresh_token_cookie_secure,
        samesite="lax",
    )


def _validate_browser_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        return
    allowed_origins = {
        value.strip().rstrip("/")
        for value in settings.frontend_origins.split(",")
        if value.strip()
    }
    if origin.rstrip("/") not in allowed_origins:
        raise HTTPException(status_code=403, detail="Untrusted request origin")


def _create_access_token(user_id: int, session_id: int) -> str:
    now = _now()
    expires = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": session_id,
            "exp": expires,
            "iat": now,
        },
        _secret_key(),
        algorithm="HS256",
    )


def _token_response(user_id: int, session_id: int) -> TokenResponse:
    return TokenResponse(
        access_token=_create_access_token(user_id, session_id),
        expires_in=ACCESS_TOKEN_MINUTES * 60,
    )


def _set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _secret_key(), algorithms=["HS256"])
        user_id = int(payload["sub"])
        session_id = int(payload["sid"])
        if user_id <= 0 or session_id <= 0:
            raise ValueError("Invalid token subject")
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise credentials_error

    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if session is None or _aware(session.expires_at) <= _now():
        raise credentials_error

    user = await db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    verification_required = settings.email_verification_required
    if verification_required and not _email_delivery_configured():
        raise HTTPException(
            status_code=503,
            detail="Email delivery is not configured",
        )

    user = User(
        email=request.email,
        hashed_password=await asyncio.to_thread(password_hasher.hash, request.password),
        email_verified=not verification_required,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists",
        ) from exc

    if verification_required:
        token = await _create_action_token(
            user, db, "email_verification",
            timedelta(hours=EMAIL_VERIFICATION_TOKEN_HOURS),
        )
        try:
            await _send_action_email(user, token, "email_verification")
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Account created, but verification email could not be sent. Request a new verification email.",
            ) from exc
    return user


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AccountActionToken)
        .where(
            AccountActionToken.token_hash == _hash_refresh_token(request.token),
            AccountActionToken.purpose == "email_verification",
        )
        .with_for_update()
    )
    token_record = result.scalar_one_or_none()
    if token_record is None or _aware(token_record.expires_at) <= _now():
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired")

    user = await db.get(User, token_record.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired")
    if token_record.used_at is not None:
        if user.email_verified:
            return user
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired")
    token_record.used_at = _now()
    user.email_verified = True
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/resend-verification", status_code=202)
async def resend_verification(
    request: EmailTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    if not settings.email_verification_required:
        return {"message": "If the account requires verification, an email will be sent."}
    if not _email_delivery_configured():
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    if user is not None and not user.email_verified:
        token = await _create_action_token(
            user, db, "email_verification",
            timedelta(hours=EMAIL_VERIFICATION_TOKEN_HOURS),
        )
        try:
            await _send_action_email(user, token, "email_verification")
        except Exception:
            logger.warning("Verification email delivery failed")
    return {"message": "If the account requires verification, an email will be sent."}


@router.post("/forgot-password", status_code=202)
async def forgot_password(
    request: EmailTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    if not _email_delivery_configured():
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    if user is not None:
        token = await _create_action_token(
            user, db, "password_reset",
            timedelta(minutes=PASSWORD_RESET_TOKEN_MINUTES),
        )
        try:
            await _send_action_email(user, token, "password_reset")
        except Exception:
            logger.warning("Password reset email delivery failed")
    return {"message": "If an account with this email exists, a password reset email will be sent."}


@router.post("/reset-password", status_code=204)
async def reset_password(
    request: PasswordResetRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AccountActionToken)
        .where(
            AccountActionToken.token_hash == _hash_refresh_token(request.token),
            AccountActionToken.purpose == "password_reset",
        )
        .with_for_update()
    )
    token_record = result.scalar_one_or_none()
    if (
        token_record is None
        or token_record.used_at is not None
        or _aware(token_record.expires_at) <= _now()
    ):
        raise HTTPException(status_code=400, detail="Password reset link is invalid or expired")

    user = await db.get(User, token_record.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Password reset link is invalid or expired")

    user.hashed_password = await asyncio.to_thread(password_hasher.hash, request.new_password)
    token_record.used_at = _now()
    other_tokens = await db.execute(
        select(AccountActionToken).where(
            AccountActionToken.user_id == user.id,
            AccountActionToken.used_at.is_(None),
        )
    )
    for other_token in other_tokens.scalars().all():
        other_token.used_at = _now()

    sessions = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
    )
    for session in sessions.scalars().all():
        session.revoked_at = _now()

    await db.commit()
    response.status_code = 204
    return response


async def _create_session(user: User, db: AsyncSession) -> tuple[UserSession, str]:
    refresh_token = _new_refresh_token()
    token_hash = _hash_refresh_token(refresh_token)
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=token_hash,
        expires_at=_now() + timedelta(days=REFRESH_TOKEN_DAYS),
    )
    db.add(session)
    await db.flush()
    db.add(SessionRefreshToken(session_id=session.id, token_hash=token_hash))
    await db.commit()
    await db.refresh(session)
    return session, refresh_token


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    _validate_browser_origin(request)
    email = form.username.strip().casefold()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if user is None or not await asyncio.to_thread(
        password_hasher.verify,
        form.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if settings.email_verification_required and not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address before signing in",
        )

    session, refresh_token = await _create_session(user, db)
    _set_refresh_cookie(response, refresh_token)
    _set_no_store_headers(response)
    return _token_response(user.id, session.id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    _validate_browser_origin(request)
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token is missing")

    token_hash = _hash_refresh_token(refresh_token)
    token_result = await db.execute(
        select(SessionRefreshToken)
        .where(SessionRefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    token_record = token_result.scalar_one_or_none()
    if token_record is None:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    session_result = await db.execute(
        select(UserSession)
        .where(UserSession.id == token_record.session_id)
        .with_for_update()
    )
    session = session_result.scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token_record.used_at is not None:
        # Another browser tab may have refreshed with the same cookie at nearly
        # the same time. Give it a short retry window before treating reuse as
        # a compromised token family.
        if _now() - _aware(token_record.used_at) <= timedelta(
            seconds=REFRESH_TOKEN_REUSE_GRACE_SECONDS
        ):
            raise HTTPException(
                status_code=409,
                detail="Refresh token was already rotated",
                headers={"Retry-After": "0.1"},
            )
        session.revoked_at = _now()
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Refresh token reuse detected")

    if _aware(session.expires_at) <= _now():
        session.revoked_at = _now()
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = await db.get(User, session.user_id)
    if user is None:
        session.revoked_at = _now()
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    replacement = _new_refresh_token()
    replacement_hash = _hash_refresh_token(replacement)
    token_record.used_at = _now()
    session.refresh_token_hash = replacement_hash
    db.add(SessionRefreshToken(session_id=session.id, token_hash=replacement_hash))
    await db.commit()
    _set_refresh_cookie(response, replacement)
    _set_no_store_headers(response)
    return _token_response(user.id, session.id)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    _validate_browser_origin(request)
    # A short-lived access token may already be expired when the user logs out.
    # The HttpOnly refresh cookie is an independent proof of the session.
    bearer = request.headers.get("Authorization", "")
    token_session_id: int | None = None
    token_user_id: int | None = None
    if bearer.lower().startswith("bearer "):
        try:
            payload = jwt.decode(
                bearer[7:].strip(),
                _secret_key(),
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            token_session_id = int(payload["sid"])
            token_user_id = int(payload["sub"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            token_session_id = None
            token_user_id = None

    cookie_session_id: int | None = None
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        token_result = await db.execute(
            select(SessionRefreshToken).where(
                SessionRefreshToken.token_hash == _hash_refresh_token(refresh_token)
            )
        )
        refresh_record = token_result.scalar_one_or_none()
        if refresh_record is not None:
            cookie_session_id = refresh_record.session_id

    if (
        token_session_id is not None
        and cookie_session_id is not None
        and token_session_id != cookie_session_id
    ):
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Session credentials do not match")

    session_id = token_session_id or cookie_session_id
    if session_id is not None:
        query = select(UserSession).where(UserSession.id == session_id)
        if token_user_id is not None:
            query = query.where(UserSession.user_id == token_user_id)
        result = await db.execute(query)
        session = result.scalar_one_or_none()
        if session is not None and session.revoked_at is None:
            session.revoked_at = _now()
            await db.commit()

    _clear_refresh_cookie(response)
    response.status_code = 204
    return response


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > _now(),
        )
        .order_by(UserSession.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.revoked_at is None:
        session.revoked_at = _now()
        await db.commit()
    response.status_code = 204
    return response


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user
