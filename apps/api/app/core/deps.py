import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import decode_token
from app.models import User, UserRole

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = AppError(401, "unauthorized", "Token inválido o expirado")
    if credentials is None:
        raise unauthorized
    payload = decode_token(credentials.credentials, "access")
    if payload is None:
        raise unauthorized
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise AppError(403, "forbidden", "Tu rol no permite esta acción")
        return user

    return _check


EditorUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.EDITOR))]
