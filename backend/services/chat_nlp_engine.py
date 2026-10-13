"""
Motor de NLP Híbrido para el Chat Honeypot.
Pipeline de 2 capas:
  Capa 1 (Regex Rápida): Patrones conocidos de alta confianza (~0ms)
  Capa 2 (LLM Profunda): Cerebras/DeepSeek para contexto semántico (~200ms-2s)

Auto-upsert en PerfilInvestigacion (Fase 2) con audit trail.
"""

import re
import json
import asyncio
from sqlalchemy.orm import Session
from models.perfil_investigacion import PerfilInvestigacion
from models.chat import Message, Conversation
from models.reporte import ReporteBrandDefense
from models.audit_log import AuditLog
from services.cron_logger import cron_logger


# ─── Capa 1: Patrones Regex de Alta Confianza ──────────────────────────────

REGEX_PATTERNS = {
    "dni_cedula": [
        # DNI argentino: 7-8 dígitos, opcionalmente con puntos
        r'\b(\d{2}\.?\d{3}\.?\d{3})\b',
    ],
    "cuit_cuil_ruc": [
        # CUIT/CUIL: prefijo(20|23|24|27|30|33|34) + 8 dígitos + verificador
        r'\b((?:20|23|24|27|30|33|34)[\-\s]?\d{8}[\-\s]?\d)\b',
    ],
    "cvu_cbu": [
        # CBU/CVU: exactamente 22 dígitos consecutivos
        r'\b(\d{22})\b',
    ],
    "alias_bancario": [
        # Alias MercadoPago/banco: palabra.palabra.palabra (mín 2 segmentos)
        r'\b([a-zA-Z0-9]+\.[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*)\b',
    ],
    "email": [
        r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b',
    ],
    "telefono_privado": [
        # Teléfonos argentinos: +54, 011, 15, etc.
        r'(?:\+?54\s?9?\s?)?(?:11|[2368]\d)\s?\d{4}[\s\-]?\d{4}\b',
    ],
    "precio_final_cotizado": [
        # Precios: $45.000, USD 200, 15000, etc.
        r'(?:(?:ARS|USD|\$|U\$S)\s*\d[\d.,]*|\d[\d.,]*\s*(?:pesos|dólares|dolares|usd|ars))',
    ],
}

# Patrones que NO deben matchear como alias bancario (falsos positivos comunes)
ALIAS_BLACKLIST = {"www.facebook", "www.instagram", "www.mercadolibre", "api.whatsapp"}


def _extract_regex(text: str) -> dict:
    """
    Capa 1: Extrae entidades usando Regex de alta confianza.
    Retorna dict con los campos encontrados.
    """
    extracted = {}

    for field, patterns in REGEX_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1) if match.lastindex else match.group(0)
                value = value.strip()

                # Filtro anti-falsos-positivos para alias
                if field == "alias_bancario":
                    if value.lower() in ALIAS_BLACKLIST:
                        continue
                    # Un alias válido debe tener al menos 2 segmentos y no ser un dominio web
                    if value.count(".") < 1 or any(ext in value.lower() for ext in [".com", ".ar", ".net", ".org"]):
                        continue

                # Filtro para DNI: evitar números que son precios o IDs
                if field == "dni_cedula":
                    clean = value.replace(".", "")
                    if len(clean) < 7 or len(clean) > 8:
                        continue

                extracted[field] = value
                break  # Un match por campo es suficiente

    return extracted


# ─── Pipeline Completo ──────────────────────────────────────────────────────

def analyze_incoming_message(db: Session, message: Message):
    """
    Pipeline maestro de extracción de entidades.
    Ejecuta Regex primero, luego LLM si es necesario.
    Actualiza PerfilInvestigacion y Message.extracted_entities.
    
    Nota: Esta función es síncrona pero lanza el LLM de forma async internamente.
    """
    if message.sender not in ("infractor", "Infractor"):
        return

    text = message.text
    if not text or len(text.strip()) < 3:
        return

    # ═══ CAPA 1: Regex Rápida ═══
    regex_entities = _extract_regex(text)
    if regex_entities:
        cron_logger.log(f"[NLP Regex] 🔍 Entidades detectadas: {regex_entities}")

    # ═══ CAPA 2: LLM Profunda (solo si Regex no encontró suficiente) ═══
    llm_entities = {}
    # Disparar LLM si: no encontramos nada con Regex, o el mensaje es largo (puede tener contexto)
    if len(regex_entities) < 2 and len(text) > 20:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Estamos dentro de un contexto async (FastAPI) - crear task
                import concurrent.futures
                from services.llm_client import extract_entities_llm

                # Ejecutar en un nuevo loop en un thread separado
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(_run_async_extraction, text)
                    llm_entities = future.result(timeout=20)
            else:
                llm_entities = loop.run_until_complete(
                    __import__('services.llm_client', fromlist=['extract_entities_llm']).extract_entities_llm(text)
                )
        except Exception as e:
            cron_logger.log(f"[NLP LLM]  Error en extracción LLM: {e}")

    # ═══ MERGE: Regex tiene prioridad (más confiable), LLM complementa ═══
    merged = {**llm_entities, **regex_entities}

    # Guardar entidades extraídas en el Message
    if merged:
        message.extracted_entities = json.dumps(merged, ensure_ascii=False)
        db.add(message)

    # ═══ AUTO-UPSERT en PerfilInvestigacion ═══
    if merged:
        try:
            _upsert_perfil(db, message, merged)
        except Exception as e:
            cron_logger.log(f"[NLP]  Error en _upsert_perfil: {e}")

    try:
        db.commit()
    except Exception as e:
        cron_logger.log(f"[NLP]  Error al guardar entidades de mensaje: {e}")
        db.rollback()


def _run_async_extraction(text: str) -> dict:
    """Helper para ejecutar la extracción async del LLM en un thread separado."""
    import asyncio
    from services.llm_client import extract_entities_llm

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(extract_entities_llm(text))
    finally:
        loop.close()


def _upsert_perfil(db: Session, message: Message, entities: dict):
    """
    Actualiza o crea el PerfilInvestigacion con las entidades extraídas.
    Genera audit trail para cada campo actualizado.
    """
    conversation = db.query(Conversation).filter(
        Conversation.id == message.conversation_id
    ).first()
    if not conversation or not conversation.reporte_id:
        return

    reporte_id = conversation.reporte_id

    perfil = db.query(PerfilInvestigacion).filter(
        PerfilInvestigacion.reporte_id == reporte_id
    ).first()

    if not perfil:
        perfil = PerfilInvestigacion(reporte_id=reporte_id)
        db.add(perfil)
        db.flush()

    # Mapeo de claves LLM → columnas del modelo
    FIELD_MAP = {
        "dni_cedula": "dni_cedula",
        "cuit_cuil_ruc": "cuit_cuil_ruc",
        "cvu_cbu": "cvu_cbu",
        "alias_bancario": "alias_bancario",
        "email": "email",
        "telefono_privado": "telefono_privado",
        "direccion_exacta": "direccion_exacta",
        "precio_final_cotizado": "precio_final_cotizado",
        "banco": "banco",
    }

    # Buscar un user_id válido en la base de datos para no violar la Foreign Key de audit_logs
    valid_user_id = None
    try:
        from models.user import User
        admin_user = db.query(User).filter(User.rol.in_(["sup_admin", "admin"])).first()
        if admin_user:
            valid_user_id = admin_user.id
        else:
            first_u = db.query(User.id).first()
            if first_u:
                valid_user_id = first_u[0]
    except Exception:
        valid_user_id = None

    updated_fields = []
    for entity_key, db_field in FIELD_MAP.items():
        if entity_key in entities and hasattr(perfil, db_field):
            old_value = getattr(perfil, db_field, None) or "N/D"
            new_value = str(entities[entity_key])

            # Solo actualizar si es un valor nuevo
            if new_value != old_value:
                setattr(perfil, db_field, new_value)
                updated_fields.append(db_field)

                # Audit trail seguro
                if valid_user_id:
                    try:
                        audit = AuditLog(
                            reporte_id=reporte_id,
                            user_id=valid_user_id,
                            campo=db_field,
                            valor_anterior=str(old_value),
                            valor_nuevo=new_value,
                        )
                        db.add(audit)
                    except Exception as err:
                        cron_logger.log(f"[NLP AuditLog]  {err}")

    if updated_fields:
        cron_logger.log(f"[NLP → Perfil]  Campos actualizados en Reporte #{reporte_id}: {updated_fields}")
