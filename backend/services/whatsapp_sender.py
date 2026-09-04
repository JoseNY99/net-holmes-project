"""
Servicio de envío de mensajes vía WhatsApp Cloud API.
Incluye el motor de respuesta Honeypot con LLM contextual.
"""

import json
import httpx
from config import settings
from services.cron_logger import cron_logger


def get_active_whatsapp_credentials(db=None):
    """Obtiene el access token y phone number ID activos desde PostgreSQL o fallback settings."""
    token = settings.WHATSAPP_ACCESS_TOKEN
    phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    try:
        from database import SessionLocal
        from models.api_key_setting import ApiKeySetting
        session = db or SessionLocal()
        try:
            setting = session.query(ApiKeySetting).filter(
                ApiKeySetting.service_name == "meta_whatsapp",
                ApiKeySetting.is_active == True
            ).first()
            if setting:
                if setting.api_key:
                    token = setting.api_key
                if setting.extra_config:
                    cfg = json.loads(setting.extra_config)
                    phone_id = cfg.get("whatsapp_phone_number_id") or phone_id
        finally:
            if not db:
                session.close()
    except Exception:
        pass
    return token, phone_id


async def send_text_message(phone: str, text: str, db=None) -> bool:
    """
    Envía un mensaje de texto via WhatsApp Cloud API.
    
    Args:
        phone: Número destino en formato E.164 (ej: 5491112345678)
        text: Contenido del mensaje
    
    Returns:
        True si se envió exitosamente, False en caso contrario
    """
    token, phone_id = get_active_whatsapp_credentials(db)
    if not token or not phone_id:
        cron_logger.log("[WhatsApp Sender] ⚠️ Credenciales de WhatsApp no configuradas en BD ni .env. Mensaje NO enviado.")
        return False

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            cron_logger.log(f"[WhatsApp Sender] ✅ Mensaje enviado a {phone}: {text[:50]}...")
            return True
    except Exception as e:
        cron_logger.log(f"[WhatsApp Sender] ❌ Error enviando mensaje a {phone}: {e}")
        return False


async def send_honeypot_reply(db, conversation, incoming_message):
    """
    Genera una respuesta honeypot usando Cerebras/DeepSeek LLM y la envía por WhatsApp.
    El objetivo es que el infractor revele datos financieros/identitarios.
    """
    if not conversation.whatsapp_phone:
        cron_logger.log("[WhatsApp Sender] ⚠️ Sin número de WhatsApp para responder.")
        return

    from models.chat import Message
    from services.llm_client import generate_honeypot_response

    # Construir historial de conversación para contexto del LLM
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.timestamp.asc())
        .all()
    )
    history = [{"sender": m.sender, "text": m.text} for m in messages]

    # Info del target para el prompt del LLM
    target_info = {}
    if conversation.reporte:
        target_info = {
            "marca": conversation.reporte.marca_afectada,
            "plataforma": conversation.reporte.plataforma,
            "titular": conversation.reporte.titular_cuenta,
        }
    else:
        from models.reporte import ReporteBrandDefense
        reporte = db.query(ReporteBrandDefense).filter(
            ReporteBrandDefense.id == conversation.reporte_id
        ).first()
        if reporte:
            target_info = {
                "marca": reporte.marca_afectada,
                "plataforma": reporte.plataforma,
                "titular": reporte.titular_cuenta,
            }

    # Generar respuesta con LLM
    reply_text = await generate_honeypot_response(history, target_info)

    # Enviar por WhatsApp
    success = await send_text_message(conversation.whatsapp_phone, reply_text)

    if success:
        # Guardar la respuesta del bot en la conversación
        bot_msg = Message(
            conversation_id=conversation.id,
            sender="bot",
            text=reply_text,
        )
        db.add(bot_msg)
        db.commit()
        cron_logger.log(f"[Honeypot] 🤖 Respuesta bot enviada y registrada: {reply_text[:60]}...")
    else:
        cron_logger.log(f"[Honeypot] ⚠️ Respuesta generada pero no se pudo enviar por WhatsApp.")
