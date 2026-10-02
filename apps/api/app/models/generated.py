import uuid
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPk


class GeneratedFile(UUIDPk, CreatedAt, Base):
    """Archivo creado por una herramienta del agente (conversión, ZIP, compresión).

    No se indexa para la búsqueda: es un resultado descargable, no un documento fuente.
    """

    __tablename__ = "generated_files"
    __table_args__ = (Index("ix_generated_files_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # "convert" | "zip" | "reduce"
    operation: Mapped[str] = mapped_column(String(20))
    # [{"id": ..., "filename": ...}] de los archivos de origen.
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
