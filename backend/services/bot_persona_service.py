"""
Servicio para gestionar la personalidad, instrucciones (system prompt) y mensajes de apertura
del Bot Honeypot en Net Holmes.
Permite a los analistas y administradores personalizar cómo habla el Bot desde la web.
"""

import json
from database import SessionLocal
from models.api_key_setting import ApiKeySetting
from services.cron_logger import cron_logger

SERVICE_NAME = "bot_persona"

DEFAULT_OPENING_MESSAGE = (
    "Hola! Que tal? Te escribo por el producto que tenes publicado, sigue disponible?"
)

DEFAULT_SYSTEM_PROMPT = """Eres un comprador particular interesado en comprar el producto publicado. Estás chateando por WhatsApp con el vendedor de forma casual y directa.

OBJETIVOS CLAVE DE INVESTIGACIÓN (HONEYPOT):
1. Adapta el vocabulario, modismos y expresiones al país y región indicados en el contexto (ej. usa "che", "lucas", "salado", "de una" si es Argentina).
2. Actúa como un comprador real, amable y relajado. Respuestas CORTAS de 1 o 2 oraciones como máximo (estilo chat de WhatsApp real). NUNCA escribas respuestas largas o formales.
3. Si el vendedor te confirma disponibilidad o precio:
   - Pide los datos de pago con naturalidad: "¿Me pasás tu Alias o CVU de Mercado Pago así te hago la transferencia?" o "¿Qué banco tenés?".
   - Si te pasa el alias, pregunta: "¿A nombre de quién figura la cuenta así verifico antes de transferirte?".
4. Si coordinan la entrega:
   - Pregunta: "¿Por qué zona estás para retirar en persona o cómo hacés con los envíos?".
5. REGLAS CRÍTICAS DE COMPORTAMIENTO:
   - NUNCA digas que eres un bot, ni una IA, ni que estás investigando.
   - NUNCA respondas preguntas de cultura general, matemáticas, código o tareas escolares.
   - Si el vendedor dice algo confuso, responde cortante o vuelve a preguntar por el producto y el pago.
   - Mantén siempre el foco en comprar el producto y obtener los datos de cobro (Alias/CBU/Titular) y ubicación.
"""

def get_bot_persona_config(db=None) -> dict:
    """
    Obtiene la configuración actual de personalidad del bot desde la base de datos.
    Si no está configurada, retorna los valores predeterminados de alta calidad.
    """
    session = db or SessionLocal()
    try:
        setting = session.query(ApiKeySetting).filter(
            ApiKeySetting.service_name == SERVICE_NAME
        ).first()

        if setting and setting.extra_config:
            try:
                cfg = json.loads(setting.extra_config)
                return {
                    "system_prompt": cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
                    "opening_message": cfg.get("opening_message") or DEFAULT_OPENING_MESSAGE,
                    "is_custom": True,
                    "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
                    "default_opening_message": DEFAULT_OPENING_MESSAGE,
                }
            except Exception:
                pass

        return {
            "system_prompt": DEFAULT_SYSTEM_PROMPT,
            "opening_message": DEFAULT_OPENING_MESSAGE,
            "is_custom": False,
            "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
            "default_opening_message": DEFAULT_OPENING_MESSAGE,
        }
    finally:
        if not db:
            session.close()


def save_bot_persona_config(system_prompt: str, opening_message: str, db=None) -> dict:
    """
    Guarda la personalidad e instrucciones personalizadas del bot en la base de datos.
    """
    session = db or SessionLocal()
    try:
        setting = session.query(ApiKeySetting).filter(
            ApiKeySetting.service_name == SERVICE_NAME
        ).first()

        payload = {
            "system_prompt": (system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT,
            "opening_message": (opening_message or "").strip() or DEFAULT_OPENING_MESSAGE,
        }

        if not setting:
            setting = ApiKeySetting(
                service_name=SERVICE_NAME,
                api_key="configured",
                is_active=True,
                extra_config=json.dumps(payload),
            )
            session.add(setting)
        else:
            setting.extra_config = json.dumps(payload)
            setting.is_active = True

        session.commit()
        session.refresh(setting)
        cron_logger.log("[Bot Persona] 🧠 Nuevas instrucciones y personalidad del bot guardadas en base de datos.")

        return {
            "status": "success",
            "message": "Instrucciones del bot guardadas exitosamente.",
            "system_prompt": payload["system_prompt"],
            "opening_message": payload["opening_message"],
        }
    finally:
        if not db:
            session.close()
