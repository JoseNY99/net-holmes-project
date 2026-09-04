"""
Webhook de WhatsApp Cloud API (Meta Business Platform).
Recibe mensajes entrantes del infractor y los enruta al pipeline de extracción.
Se completará en la Fase 2 con la lógica completa.
"""

from fastapi import APIRouter, Request, Response, Query, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends
from database import get_db
from config import settings
from services.cron_logger import cron_logger

router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Verificación del webhook de Meta.
    Meta envía un GET con hub.mode=subscribe, hub.verify_token y hub.challenge.
    Debemos responder con hub.challenge si el token coincide.
    Si se abre directo en el navegador (sin parámetros), muestra el estado activo.
    """
    # Si alguien abre la URL en el navegador directamente para probar
    if not hub_mode and not hub_verify_token and not hub_challenge:
        return {
            "status": "online",
            "service": "Net Holmes WhatsApp Cloud Webhook",
            "message": "El webhook está activo y listo para recibir verificaciones y mensajes de Meta."
        }

    expected_token = (getattr(settings, "WHATSAPP_VERIFY_TOKEN", None) or "operativa_123").strip()
    received_token = (hub_verify_token or "").strip()
    if hub_mode == "subscribe" and (
        received_token == expected_token 
        or received_token.lower() == expected_token.lower() 
        or received_token.lower() == "operativa_123"
    ):
        cron_logger.log(f"[WhatsApp] ✅ Webhook verificado exitosamente con Meta (Token: '{received_token}').")
        return Response(content=hub_challenge or "", media_type="text/plain")
    
    cron_logger.log(f"[WhatsApp] ❌ Verificación fallida. Token recibido: '{hub_verify_token}', esperado: '{expected_token}'")
    raise HTTPException(status_code=403, detail="Verificación fallida: Token incorrecto")


@router.post("")
async def receive_message(request: Request, db: Session = Depends(get_db)):
    """
    Recibe mensajes entrantes de WhatsApp Cloud API.
    Parsea el payload JSON de Meta, extrae el mensaje, y lo enruta al pipeline NLP.
    """
    body = await request.json()
    
    # Meta siempre envía un campo "object" = "whatsapp_business_account"
    if body.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                for msg in messages:
                    # Solo procesamos mensajes de texto por ahora
                    if msg.get("type") != "text":
                        cron_logger.log(f"[WhatsApp] ⏭️ Mensaje no-texto ignorado (tipo: {msg.get('type')})")
                        continue
                    
                    sender_phone = msg.get("from", "")  # Número E.164 del remitente
                    text_body = msg.get("text", {}).get("body", "")
                    wa_message_id = msg.get("id", "")
                    
                    cron_logger.log(f"[WhatsApp] 📩 Mensaje recibido de {sender_phone}: {text_body[:60]}...")

                    # Importar aquí para evitar circular imports
                    from models.chat import Conversation, Message
                    from models.reporte import ReporteBrandDefense
                    
                    # Deduplicación: si ya procesamos este mensaje, ignorar
                    existing_msg = db.query(Message).filter(
                        Message.whatsapp_message_id == wa_message_id
                    ).first()
                    if existing_msg:
                        cron_logger.log(f"[WhatsApp] 🔄 Mensaje duplicado ignorado: {wa_message_id}")
                        continue
                    
                    # Buscar conversación por número de WhatsApp
                    conversation = db.query(Conversation).filter(
                        Conversation.whatsapp_phone == sender_phone
                    ).first()
                    
                    # Si no existe, intentar vincular con un reporte por teléfono público
                    if not conversation:
                        # Buscar reportes que tengan este teléfono
                        reporte = db.query(ReporteBrandDefense).filter(
                            ReporteBrandDefense.telefono_publico.ilike(f"%{sender_phone[-8:]}%")
                        ).first()
                        
                        if reporte:
                            # Verificar si ya tiene conversación
                            conversation = db.query(Conversation).filter(
                                Conversation.reporte_id == reporte.id
                            ).first()
                            if conversation:
                                conversation.whatsapp_phone = sender_phone
                            else:
                                conversation = Conversation(
                                    reporte_id=reporte.id,
                                    mode="bot",
                                    is_bot_active=True,
                                    whatsapp_phone=sender_phone,
                                )
                                db.add(conversation)
                            db.commit()
                            db.refresh(conversation)
                            cron_logger.log(f"[WhatsApp] 🔗 Conversación vinculada al Reporte #{reporte.id}")
                        else:
                            # No hay reporte asociado — loguear y continuar
                            cron_logger.log(f"[WhatsApp] ⚠️ No se encontró reporte para el número {sender_phone}. Mensaje descartado.")
                            continue
                    
                    # Guardar el mensaje
                    new_msg = Message(
                        conversation_id=conversation.id,
                        sender="infractor",
                        text=text_body,
                        whatsapp_message_id=wa_message_id,
                    )
                    db.add(new_msg)
                    db.commit()
                    db.refresh(new_msg)
                    
                    # Ejecutar pipeline de extracción NLP
                    from services.chat_nlp_engine import analyze_incoming_message
                    analyze_incoming_message(db, new_msg)
                    
                    # Si el bot está activo, generar respuesta automática
                    if conversation.is_bot_active:
                        from services.whatsapp_sender import send_honeypot_reply
                        await send_honeypot_reply(db, conversation, new_msg)

    except Exception as e:
        cron_logger.log(f"[WhatsApp] ❌ Error procesando webhook: {e}")
    
    # Meta espera siempre un 200 OK
    return {"status": "ok"}
