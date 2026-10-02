import secrets
import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import Organization, User, UserRole
from app.schemas.auth import (
    AuthOptions,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens_for(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, user.organization_id, user.role, "access"),
        refresh_token=create_token(user.id, user.organization_id, user.role, "refresh"),
    )


@router.get("/options", response_model=AuthOptions)
async def options() -> AuthOptions:
    """Qué formas de acceso ofrece la pantalla de login. Sirve también para despertar el
    servidor en planes gratuitos que lo duermen."""
    return AuthOptions(
        registration=settings.allow_registration, demo=bool(settings.demo_owner_email)
    )


@router.post("/demo", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def demo(db: DbSession) -> TokenPair:
    """Crea un visitante (viewer) en la organización demo: ve y consulta los documentos
    compartidos, con sus propias conversaciones, pero no puede subir ni borrar."""
    owner_email = (settings.demo_owner_email or "").lower()
    owner = await db.scalar(select(User).where(User.email == owner_email)) if owner_email else None
    if owner is None:
        raise AppError(404, "demo_unavailable", "La demo no está disponible")
    visitor = User(
        organization_id=owner.organization_id,
        email=f"visitante-{uuid.uuid4().hex[:10]}@demo.findocs",
        password_hash=hash_password(secrets.token_urlsafe(24)),
        role=UserRole.VIEWER,
    )
    db.add(visitor)
    await db.commit()
    return _tokens_for(visitor)


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbSession) -> TokenPair:
    """Crea una organización nueva y su usuario administrador."""
    if not settings.allow_registration:
        raise AppError(403, "registration_closed", "El registro está cerrado en esta demo")
    email = body.email.lower()
    exists = await db.scalar(select(func.count()).select_from(User).where(User.email == email))
    if exists:
        raise AppError(409, "email_taken", "Ya existe una cuenta con ese email")

    org = Organization(name=body.organization_name)
    db.add(org)
    await db.flush()
    user = User(
        organization_id=org.id,
        email=email,
        password_hash=hash_password(body.password),
        role=UserRole.ADMIN,
    )
    db.add(user)
    await db.commit()
    return _tokens_for(user)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, db: DbSession) -> TokenPair:
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Email o contraseña incorrectos")
    return _tokens_for(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: DbSession) -> TokenPair:
    payload = decode_token(body.refresh_token, "refresh")
    user = await db.get(User, uuid.UUID(payload["sub"])) if payload else None
    if user is None:
        raise AppError(401, "unauthorized", "Refresh token inválido o expirado")
    return _tokens_for(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser, db: DbSession) -> UserOut:
    org = await db.get(Organization, user.organization_id)
    assert org is not None
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        organization_id=org.id,
        organization_name=org.name,
    )
