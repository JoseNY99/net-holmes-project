"""Modelo SQLAlchemy para la tabla de perfil_investigacion."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base

RECOLECCION_FIELDS = (
    "dni_cedula",
    "cuit_cuil_ruc",
    "banco",
    "alias_bancario",
    "cvu_cbu",
    "email",
    "direccion_exacta",
    "telefono_privado",
    "precio_final_cotizado",
)

class PerfilInvestigacion(Base):
    __tablename__ = "perfil_investigacion"

    id = Column(Integer, primary_key=True, index=True)
    reporte_id = Column(Integer, ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Bloque 1: Identidad y Fiscalidad
    dni_cedula = Column(String(50), nullable=True)
    cuit_cuil_ruc = Column(String(50), nullable=True)
    
    # Bloque 2: Trazabilidad Financiera
    banco = Column(String(200), nullable=True)
    alias_bancario = Column(String(200), nullable=True)
    cvu_cbu = Column(String(50), nullable=True)
    
    # Bloque 3: Contacto y Cierre Transaccional
    email = Column(String(255), nullable=True)
    direccion_exacta = Column(Text, nullable=True)
    telefono_privado = Column(String(50), nullable=True)
    precio_final_cotizado = Column(String(100), nullable=True)
    
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

    # Relaciones
    reporte = relationship("ReporteBrandDefense", back_populates="perfil", lazy="select")

    @property
    def progreso_recoleccion(self) -> int:
        completados = sum(
            bool((getattr(self, campo) or "").strip())
            for campo in RECOLECCION_FIELDS
        )
        return round(completados * 100 / len(RECOLECCION_FIELDS))

    @property
    def umbral_80_alcanzado(self) -> bool:
        return self.progreso_recoleccion >= 80
