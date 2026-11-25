import asyncio
import hashlib
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

router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
password_hasher = PasswordHash.recommended()
ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 30
REFRESH_COOKIE_NAME = "mindbase_refresh"


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\\s@]+@[^\\s@]+\\.[^\\s@]+", normalized):
            raise ValueError("A valid email address is required")
        return normalized


class UserResponse(BaseModel):
    id: int
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SessionResponse(BaseModel):
    id: int
    created_at: datetime
    expires_at: datetime


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
    user = User(
        email=request.email,
        hashed_password=await asyncio.to_thread(password_hasher.hash, request.password),
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
    return user


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
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
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

    session, refresh_token = await _create_session(user, db)
    _set_refresh_cookie(response, refresh_token)
    return _token_response(user.id, session.id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
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
    return _token_response(user.id, session.id)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = jwt.decode(token, _secret_key(), algorithms=["HS256"])
        session_id = int(payload["sid"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    session = await db.get(UserSession, session_id)
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
