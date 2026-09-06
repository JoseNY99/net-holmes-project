"""
Webhook de WhatsApp Cloud API (Meta Business Platform).
Recibe mensajes entrantes del infractor y los enruta al pipeline de extracción.
Se completará en la Fase 2 con la lógica completa.
"""

import re
from fastapi import APIRouter, Request, Response, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db
from config import settings
from services.cron_logger import cron_logger
from services.whatsapp_sender import normalize_whatsapp_phone

router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])


@router.get("")
@router.get("/")
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
@router.post("/")
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

                # Registrar estados de entrega emitidos por Meta (sent, delivered, read, failed)
                statuses = value.get("statuses", [])
                for status_obj in statuses:
                    wa_status = status_obj.get("status")
                    recipient = status_obj.get("recipient_id")
                    st_id = status_obj.get("id")
                    errors = status_obj.get("errors", [])
                    if wa_status == "failed" or errors:
                        err_msg = errors[0].get("message") if errors else "Falla desconocida de entrega"
                        err_code = errors[0].get("code") if errors else "N/A"
                        cron_logger.log(
                            f"[WhatsApp Delivery ❌] Meta NO pudo entregar el mensaje {st_id} a {recipient}. "
                            f"Error ({err_code}): {err_msg}"
                        )
                    else:
                        cron_logger.log(f"[WhatsApp Delivery ℹ️] Mensaje {st_id} a {recipient}: estado '{wa_status}'")

                messages = value.get("messages", [])
                
                for msg in messages:
                    msg_type = msg.get("type", "text")
                    sender_phone = str(msg.get("from", "")).strip()  # Número E.164 del remitente (ej. "595984716528")
                    wa_message_id = msg.get("id", "")
                    
                    media_id = None
                    mime_hint = ""
                    filename_hint = ""

                    if msg_type == "text":
                        text_body = msg.get("text", {}).get("body", "")
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        text_body = (
                            interactive.get("button_reply", {}).get("title") or
                            interactive.get("list_reply", {}).get("title") or
                            "[Respuesta interactiva]"
                        )
                    elif msg_type == "image":
                        img_data = msg.get("image", {})
                        media_id = img_data.get("id")
                        mime_hint = img_data.get("mime_type", "image/jpeg")
                        caption = img_data.get("caption", "")
                        text_body = f"[📷 Foto]: {caption}" if caption else "[📷 Foto recibida]"
                    elif msg_type in ("audio", "voice"):
                        aud_data = msg.get("audio", {}) or msg.get("voice", {})
                        media_id = aud_data.get("id")
                        mime_hint = aud_data.get("mime_type", "audio/ogg")
                        text_body = "[🎤 Mensaje de voz recibido]"
                    elif msg_type == "video":
                        vid_data = msg.get("video", {})
                        media_id = vid_data.get("id")
                        mime_hint = vid_data.get("mime_type", "video/mp4")
                        caption = vid_data.get("caption", "")
                        text_body = f"[🎥 Video]: {caption}" if caption else "[🎥 Video recibido]"
                    elif msg_type == "document":
                        doc_data = msg.get("document", {})
                        media_id = doc_data.get("id")
                        mime_hint = doc_data.get("mime_type", "application/pdf")
                        filename_hint = doc_data.get("filename", "archivo")
                        text_body = f"[📄 Documento: {filename_hint}]"
                    elif msg_type == "location":
                        loc = msg.get("location", {})
                        text_body = f"[📍 Ubicación: {loc.get('latitude')}, {loc.get('longitude')}]"
                    elif msg_type == "reaction":
                        emoji = msg.get("reaction", {}).get("emoji", "👍")
                        text_body = f"[Reacción: {emoji}]"
                    else:
                        text_body = f"[{msg_type.capitalize()} recibido]"

                    if not text_body:
                        continue
                    
                    cron_logger.log(f"[WhatsApp] 📩 Mensaje ({msg_type}) recibido de {sender_phone}: {text_body[:60]}...")

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
                    
                    # Normalizar número a E.164 estricto de Meta
                    clean_digits = normalize_whatsapp_phone(sender_phone)
                    raw_digits = re.sub(r'\D', '', sender_phone)
                    phone_variants = list(set([sender_phone, clean_digits, f"+{clean_digits}", raw_digits, f"+{raw_digits}"]))
                    
                    # 1. Buscar conversación existente por cualquiera de las variantes de teléfono o últimos dígitos
                    conversation = None
                    if clean_digits:
                        search_filters = [Conversation.whatsapp_phone.in_(phone_variants)]
                        if len(clean_digits) >= 8:
                            search_filters.append(Conversation.whatsapp_phone.ilike(f"%{clean_digits[-8:]}"))
                        
                        conversation = db.query(Conversation).filter(
                            or_(*search_filters)
                        ).order_by(Conversation.id.desc()).first()
                    
                    # 2. Si no existe conversación directa, buscar en reportes por teléfono
                    if not conversation and clean_digits:
                        report_filters = [ReporteBrandDefense.telefono_publico.in_(phone_variants)]
                        if len(clean_digits) >= 8:
                            report_filters.append(ReporteBrandDefense.telefono_publico.ilike(f"%{clean_digits[-8:]}%"))

                        reporte = db.query(ReporteBrandDefense).filter(
                            or_(*report_filters)
                        ).order_by(ReporteBrandDefense.id.desc()).first()
                        
                        if reporte:
                            # Verificar si el reporte ya tiene conversación
                            conversation = db.query(Conversation).filter(
                                Conversation.reporte_id == reporte.id
                            ).order_by(Conversation.id.desc()).first()

                            if conversation:
                                conversation.whatsapp_phone = f"+{clean_digits}"
                            else:
                                conversation = Conversation(
                                    reporte_id=reporte.id,
                                    mode="bot",
                                    is_bot_active=True,
                                    whatsapp_phone=f"+{clean_digits}",
                                )
                                db.add(conversation)
                            db.commit()
                            db.refresh(conversation)
                            cron_logger.log(f"[WhatsApp] 🔗 Conversación vinculada al Reporte #{reporte.id}")
                        else:
                            # 3. No hay reporte previo — Crear reporte y conversación automáticamente
                            reporte = ReporteBrandDefense(
                                pais="Contacto WhatsApp",
                                producto_catalogo="Contacto Directo WhatsApp",
                                marca_afectada="WhatsApp Inbound",
                                plataforma="WhatsApp",
                                titular_cuenta=f"+{clean_digits}",
                                url_evidencia=f"https://wa.me/{clean_digits}",
                                telefono_publico=f"+{clean_digits}",
                                estado="Sospechoso",
                            )
                            db.add(reporte)
                            db.commit()
                            db.refresh(reporte)

                            conversation = Conversation(
                                reporte_id=reporte.id,
                                mode="bot",
                                is_bot_active=True,
                                whatsapp_phone=f"+{clean_digits}",
                            )
                            db.add(conversation)
                            db.commit()
                            db.refresh(conversation)
                            cron_logger.log(f"[WhatsApp] 🆕 Nuevo reporte #{reporte.id} y conversación creados automáticamente para +{clean_digits}")
                    
                    if not conversation:
                        cron_logger.log(f"[WhatsApp] ⚠️ No se pudo asignar conversación para {sender_phone}")
                        continue

                    # Descarga y compresión máxima de archivos adjuntos (imágenes, audios, videos, documentos)
                    saved_media_url = None
                    if media_id:
                        try:
                            from services.media_compressor import download_and_save_whatsapp_media
                            saved_media_url, _local_path = await download_and_save_whatsapp_media(
                                media_id=media_id,
                                media_type=msg_type if msg_type != "voice" else "audio",
                                mime_type_hint=mime_hint,
                                filename_hint=filename_hint,
                                db=db
                            )
                        except Exception as media_err:
                            cron_logger.log(f"[WhatsApp] ⚠️ Error procesando multimedia {media_id}: {media_err}")

                    # Guardar el mensaje del infractor / contacto con URL de multimedia comprimida
                    new_msg = Message(
                        conversation_id=conversation.id,
                        sender="infractor",
                        text=text_body,
                        media_url=saved_media_url,
                        whatsapp_message_id=wa_message_id,
                    )
                    db.add(new_msg)
                    db.commit()
                    db.refresh(new_msg)
                    
                    media_tag = f" [Multimedia comprimida: {saved_media_url}]" if saved_media_url else ""
                    cron_logger.log(
                        f"[AUDITORÍA WHATSAPP] 💾 Mensaje ID {wa_message_id} registrado en Conversación #{conversation.id} "
                        f"(Reporte #{conversation.reporte_id} - {conversation.whatsapp_phone}): {text_body}{media_tag}"
                    )

                    # Ejecutar pipeline de extracción NLP
                    from services.chat_nlp_engine import analyze_incoming_message
                    analyze_incoming_message(db, new_msg)
                    
                    # Si el bot está activo, generar respuesta automática honeypot
                    if conversation.is_bot_active:
                        from services.whatsapp_sender import send_honeypot_reply
                        await send_honeypot_reply(db, conversation, new_msg)

    except Exception as e:
        cron_logger.log(f"[WhatsApp] ❌ Error procesando webhook: {e}")
    
    # Meta espera siempre un 200 OK
    return {"status": "ok"}
