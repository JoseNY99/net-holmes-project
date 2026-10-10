"""
Modelos SQLAlchemy para el sistema de Chat Honeypot.
Soporta WhatsApp Cloud API + Chat interno del panel.

- Conversation: Sesión de chat vinculada 1:1 con un ReporteBrandDefense
- Message: Cada mensaje individual con metadata de WhatsApp y extracción LLM
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    reporte_id = Column(Integer, ForeignKey("reportes_brand_defense.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Modo operativo: "bot" (automático con LLM) o "analista" (control manual humano)
    mode = Column(String(50), default="analista")
    is_bot_active = Column(Boolean, default=False)

    # ─── WhatsApp Cloud API ───
    # Número del infractor (formato E.164: +5491112345678)
    whatsapp_phone = Column(String(30), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relaciones
    reporte = relationship("ReporteBrandDefense", backref="conversation", uselist=False)
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.timestamp.asc()")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)

    # Remitente: "infractor", "bot", "analista"
    sender = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)

    # ─── WhatsApp Metadata ───
    # ID único del mensaje en Meta (para deduplicación)
    whatsapp_message_id = Column(String(100), nullable=True, unique=True, index=True)
    # URL de media adjunta (imagen, audio, documento)
    media_url = Column(Text, nullable=True)

    # ─── Extracción LLM ───
    # JSON con las entidades extraídas por el pipeline NLP de este mensaje
    # Ejemplo: {"dni_cedula": "35123456", "alias_bancario": "pepito.mp", "confianza": 0.92}
    extracted_entities = Column(Text, nullable=True)

    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
