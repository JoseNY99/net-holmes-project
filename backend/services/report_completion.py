RECOLECCION_FIELDS = (
    "dni_cedula",
    "cuit_cuil_ruc",
    "banco",
    "alias_bancario",
    "cvu_cbu",
    "email",
    "direccion_exacta",
    "telefono_privado",
    "precio_final_cotizado",
)

FIELD_LABELS = {
    "dni_cedula": "DNI / cédula",
    "cuit_cuil_ruc": "CUIT / CUIL / RUC",
    "banco": "Banco / billetera",
    "alias_bancario": "Alias bancario",
    "cvu_cbu": "CVU / CBU",
    "email": "Correo electrónico",
    "direccion_exacta": "Dirección exacta",
    "telefono_privado": "Teléfono privado",
    "precio_final_cotizado": "Precio final cotizado",
}


def _read_value(data, key):
    if isinstance(data, dict):
        return data.get(key)
    return getattr(data, key, None)


def calculate_completion_percentage(report_data) -> float:
    """Calcula el porcentaje de campos de relevamiento de identidad completados."""
    profile_data = _read_value(report_data, "perfil") or report_data
    if profile_data is None:
        return 0.0

    completed_fields = sum(
        bool(str(_read_value(profile_data, field) or "").strip())
        for field in RECOLECCION_FIELDS
    )
    return round(completed_fields * 100 / len(RECOLECCION_FIELDS), 2)


def get_missing_recollection_fields(report_data) -> list[str]:
    """Return labels for empty fields counted toward final report completion."""
    profile_data = _read_value(report_data, "perfil") or report_data
    if profile_data is None:
        return [FIELD_LABELS[field] for field in RECOLECCION_FIELDS]
    return [
        FIELD_LABELS[field]
        for field in RECOLECCION_FIELDS
        if not bool(str(_read_value(profile_data, field) or "").strip())
    ]
