"""Modelo SQLAlchemy para almacenamiento y gestión de API Keys en Base de Datos."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from database import Base

class ApiKeySetting(Base):
    __tablename__ = "api_key_settings"

    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String(50), nullable=False, unique=True, index=True) # serper, apify, rapidapi, cerebras, deepseek, meta_whatsapp
    api_key = Column(Text, nullable=True)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    extra_config = Column(Text, nullable=True) # JSON para campos adicionales
    
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