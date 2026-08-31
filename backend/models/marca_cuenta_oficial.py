"""Modelo SQLAlchemy para las cuentas oficiales asociadas a las marcas."""

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from database import Base

class MarcaCuentaOficial(Base):
    __tablename__ = "marca_cuentas_oficiales"

    id = Column(Integer, primary_key=True, index=True)
    marca_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    plataforma = Column(String(50), default="todas", nullable=False)  # 'instagram', 'facebook', 'tiktok', 'mercadolibre', 'todas'
    handle_oficial = Column(String(255), nullable=False)  # ej: "adidasar", "nikestore"

    # Relación inversa con Marca
    marca = relationship("Brand", back_populates="cuentas_oficiales")
