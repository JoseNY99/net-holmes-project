"""
Router del Chat Center — Endpoints para el frontend.
Gestiona conversaciones, mensajes, toggle bot/analista, envío manual vía WhatsApp,
chat de prueba simulado @curtis_holmes y agregado temporal de números para pruebas.
"""

import re
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
from models.user import User
from models.chat import Conversation, Message
from models.reporte import ReporteBrandDefense
from middleware.auth_middleware import get_current_user, require_admin
from services.chat_nlp_engine import analyze_incoming_message
from services.cron_logger import cron_logger
from services.whatsapp_sender import send_text_message, send_template_message, get_active_whatsapp_credentials, normalize_whatsapp_phone

router = APIRouter(prefix="/api/chat", tags=["Chat Center"])

from datetime import datetime

CURTIS_TITULAR = "@curtis_holmes"
CURTIS_WELCOME = (
    "¡Hola! Soy Curtis Holmes, el agente honeypot de Net Holmes. "
    "Estoy activo y listo para simular conversaciones. Escríbeme haciéndote "
    "pasar por un vendedor o infractor y pondré a prueba mis técnicas de "
    "extracción de datos (CBU, Alias, DNI, precios, etc.)."
)

TEST_PHONE_DEFAULT = "+595984716528"
TEST_PHONE_OLIVER = "+595971682207"


def get_time_based_greeting() -> str:
    """Genera un saludo dinámico según la hora local del sistema (Buenos días / tardes / noches)."""
    hour = datetime.now().hour
    if 6 <= hour < 13:
        saludo = "Buenos días"
    elif 13 <= hour < 20:
        saludo = "Buenas tardes"
    else:
        saludo = "Buenas noches"
    return f"¡Hola! {saludo}, vi tu publicación. ¿Sigue disponible? ¿Cuánto sale y cómo coordinamos?"


# ─── Helpers ────────────────────────────────────────────────────────────────

def ensure_test_phone_conversation(db: Session):
    """Asegura que los números de prueba de WhatsApp (+595971682207 y +595984716528) estén disponibles en Chat Center."""
    test_numbers = [
        (TEST_PHONE_OLIVER, "Oliver Personal (+595971682207)"),
        (TEST_PHONE_DEFAULT, "Sujeto de Prueba (+595984716528)"),
    ]
    for phone_raw, titular in test_numbers:
        clean = normalize_whatsapp_phone(phone_raw)
        formatted = f"+{clean}"
        conv = db.query(Conversation).filter(
            Conversation.whatsapp_phone.in_([formatted, clean, phone_raw])
        ).first()

        if not conv:
            reporte = ReporteBrandDefense(
                pais="Paraguay",
                producto_catalogo="Contacto WhatsApp de Prueba",
                marca_afectada="Test WhatsApp PY",
                plataforma="WhatsApp",
                titular_cuenta=titular,
                url_evidencia=f"https://wa.me/{clean}",
                telefono_publico=formatted,
                estado="Sospechoso",
            )
            db.add(reporte)
            db.commit()
            db.refresh(reporte)

            conv = Conversation(
                reporte_id=reporte.id,
                mode="bot",
                is_bot_active=False,  # En espera de la orden de arranque del admin
                whatsapp_phone=formatted,
            )
            db.add(conv)
            db.commit()
            cron_logger.log(f"[Chat] 📱 Conversación de prueba para {formatted} ({titular}) preparada en Chat Center.")


def get_or_create_curtis_test_conversation(db: Session) -> Conversation:
    """Busca o crea la conversación de prueba oficial @curtis_holmes."""
    reporte = db.query(ReporteBrandDefense).filter(
        ReporteBrandDefense.titular_cuenta == CURTIS_TITULAR
    ).first()

    if not reporte:
        reporte = ReporteBrandDefense(
            pais="Argentina",
            producto_catalogo="Entrenamiento y Simulación Honeypot",
            marca_afectada="Simulador Curtis Holmes",
            plataforma="Simulador AI",
            titular_cuenta=CURTIS_TITULAR,
            url_evidencia="https://netholmes.tech/chat",
            telefono_publico="SIMULADOR",
            estado="Simulación",
        )
        db.add(reporte)
        db.commit()
        db.refresh(reporte)

    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte.id).first()
    if not conv:
        conv = Conversation(
            reporte_id=reporte.id,
            mode="bot",
            is_bot_active=True,
            whatsapp_phone=CURTIS_TITULAR,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        # Sembrar mensaje de bienvenida inicial
        welcome_msg = Message(
            conversation_id=conv.id,
            sender="bot",
            text=CURTIS_WELCOME,
        )
        db.add(welcome_msg)
        db.commit()
    else:
        if conv.whatsapp_phone != CURTIS_TITULAR:
            conv.whatsapp_phone = CURTIS_TITULAR
            db.commit()

    return conv


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

class CurtisMessageCreate(BaseModel):
    text: str
    sender: Optional[str] = "infractor"  # "infractor" para que Curtis responda con IA, o "analista"
    bot_role: Optional[str] = None  # "seller" (vendedor simulacro) o "honeypot" (analista comprador)

class AddTemporaryNumberRequest(BaseModel):
    phone: str
    name: Optional[str] = None
    initial_mode: Optional[str] = "bot"  # "bot" o "analista"
    send_opening_message: Optional[bool] = False
    custom_opening_text: Optional[str] = None

class StartBotRequest(BaseModel):
    custom_message: Optional[str] = None

class EditContactRequest(BaseModel):
    phone: str
    titular: Optional[str] = None

class SendTemplateRequest(BaseModel):
    template_name: Optional[str] = ""
    language_code: Optional[str] = "es"


# ─── GET Todas las Conversaciones ───────────────────────────────────────────

@router.get("/all")
def get_all_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtiene la lista de todas las conversaciones activas.
    Solo administradores y superadministradores pueden ver y acceder al chat @curtis_holmes.
    """
    is_admin = current_user.rol in ("admin", "sup_admin")

    if is_admin:
        get_or_create_curtis_test_conversation(db)
        ensure_test_phone_conversation(db)

    conversations = (
        db.query(Conversation)
        .outerjoin(ReporteBrandDefense, Conversation.reporte_id == ReporteBrandDefense.id)
        .all()
    )

    curtis_conv = None
    result = []
    for conv in conversations:
        is_curtis = (
            conv.whatsapp_phone == CURTIS_TITULAR
            or (conv.reporte and conv.reporte.titular_cuenta == CURTIS_TITULAR)
        )

        # Si no es admin y es la conversación de prueba de Curtis, no mostrar
        if is_curtis and not is_admin:
            continue

        unread_count = db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.sender == 'infractor'
        ).count()

        last_msg = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.timestamp.desc())
            .first()
        )

        reporte_data = None
        if conv.reporte:
            reporte_data = {
                "id": conv.reporte.id,
                "marca_afectada": conv.reporte.marca_afectada,
                "plataforma": conv.reporte.plataforma,
                "titular_cuenta": conv.reporte.titular_cuenta,
            }

        conv_dict = {
            "id": conv.id,
            "reporte_id": conv.reporte_id,
            "mode": conv.mode,
            "is_bot_active": conv.is_bot_active,
            "whatsapp_phone": conv.whatsapp_phone,
            "is_curtis": is_curtis,
            "reporte": reporte_data,
            "unread_count": unread_count,
            "last_message": {
                "text": last_msg.text if last_msg else None,
                "timestamp": last_msg.timestamp.isoformat() if (last_msg and last_msg.timestamp) else None,
            } if last_msg else None
        }

        if is_curtis:
            curtis_conv = conv_dict
        else:
            result.append(conv_dict)

    # Ordenar por fecha del último mensaje descendente
    result.sort(
        key=lambda x: x["last_message"]["timestamp"] if (x.get("last_message") and x["last_message"].get("timestamp")) else "",
        reverse=True
    )
    if curtis_conv:
        result.insert(0, curtis_conv)

    return {"data": result}


# ─── GET Conversación por Reporte ID ───────────────────────────────────────

@router.get("/{reporte_id}")
def get_conversation(
    reporte_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene una conversación vinculada a un reporte o la crea."""
    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).order_by(Conversation.id.desc()).first()
    if not conv:
        conv = Conversation(reporte_id=reporte_id, mode="analista", is_bot_active=False)
        db.add(conv)
        db.commit()
        db.refresh(conv)

    is_curtis = (
        conv.whatsapp_phone == CURTIS_TITULAR
        or (conv.reporte and conv.reporte.titular_cuenta == CURTIS_TITULAR)
    )

    if is_curtis and current_user.rol not in ("admin", "sup_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El chat de prueba @curtis_holmes es exclusivo para administradores."
        )

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
        "is_curtis": is_curtis,
        "reporte": {
            "id": conv.reporte.id,
            "titular_cuenta": conv.reporte.titular_cuenta,
            "marca_afectada": conv.reporte.marca_afectada,
            "plataforma": conv.reporte.plataforma,
        } if conv.reporte else None,
        "messages": [
            {
                "id": m.id,
                "sender": m.sender,
                "text": m.text,
                "content": m.text,
                "timestamp": m.timestamp,
                "extracted_entities": m.extracted_entities,
                "media_url": m.media_url,
            }
            for m in messages
        ],
    }


# ─── POST Mensaje en @curtis_holmes (Exclusivo Admins) ─────────────────────

@router.post("/curtis/message")
async def send_curtis_simulation_message(
    data: CurtisMessageCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Envía un mensaje de prueba al chat @curtis_holmes.
    - Si el usuario actúa como 'analista', el Bot asume el rol de VENDEDOR SIMULACRO (infractor),
      responde cotizando réplicas con Alias/CBU para que el analista practique la investigación OSINT.
    - Si el usuario actúa como 'infractor', el Bot asume el rol de ANALISTA HONEYPOT (comprador),
      interroga al usuario para extraer datos.
    Retorna llm_error si DeepSeek reportó alguna falla (falta de crédito, API key inválida, etc).
    """
    conv = get_or_create_curtis_test_conversation(db)

    # Asegurar que el bot esté activo en la conversación de simulación
    if not conv.is_bot_active:
        conv.is_bot_active = True
        db.commit()

    user_sender = (data.sender or "infractor").lower()

    try:
        # 1. Guardar mensaje ingresado por el usuario
        new_msg = Message(
            conversation_id=conv.id,
            sender=user_sender,
            text=data.text.strip(),
        )
        db.add(new_msg)
        db.commit()
        db.refresh(new_msg)
    except Exception as e:
        cron_logger.log(f"[Curtis Holmes] ❌ Error guardando mensaje del usuario: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error guardando mensaje en la base de datos: {str(e)}"
        )

    bot_reply_text = None
    llm_error = None

    try:
        from services.llm_client import generate_honeypot_response, generate_seller_simulation_response

        # Historial de conversación
        messages = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.timestamp.asc())
            .all()
        )
        history = [{"sender": m.sender, "text": m.text} for m in messages]
        target_info = {
            "marca": "Nike / Zapatillas (Simulador)",
            "plataforma": "Simulador AI",
            "titular": CURTIS_TITULAR,
        }

        if user_sender == "analista" or data.bot_role == "seller":
            # El usuario actúa como Analista -> El Bot responde como Vendedor Infractor
            bot_reply_text, llm_error = await generate_seller_simulation_response(history, target_info)
            if bot_reply_text:
                bot_msg = Message(
                    conversation_id=conv.id,
                    sender="infractor",
                    text=bot_reply_text,
                )
                db.add(bot_msg)
                db.commit()
                db.refresh(bot_msg)
                # Analizar con NLP la respuesta del vendedor simulado de forma segura
                try:
                    analyze_incoming_message(db, bot_msg)
                except Exception as nlp_err:
                    cron_logger.log(f"[Curtis Holmes NLP] ⚠️ {nlp_err}")
                cron_logger.log(f"[Curtis Holmes AI - Vendedor] 🎭 Respuesta generada: {bot_reply_text[:60]}...")
        else:
            # El usuario actúa como Infractor -> Analizar mensaje del usuario con NLP de forma segura
            try:
                analyze_incoming_message(db, new_msg)
            except Exception as nlp_err:
                cron_logger.log(f"[Curtis Holmes NLP] ⚠️ {nlp_err}")

            # El Bot responde como Analista Honeypot Comprador
            bot_reply_text, llm_error = await generate_honeypot_response(history, target_info)
            if bot_reply_text:
                bot_msg = Message(
                    conversation_id=conv.id,
                    sender="bot",
                    text=bot_reply_text,
                )
                db.add(bot_msg)
                db.commit()
                db.refresh(bot_msg)
                cron_logger.log(f"[Curtis Holmes AI - Honeypot] 🤖 Respuesta generada: {bot_reply_text[:60]}...")

    except Exception as e:
        cron_logger.log(f"[Curtis Holmes] ❌ Error generando respuesta bot: {e}")
        db.rollback()
        llm_error = str(e)
        bot_reply_text = "Disculpa, ocurrió un error temporal al procesar la respuesta con la IA."

    return {
        "status": "success",
        "message_id": new_msg.id,
        "bot_reply": bot_reply_text,
        "llm_error": llm_error,
    }


# ─── POST Reiniciar Simulación @curtis_holmes ──────────────────────────────

@router.post("/curtis/reset")
def reset_curtis_simulation(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Limpia el historial de mensajes de @curtis_holmes y restablece el mensaje de bienvenida."""
    conv = get_or_create_curtis_test_conversation(db)

    # Borrar mensajes previos
    db.query(Message).filter(Message.conversation_id == conv.id).delete()
    conv.mode = "bot"
    conv.is_bot_active = True

    # Mensaje inicial
    welcome = Message(
        conversation_id=conv.id,
        sender="bot",
        text=CURTIS_WELCOME,
    )
    db.add(welcome)
    db.commit()

    cron_logger.log("[Chat] 🧹 Chat de prueba @curtis_holmes reiniciado por administrador.")
    return {"status": "success", "message": "Chat de simulación @curtis_holmes reiniciado con éxito."}


# ─── POST Agregar Número Temporal (Exclusivo Admins) ───────────────────────

@router.post("/add-number")
async def add_temporary_number(
    data: AddTemporaryNumberRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Permite a administradores agregar un número temporal para probar la interacción
    por WhatsApp con personas reales o dispositivos de prueba.
    """
    clean_phone = normalize_whatsapp_phone(data.phone or '')
    if len(clean_phone) < 8:
        raise HTTPException(
            status_code=400,
            detail="El número de teléfono debe contener al menos 8 dígitos numéricos válidos."
        )

    formatted_phone = f"+{clean_phone}"

    # Verificar si ya existe conversación con este teléfono
    conv = db.query(Conversation).filter(
        Conversation.whatsapp_phone.in_([formatted_phone, clean_phone])
    ).first()

    if not conv:
        # Crear Reporte asociado
        reporte_titular = data.name.strip() if (data.name and data.name.strip()) else f"Contacto {formatted_phone}"
        reporte = ReporteBrandDefense(
            pais="Argentina",
            producto_catalogo="Prueba WhatsApp Temporal",
            marca_afectada="Test Temporal",
            plataforma="WhatsApp",
            titular_cuenta=reporte_titular,
            url_evidencia=f"https://wa.me/{clean_phone}",
            telefono_publico=formatted_phone,
            estado="Sospechoso",
        )
        db.add(reporte)
        db.commit()
        db.refresh(reporte)

        conv = Conversation(
            reporte_id=reporte.id,
            mode=data.initial_mode or "bot",
            is_bot_active=(data.initial_mode == "bot"),
            whatsapp_phone=formatted_phone,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        cron_logger.log(f"[Chat] 📱 Administrador ({_admin.nombre}) agregó número temporal {formatted_phone} (Reporte #{reporte.id})")
    else:
        # Actualizar modo si se especifica
        if data.initial_mode:
            conv.mode = data.initial_mode
            conv.is_bot_active = (data.initial_mode == "bot")
            db.commit()

    wa_sent = False
    wa_detail = None

    # Si se solicitó enviar mensaje de apertura de inmediato
    if data.send_opening_message:
        opening_text = (
            data.custom_opening_text.strip()
            if (data.custom_opening_text and data.custom_opening_text.strip())
            else get_time_based_greeting()
        )
        
        wa_sent, wa_detail = await send_text_message(conv.whatsapp_phone, opening_text, db=db)

        # Registrar el mensaje enviado
        new_msg = Message(
            conversation_id=conv.id,
            sender="bot" if conv.is_bot_active else "analista",
            text=opening_text,
        )
        db.add(new_msg)
        db.commit()

    return {
        "status": "success",
        "conversation_id": conv.id,
        "reporte_id": conv.reporte_id,
        "whatsapp_phone": conv.whatsapp_phone,
        "whatsapp_sent": wa_sent,
        "whatsapp_detail": wa_detail,
        "message": f"Número {conv.whatsapp_phone} incorporado exitosamente al Chat Center."
    }


# ─── PUT Editar Número o Titular de Contacto ──────────────────────────────

@router.put("/{reporte_id}/edit-contact")
def edit_contact_info(
    reporte_id: int,
    data: EditContactRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Permite corregir o actualizar el número de teléfono y/o el nombre titular
    de un contacto si fue ingresado con errores o cambió.
    """
    clean = normalize_whatsapp_phone(data.phone or '')
    if len(clean) < 8:
        raise HTTPException(
            status_code=400,
            detail="El número debe contener al menos 8 dígitos numéricos válidos (incluyendo código de país)."
        )
    formatted_phone = f"+{clean}"

    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).order_by(Conversation.id.desc()).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")

    conv.whatsapp_phone = formatted_phone

    if conv.reporte:
        conv.reporte.telefono_publico = formatted_phone
        conv.reporte.url_evidencia = f"https://wa.me/{clean}"
        if data.titular and data.titular.strip():
            conv.reporte.titular_cuenta = data.titular.strip()

    db.commit()
    db.refresh(conv)

    cron_logger.log(f"[Chat] ✏️ Contacto #{reporte_id} actualizado por {_admin.nombre}: Teléfono {formatted_phone}, Titular {conv.reporte.titular_cuenta if conv.reporte else 'N/A'}")
    return {
        "status": "success",
        "message": f"Número corregido a {formatted_phone} exitosamente.",
        "whatsapp_phone": conv.whatsapp_phone,
        "titular_cuenta": conv.reporte.titular_cuenta if conv.reporte else None,
        "reporte_id": reporte_id
    }


# ─── POST Dar Orden de Arrancar al Bot ────────────────────────────────────

@router.post("/{reporte_id}/start-bot")
async def start_bot_command(
    reporte_id: int,
    data: StartBotRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Da la orden de arrancar al bot:
    1. Activa el modo bot automático.
    2. Envía un mensaje de apertura por WhatsApp para enganchar a la persona.
    3. Deja al bot en escucha activa para responder automáticamente cuando contesten.
    """
    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv.mode = "bot"
    conv.is_bot_active = True
    db.commit()

    is_curtis = (
        conv.whatsapp_phone == CURTIS_TITULAR
        or (conv.reporte and conv.reporte.titular_cuenta == CURTIS_TITULAR)
    )

    opening_text = (
        data.custom_message.strip()
        if (data.custom_message and data.custom_message.strip())
        else get_time_based_greeting()
    )

    wa_sent = False
    wa_detail = None

    if is_curtis:
        # En simulación no se envía a Meta
        bot_msg = Message(conversation_id=conv.id, sender="bot", text=opening_text)
        db.add(bot_msg)
        db.commit()
        wa_sent = True
        wa_detail = "Mensaje simulado publicado en @curtis_holmes"
    else:
        if conv.whatsapp_phone:
            wa_sent, wa_detail = await send_text_message(conv.whatsapp_phone, opening_text, db=db)
        
        bot_msg = Message(
            conversation_id=conv.id,
            sender="bot",
            text=opening_text,
        )
        db.add(bot_msg)
        db.commit()

    cron_logger.log(
        f"[Chat] 🚀 Orden de arranque enviada al Reporte #{reporte_id} por {_admin.nombre}. "
        f"WhatsApp: {'✅' if wa_sent else '❌'} ({wa_detail})"
    )

    return {
        "status": "success",
        "is_bot_active": True,
        "mode": "bot",
        "bot_text": opening_text,
        "whatsapp_sent": wa_sent,
        "whatsapp_detail": wa_detail,
        "message": "¡Orden de arranque ejecutada! El bot está activo y envió el mensaje de apertura."
    }


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
    Si hay WhatsApp configurado, lo envía por Cloud API sanitizando el formato.
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

    is_curtis = (
        conv.whatsapp_phone == CURTIS_TITULAR
        or (conv.reporte and conv.reporte.titular_cuenta == CURTIS_TITULAR)
    )

    wa_sent = False
    wa_detail = None

    if is_curtis:
        wa_sent = True
        wa_detail = "Mensaje simulado enviado en @curtis_holmes"
    elif conv.whatsapp_phone:
        wa_sent, wa_detail = await send_text_message(conv.whatsapp_phone, data.text, db=db)

    cron_logger.log(
        f"[Chat] 👤 Analista ({_user.nombre}) envió mensaje al Reporte #{reporte_id}"
        + (f" → WhatsApp {'✅' if wa_sent else '❌'} ({wa_detail})" if conv.whatsapp_phone else " (sin WhatsApp)")
    )

    return {
        "status": "success",
        "message_id": new_msg.id,
        "whatsapp_sent": wa_sent,
        "whatsapp_detail": wa_detail,
    }


# ─── POST Enviar Plantilla Oficial (Message Template) ──────────────────────

@router.post("/{reporte_id}/send-template")
async def send_template_to_contact(
    reporte_id: int,
    data: Optional[SendTemplateRequest] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Envía una plantilla oficial de WhatsApp (Message Template) al contacto.
    Permite abrir la ventana de 24 horas con números nuevos o inactivos.
    """
    conv = db.query(Conversation).filter(Conversation.reporte_id == reporte_id).order_by(Conversation.id.desc()).first()
    if not conv or not conv.whatsapp_phone:
        raise HTTPException(status_code=404, detail="Conversación o número de WhatsApp no encontrado.")

    tpl_name = (data.template_name if (data and data.template_name) else "").strip()
    lang_code = (data.language_code if (data and data.language_code) else "es").strip()

    if not tpl_name:
        raise HTTPException(
            status_code=400, 
            detail="Debes especificar el nombre de una plantilla aprobada en Meta Business Suite. "
                   "La plantilla 'hello_world' NO funciona con números reales."
        )

    success, detail = await send_template_message(
        phone=conv.whatsapp_phone,
        template_name=tpl_name,
        language_code=lang_code,
        db=db,
    )

    if success:
        # Registrar en la conversación que se envió la plantilla de apertura
        new_msg = Message(
            conversation_id=conv.id,
            sender="bot",
            text=f"[📲 Plantilla de Apertura Enviada: {tpl_name}]",
        )
        db.add(new_msg)
        db.commit()

    cron_logger.log(
        f"[Chat] 📲 {_user.nombre} envió plantilla '{tpl_name}' a {conv.whatsapp_phone}: "
        f"{'✅ Éxito' if success else '❌ Falló'} ({detail})"
    )

    return {
        "status": "success" if success else "error",
        "whatsapp_sent": success,
        "whatsapp_detail": detail,
        "template_name": tpl_name,
        "phone": conv.whatsapp_phone,
        "message": f"Plantilla '{tpl_name}' enviada con éxito." if success else f"Error al enviar plantilla: {detail}",
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
            mode="analista",
            is_bot_active=False,
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


# ─── GET System Logs (WhatsApp / Bot / Webhook) ────────────────────────────

CHAT_LOG_PREFIXES = (
    "[WhatsApp", "[Chat]", "[Honeypot", "[Curtis", "[Webhook",
    "[NLP", "[Meta", "[DeepSeek", "[Cerebras", "[LLM",
)

@router.get("/system-logs")
def get_system_logs(
    last_n: int = 150,
    filter: str = "",
    _user: User = Depends(get_current_user),
):
    """
    Devuelve los últimos logs del sistema relacionados con Chat, WhatsApp, Bot y Webhook.
    Opcionalmente filtra por texto libre.
    """
    all_logs = cron_logger.get_logs(last_n=500)

    # Filtrar solo logs relevantes al chat/whatsapp/bot
    chat_logs = []
    for line in all_logs:
        # Extraer la parte después del timestamp [HH:MM:SS]
        content = line[11:] if len(line) > 11 and line[0] == '[' else line
        if any(content.startswith(prefix) for prefix in CHAT_LOG_PREFIXES):
            chat_logs.append(line)

    # Filtro de texto libre adicional
    if filter and filter.strip():
        f_lower = filter.strip().lower()
        chat_logs = [l for l in chat_logs if f_lower in l.lower()]

    return {
        "logs": chat_logs[-last_n:],
        "total": len(chat_logs),
    }
