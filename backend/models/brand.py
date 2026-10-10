"""Modelo SQLAlchemy para la tabla de marcas."""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    estado = Column(String(20), nullable=False, default="activa")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
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

    __table_args__ = (
        CheckConstraint(
            "estado IN ('activa', 'inactiva')", name="ck_brands_estado"
        ),
    )

    # Relación con el usuario creador
    creator = relationship("User", back_populates="brands", lazy="joined")

    # Relación con los productos de esta marca
    products = relationship(
        "Product",
        back_populates="brand",
        lazy="select",
        cascade="all, delete-orphan",
    )

    # Relación con comportamientos
    comportamientos = relationship(
        "Comportamiento",
        secondary="brand_comportamientos",
        back_populates="brands",
        lazy="select"
    )

    # Relación con cuentas oficiales (blacklist para el scraper)
    cuentas_oficiales = relationship(
        "MarcaCuentaOficial",
        back_populates="marca",
        cascade="all, delete-orphan",
        lazy="joined"
    )
