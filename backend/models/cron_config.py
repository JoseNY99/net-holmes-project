"""Modelo SQLAlchemy para la configuración del Cron."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text

from database import Base


class CronConfig(Base):
    __tablename__ = "cron_config"

    id = Column(Integer, primary_key=True, index=True)
    is_active = Column(Boolean, nullable=False, default=False)
    hora = Column(Integer, nullable=False, default=2)
    minuto = Column(Integer, nullable=False, default=0)
    plataformas_activas = Column(Text, nullable=False, default='["mercadolibre", "facebook", "instagram", "tiktok"]')
    marcas_seleccionadas = Column(Text, nullable=False, default='[]')
    pais_seleccionado = Column(String(100), nullable=False, default="Argentina")
    provincias_seleccionadas = Column(Text, nullable=False, default='[]')
    limite_extraccion = Column(Integer, nullable=False, default=5) # Deprecated
    limite_extraccion_fb = Column(Integer, nullable=False, default=5)
    limite_extraccion_ig = Column(Integer, nullable=False, default=5)
    limite_extraccion_tt = Column(Integer, nullable=False, default=5)
    limite_extraccion_ml = Column(Integer, nullable=False, default=5)
    proveedor = Column(String(50), nullable=False, default="google_meli_osint")
    fecha_inicio = Column(DateTime(timezone=True), nullable=True)
    fecha_fin = Column(DateTime(timezone=True), nullable=True)
    is_running = Column(Boolean, nullable=False, default=False)
    last_run = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(20), nullable=True)
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
