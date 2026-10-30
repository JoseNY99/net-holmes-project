"""Nomenclatura oficial y única para informes del área de PI."""

from datetime import datetime, timezone
import re

from sqlalchemy import text

from models.seizure_report import SeizureSequence


BRAND_CODES = {
    "puma": "PU", "new era": "NE", "lacoste": "LC", "tommy hilfiger": "TH",
    "calvin klein": "CK", "under armour": "UA", "mlb": "MLB", "nba": "NBA",
    "wella company": "WC", "polo": "PRL", "ralph lauren": "PRL", "among us": "AU",
    "universal studios": "US", "lego": "LE", "victoria's secret": "VP",
    "ray ban": "RB", "chanel": "CH", "alo": "AL", "nike": "NI",
}
REPORT_TYPES = {"INTELIGENCIA", "ESTUDIO_MERCADO", "ALLANAMIENTO"}


def normalize_report_type(value):
    normalized = re.sub(r"[^A-Z]+", "_", (value or "").strip().upper()).strip("_")
    aliases = {"ESTUDIO": "ESTUDIO_MERCADO", "ESTUDIO_DE_MERCADO": "ESTUDIO_MERCADO"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in REPORT_TYPES:
        raise ValueError("Tipo de informe inválido")
    return normalized


def brand_code(name):
    folded = re.sub(r"\s+", " ", (name or "").strip().casefold())
    return BRAND_CODES.get(folded) or "".join(word[0] for word in folded.split() if word)[:3].upper() or "NA"


def assign_reference(db, report_type, brand_name, *, brand_code_value=None):
    """Asigna el correlativo una sola vez dentro de la transacción actual."""
    report_type = normalize_report_type(report_type)
    scope = "ALLANAMIENTO" if report_type == "ALLANAMIENTO" else "IN"
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(73829401)"))
    sequence = db.query(SeizureSequence).filter_by(scope=scope).with_for_update().first()
    if not sequence:
        sequence = SeizureSequence(scope=scope, last_value=0)
        db.add(sequence); db.flush()
    sequence.last_value += 1
    year = datetime.now(timezone.utc).strftime("%y")
    code = (brand_code_value or brand_code(brand_name)).upper()
    middle = "-IN" if report_type in {"INTELIGENCIA", "ESTUDIO_MERCADO"} else ""
    return f"{sequence.last_value:03d}-{year}{middle}-{code}", code
