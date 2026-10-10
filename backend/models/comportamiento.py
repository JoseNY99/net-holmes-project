"""Modelo SQLAlchemy para la tabla de comportamientos y su asociación con marcas."""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Table
from sqlalchemy.orm import relationship

from database import Base

# Tabla de asociación muchos-a-muchos entre Brand y Comportamiento
brand_comportamientos = Table(
    "brand_comportamientos",
    Base.metadata,
    Column("brand_id", Integer, ForeignKey("brands.id", ondelete="CASCADE"), primary_key=True),
    Column("comportamiento_id", Integer, ForeignKey("comportamientos.id", ondelete="CASCADE"), primary_key=True),
)

class Comportamiento(Base):
    __tablename__ = "comportamientos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text, nullable=True)

    # Relación inversa con marcas
    brands = relationship(
        "Brand",
        secondary=brand_comportamientos,
        back_populates="comportamientos"
    )
