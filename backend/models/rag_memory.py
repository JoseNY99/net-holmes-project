"""Modelo SQLAlchemy para la Memoria RAG de Falsos Positivos."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class RagMemory(Base):
    __tablename__ = "rag_memory"

    id = Column(Integer, primary_key=True, index=True)
    tipo_entidad = Column(String(50), nullable=False) # ej. "username", "keyword"
    valor = Column(String(300), nullable=False, index=True)
    agregado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relación opcional con el usuario que lo agregó
    admin = relationship("User", foreign_keys=[agregado_por])
