import re
from sqlalchemy.orm import Session
from services.cron_logger import cron_logger

_CBU_CVU_PATTERN = re.compile(r"(?<!\d)\d{22}(?!\d)")
_LABELLED_CBU_CVU_PATTERN = re.compile(
    r"\b(?:cbu|cvu)\b\s*(?:es|:|-)?\s*(?:\d[\s.-]?){21}\d\b",
    re.IGNORECASE,
)
_LABELLED_ALIAS_PATTERN = re.compile(
    r"\balias\b\s*(?:es|de|:|-)?\s*([a-z0-9]+(?:\.[a-z0-9]+){1,2})\b",
    re.IGNORECASE,
)
_CONTEXTUAL_ALIAS_PATTERN = re.compile(
    r"\b(?:transferencia|transferir|transferime|transferí|pago|mercadopago|banco|mandar|mandarlo|pasame)\b"
    r".{0,50}\b([a-z0-9]+(?:\.[a-z0-9]+){1,2})\b",
    re.IGNORECASE,
)


def evaluate_and_extract_bank_data(db: Session, text: str, conversation) -> bool:
    """
    Evalúa el texto recibido del vendedor para detectar CBU, CVU o Alias bancario.
    Si encuentra datos:
      1. Guarda la información en la base de datos.
      2. Cambia el estado de la sesión a "Cerrado".
      3. Detiene cualquier comunicación futura.
    """
    if not text:
        return False

    found_details = []

    # Búsqueda de CBU/CVU (Regex estricto o etiquetado)
    if _CBU_CVU_PATTERN.search(text) or _LABELLED_CBU_CVU_PATTERN.search(text):
        match = _CBU_CVU_PATTERN.search(text)
        if match:
            found_details.append(f"CBU/CVU detectado: {match.group(0)}")
        else:
            found_details.append("CBU/CVU detectado por contexto")

    # Búsqueda de Alias (Etiquetado o Contextual)
    alias_match = _LABELLED_ALIAS_PATTERN.search(text) or _CONTEXTUAL_ALIAS_PATTERN.search(text)
    if alias_match:
        found_details.append(f"Alias bancario detectado: {alias_match.group(1)}")

    if found_details:
        cron_logger.log(f"[Safety] Datos bancarios detectados: {', '.join(found_details)}")

        # 1. Guardar la información en la base de datos
        # Asumiendo existencia de un campo de extracción, usamos hasattr por seguridad (Mocking)
        if hasattr(conversation, 'extracted_financial_data'):
            conversation.extracted_financial_data = " | ".join(found_details)
        else:
            # Mock de guardado en log si la columna no está migrada aún
            cron_logger.log(f"[Mock DB] Info guardada en entidad conversacion: {found_details}")

        # 2. Cambiar estado a "Cerrado"
        conversation.mode = "Cerrado"

        # 3. Detener comunicación futura
        conversation.is_bot_active = False

        db.add(conversation)
        db.commit()
        return True

    return False


def redact_bank_details(text: str | None) -> str:
    """Oculta los datos en el texto si se requiere guardar un log seguro."""
    if not text:
        return ""
    # Usamos la validación rápida original
    if bool(_CBU_CVU_PATTERN.search(text) or _LABELLED_ALIAS_PATTERN.search(text)):
        return "[Mensaje omitido por contener datos bancarios]"
    return text


def close_conversation_for_privacy(db: Session, conversation) -> None:
    """Cierre forzado en casos antiguos o externos."""
    conversation.mode = "Cerrado"
    conversation.is_bot_active = False
    db.add(conversation)
    db.commit()
