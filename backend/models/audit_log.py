"""Modelo SQLAlchemy para la tabla de audit_logs."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    reporte_id = Column(Integer, ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    campo = Column(String(100), nullable=False)
    valor_anterior = Column(Text, nullable=True)
    valor_nuevo = Column(Text, nullable=True)
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relaciones
    reporte = relationship("ReporteBrandDefense", back_populates="audit_logs", lazy="select")
    user = relationship("User", lazy="joined")
