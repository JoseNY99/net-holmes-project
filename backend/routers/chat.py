"""
Router del Chat Center — Endpoints para el frontend.
Gestiona conversaciones, mensajes, toggle bot/analista, y envío manual vía WhatsApp.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db
from models.user import User
from models.chat import Conversation, Message
from middleware.auth_middleware import get_current_user
from services.chat_nlp_engine import analyze_incoming_message
from services.cron_logger import cron_logger

router = APIRouter(prefix="/api/chat", tags=["Chat Center"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class MessageCreate(BaseModel):
    sender: str  # "infractor", "bot", "analista"
    text: str

class ToggleMode(BaseModel):
    mode: str  # "bot" o "analista"

class AnalystSend(BaseModel):
    text: str

class LinkWhatsApp(BaseModel):
    whatsapp_phone: str


# ─── GET Todas las Conversaciones ───────────────────────────────────────────

@router.get("/all")
def get_all_conversations(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Obtiene la lista de todas las conversaciones activas, con datos cruzados del reporte."""
    # Para poder hacer .reporte, necesitamos asegurarnos que la relación está definida en el modelo.
    # Pero también podemos hacer un join si no estuviera.
    from models.reporte import ReporteBrandDefense
    
    conversations = (
        db.query(Conversation)
        .outerjoin(ReporteBrandDefense, Conversation.reporte_id == ReporteBrandDefense.id)
        .all()
    )
    
    result = []
    for conv in conversations:
        # Calcular el número de mensajes no leídos (mensajes del infractor)
        # Esto podría mejorarse con un campo `is_read`, pero por ahora contamos todos los mensajes del infractor.
        unread_count = db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.sender == 'infractor'
        ).count()
        
        last_msg = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.timestamp.desc()).first()
        
        reporte_data = None
        if conv.reporte:
            reporte_data = {
                "id": conv.reporte.id,
                "marca_afectada": conv.reporte.marca_afectada,
                "plataforma": conv.reporte.plataforma,
                "titular_cuenta": conv.reporte.titular_cuenta,
            }
            
        result.append({
            "id": conv.id,
            "reporte_id": conv.reporte_id,
            "mode": conv.mode,
            "is_bot_active": conv.is_bot_active,
            "whatsapp_phone": conv.whatsapp_phone,
            "reporte": reporte_data,
            "unread_count": unread_count,
            "last_message": {
                "text": last_msg.text if last_msg else None,
                "timestamp": last_msg.timestamp if last_msg else None,
            } if last_msg else None
        })
        
    return {"data": result}


# ─── GET Conversación ───────────────────────────────────────────────────────

@router.get("/{reporte_id}")
def get_conversation(
    reporte_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Obtiene o crea la conversación vinculada a un reporte."""
    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).first()
    if not conv:
        conv = Conversation(reporte_id=reporte_id, mode="bot", is_bot_active=True)
        db.add(conv)
        db.commit()
        db.refresh(conv)

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.timestamp.asc())
        .all()
    )

    return {
        "conversation_id": conv.id,
        "mode": conv.mode,
        "is_bot_active": conv.is_bot_active,
        "whatsapp_phone": conv.whatsapp_phone,
        "messages": [
            {
                "id": m.id,
                "sender": m.sender,
                "text": m.text,
                "content": m.text,  # Alias para compatibilidad con el frontend
                "timestamp": m.timestamp,
                "extracted_entities": m.extracted_entities,
                "media_url": m.media_url,
            }
            for m in messages
        ],
    }


# ─── POST Mensaje (interno, no WhatsApp) ────────────────────────────────────

@router.post("/{reporte_id}/message")
def post_message(
    reporte_id: int,
    data: MessageCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Guarda un mensaje en la conversación. Dispara NLP si es del infractor."""
    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).first()
    if not conv:
        conv = Conversation(reporte_id=reporte_id, mode="bot", is_bot_active=True)
        db.add(conv)
        db.commit()
        db.refresh(conv)

    new_msg = Message(conversation_id=conv.id, sender=data.sender, text=data.text)
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    # Ejecutar extracción si es mensaje del infractor
    if new_msg.sender.lower() == "infractor":
        analyze_incoming_message(db, new_msg)

    return {"status": "success", "message_id": new_msg.id}


# ─── POST Envío Manual del Analista (vía WhatsApp Cloud API) ────────────────

@router.post("/{reporte_id}/send")
async def analyst_send_message(
    reporte_id: int,
    data: AnalystSend,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Endpoint para que el analista envíe un mensaje manualmente.
    Si hay WhatsApp configurado, lo envía por Cloud API.
    Siempre guarda el mensaje en la conversación.
    """
    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    # Guardar mensaje del analista
    new_msg = Message(
        conversation_id=conv.id,
        sender="analista",
        text=data.text,
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    # Si hay número de WhatsApp, enviar por Cloud API
    wa_sent = False
    if conv.whatsapp_phone:
        from services.whatsapp_sender import send_text_message
        wa_sent = await send_text_message(conv.whatsapp_phone, data.text)

    cron_logger.log(
        f"[Chat] 👤 Analista ({_user.nombre}) envió mensaje al Reporte #{reporte_id}"
        + (f" → WhatsApp {'✅' if wa_sent else '❌'}" if conv.whatsapp_phone else " (sin WhatsApp)")
    )

    return {
        "status": "success",
        "message_id": new_msg.id,
        "whatsapp_sent": wa_sent,
    }


# ─── POST Toggle Bot/Analista ──────────────────────────────────────────────

@router.post("/{reporte_id}/toggle-mode")
def toggle_mode(
    reporte_id: int,
    data: ToggleMode,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Alterna entre modo Bot (automático) y Analista (manual)."""
    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv.mode = data.mode
    conv.is_bot_active = data.mode.lower() == "bot"
    db.commit()

    cron_logger.log(
        f"[Chat] 🔄 Modo cambiado a {data.mode.upper()} para Reporte #{reporte_id} "
        f"por {_user.nombre}"
    )

    return {
        "status": "success",
        "mode": conv.mode,
        "is_bot_active": conv.is_bot_active,
    }


# ─── POST Vincular WhatsApp ────────────────────────────────────────────────

@router.post("/{reporte_id}/link-whatsapp")
def link_whatsapp(
    reporte_id: int,
    data: LinkWhatsApp,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Vincula un número de WhatsApp a la conversación de un reporte."""
    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).first()
    if not conv:
        conv = Conversation(
            reporte_id=reporte_id,
            mode="bot",
            is_bot_active=True,
            whatsapp_phone=data.whatsapp_phone,
        )
        db.add(conv)
    else:
        conv.whatsapp_phone = data.whatsapp_phone

    db.commit()
    db.refresh(conv)

    cron_logger.log(f"[Chat] 📱 WhatsApp {data.whatsapp_phone} vinculado al Reporte #{reporte_id}")

    return {
        "status": "success",
        "whatsapp_phone": conv.whatsapp_phone,
    }
