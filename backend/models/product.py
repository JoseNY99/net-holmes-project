"""Modelo SQLAlchemy para la tabla de productos."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(
        Integer,
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    estado = Column(String(20), nullable=False, default="activa")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relación inversa con la marca
    brand = relationship("Brand", back_populates="products")
