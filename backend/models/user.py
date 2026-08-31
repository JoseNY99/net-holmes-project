"""Modelo SQLAlchemy para la tabla de usuarios."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, CheckConstraint
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    celular = Column(String(20), nullable=True)
    ci = Column(String(30), nullable=True)
    correo = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(20), nullable=False, default="analista")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint("rol IN ('sup_admin', 'admin', 'analista')", name="ck_users_rol"),
    )

    # Relación: marcas creadas por este usuario
    brands = relationship("Brand", back_populates="creator", lazy="select")
