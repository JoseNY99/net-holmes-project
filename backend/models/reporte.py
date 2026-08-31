"""Modelo SQLAlchemy para la tabla principal de reportes_brand_defense (Fase 1)."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship

from database import Base

class ReporteBrandDefense(Base):
    __tablename__ = "reportes_brand_defense"

    id = Column(Integer, primary_key=True, index=True)
    
    pais = Column(String(100), nullable=False)
    referencia_interna = Column(String(100), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    producto_catalogo = Column(String(255), nullable=False)
    marca_afectada = Column(String(255), nullable=False)
    plataforma = Column(String(50), nullable=False)  # Instagram, Facebook, TikTok, MercadoLibre
    
    fecha_captura = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    
    titular_cuenta = Column(String(255), nullable=False)
    url_evidencia = Column(Text, nullable=False)
    descripcion_post = Column(Text, nullable=True)
    
    precio_publico = Column(Numeric(10, 2), nullable=True)
    direccion_publica = Column(String(255), nullable=True)
    telefono_publico = Column(String(100), nullable=True)
    seguidores_infractor = Column(Integer, nullable=True)
    
    estado = Column(String(50), nullable=False, default="Pendiente") # Pendiente, Sospechoso, Descartado
    
    # Audit trail (opcional)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relación con perfil de investigación (Fase 2)
    perfil = relationship("PerfilInvestigacion", uselist=False, back_populates="reporte", lazy="joined", cascade="all, delete-orphan")
    # Relación con logs de auditoría
    audit_logs = relationship("AuditLog", back_populates="reporte", lazy="select", cascade="all, delete-orphan")
