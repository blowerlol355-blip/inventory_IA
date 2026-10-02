import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPk


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Organization(UUIDPk, CreatedAt, Base):
    """Un tenant por empresa. Todas las tablas de negocio cuelgan de aquí."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(20), default="free")

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(UUIDPk, CreatedAt, Base):
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.VIEWER)

    organization: Mapped[Organization] = relationship(back_populates="users")
