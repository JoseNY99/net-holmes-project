"""Modelo SQLAlchemy para la tabla de perfil_investigacion."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base

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
    def completitud(self) -> int:
        fields = (
            self.dni_cedula, self.cuit_cuil_ruc, self.banco, self.alias_bancario,
            self.cvu_cbu, self.email, self.direccion_exacta, self.telefono_privado,
            self.precio_final_cotizado,
        )
        completed = sum(1 for value in fields if value and str(value).strip())
        return round(completed / len(fields) * 100)
