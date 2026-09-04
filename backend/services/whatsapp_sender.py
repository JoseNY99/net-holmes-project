"""
Servicio de envío de mensajes vía WhatsApp Cloud API.
Incluye el motor de respuesta Honeypot con LLM contextual.
"""

import re
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


def normalize_whatsapp_phone(phone: str) -> str:
    """
    Normaliza cualquier número de teléfono a formato internacional E.164 (solo dígitos)
    compatible con Meta WhatsApp Cloud API.
    Soporta específicamente:
      - Paraguay (PY +595): +595971..., 0971..., 971..., 5950971...
      - Argentina (AR +54): +54911..., +5411..., 011..., 11...
      - Cualquier formato internacional válido.
    """
    if not phone:
        return ""
    digits = re.sub(r'\D', '', str(phone).strip())
    if not digits:
        return ""

    # Caso Paraguay (+595):
    if digits.startswith("595"):
        # Si tiene el 0 troncal local (ej: 5950971682207), quitar el 0
        if len(digits) == 13 and digits.startswith("5950"):
            digits = "595" + digits[4:]
        return digits

    # Si escribió formato local paraguayo (ej: 0971682207 o 0984716528 con 10 dígitos)
    if len(digits) == 10 and digits.startswith("09"):
        return f"595{digits[1:]}"

    # Si escribió 9 dígitos empezando con 9 (ej: 971682207 o 984716528)
    if len(digits) == 9 and digits.startswith("9"):
        return f"595{digits}"

    # Caso Argentina (+54):
    # Si empieza con 54 pero no tiene el 9 móvil (ej 5411xxxxxxxx con 12 dígitos)
    if digits.startswith("54") and not digits.startswith("549") and len(digits) == 12:
        return f"549{digits[2:]}"
    
    # Si escribió formato local argentino (ej: 011xxxxxxxx o 11xxxxxxxx)
    clean_local = digits
    if clean_local.startswith("0"):
        clean_local = clean_local[1:]
    if clean_local.startswith("15"):
        clean_local = clean_local[2:]
    if len(clean_local) == 10 and (clean_local.startswith("11") or clean_local.startswith("2") or clean_local.startswith("3")):
        return f"549{clean_local}"

    return digits


async def send_text_message(phone: str, text: str, db=None) -> tuple[bool, str]:
    """
    Envía un mensaje de texto via WhatsApp Cloud API.
    
    Args:
        phone: Número destino (se normaliza y sanitiza automáticamente para Paraguay, Argentina o Internacional)
        text: Contenido del mensaje
        db: Sesión SQLAlchemy opcional
    
    Returns:
        tuple (success: bool, detail: str)
    """
    token, phone_id = get_active_whatsapp_credentials(db)
    if not token or not phone_id:
        err = "Credenciales de WhatsApp (Token o Phone Number ID) no configuradas en BD."
        cron_logger.log(f"[WhatsApp Sender] ⚠️ {err}")
        return False, err

    # Normalizar número: E.164 estricto de Meta
    clean_phone = normalize_whatsapp_phone(phone)
    if not clean_phone or len(clean_phone) < 8:
        err = f"Número de teléfono inválido ('{phone}'). Debe contener al menos 8 dígitos."
        cron_logger.log(f"[WhatsApp Sender] ❌ {err}")
        return False, err

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            resp_data = response.json() if "application/json" in response.headers.get("content-type", "") else {}

            if response.status_code == 200 and "messages" in resp_data:
                msg_id = resp_data["messages"][0].get("id", "OK")
                cron_logger.log(f"[WhatsApp Sender] ✅ Mensaje enviado exitosamente a {clean_phone} (Meta ID: {msg_id}): {text[:50]}...")
                return True, f"Mensaje enviado exitosamente (Meta ID: {msg_id})"
            else:
                error_info = resp_data.get("error", {})
                error_msg = error_info.get("message", response.text)
                error_code = error_info.get("code")
                error_subcode = error_info.get("error_subcode")
                
                # Humanizar errores frecuentes de Meta para el usuario/analista
                human_reason = error_msg
                if error_code == 131030:
                    human_reason = f"El número {clean_phone} no está en la lista de destinatarios permitidos (To) de tu cuenta de Meta for Developers. Agrégalo en el panel de Meta antes de enviar mensajes de prueba."
                elif error_code == 131047:
                    human_reason = f"Han pasado más de 24 horas desde la última interacción de {clean_phone}. Meta exige que la persona envíe un mensaje primero a tu número de WhatsApp para abrir la ventana de atención."
                elif error_code == 190:
                    human_reason = "El Access Token de WhatsApp ha expirado o no es válido. Genere o guarde un token nuevo en Ajustes de WhatsApp."
                elif error_code == 100:
                    human_reason = f"Phone Number ID incorrecto o parámetro inválido en Meta ({error_msg})."
                
                cron_logger.log(f"[WhatsApp Sender] ❌ Error Meta ({error_code}/{error_subcode}) al enviar a {clean_phone}: {human_reason}")
                return False, human_reason
    except Exception as e:
        cron_logger.log(f"[WhatsApp Sender] ❌ Error de red enviando a {clean_phone}: {e}")
        return False, str(e)


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
    if not reply_text:
        return None

    # Si es el chat de prueba @curtis_holmes, no enviamos a Meta Cloud API, solo guardamos en DB
    if conversation.whatsapp_phone == "@curtis_holmes" or (conversation.reporte and conversation.reporte.titular_cuenta == "@curtis_holmes"):
        bot_msg = Message(
            conversation_id=conversation.id,
            sender="bot",
            text=reply_text,
        )
        db.add(bot_msg)
        db.commit()
        cron_logger.log(f"[Curtis Holmes AI] 🤖 Respuesta de prueba generada: {reply_text[:60]}...")
        return reply_text

    # Enviar por WhatsApp
    success, _detail = await send_text_message(conversation.whatsapp_phone, reply_text, db=db)

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
        return reply_text
    else:
        cron_logger.log(f"[Honeypot] ⚠️ Respuesta generada pero no se pudo enviar por WhatsApp.")
        return None
