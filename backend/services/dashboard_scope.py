"""Alcance del dashboard. No modifica la configuración geográfica del cron."""

import re
import unicodedata

from config import PROVINCIAS_AR


def folded(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


COUNTRIES = {
    "Argentina": {
        "gl": "ar", "hl": "es", "region": "ar-es", "currency": "ARS", "dial": "54",
        "aliases": ["Argentina"], "market": "mercadolibre.com.ar",
        "phone_format": "+54 + área y número (10 dígitos); móvil: +54 9 + 10 dígitos",
        "provincias": [p["name"] for p in PROVINCIAS_AR],
    },
    "Brasil": {
        "gl": "br", "hl": "pt", "region": "br-pt", "currency": "BRL", "dial": "55",
        "aliases": ["Brasil", "Brazil"], "market": "mercadolivre.com.br",
        "phone_format": "+55 + DDD (2 dígitos) + fijo (8) o móvil (9, comienza con 9)",
        "provincias": [
            "Acre", "Alagoas", "Amapá", "Amazonas", "Bahia", "Ceará", "Distrito Federal",
            "Espírito Santo", "Goiás", "Maranhão", "Mato Grosso", "Mato Grosso do Sul",
            "Minas Gerais", "Pará", "Paraíba", "Paraná", "Pernambuco", "Piauí",
            "Rio de Janeiro", "Rio Grande do Norte", "Rio Grande do Sul", "Rondônia",
            "Roraima", "Santa Catarina", "São Paulo", "Sergipe", "Tocantins",
        ],
    },
    "México": {
        "gl": "mx", "hl": "es", "region": "mx-es", "currency": "MXN", "dial": "52",
        "aliases": ["México", "Mexico"], "market": "mercadolibre.com.mx",
        "phone_format": "+52 + 10 dígitos (sin 01, 044, 045 ni el antiguo 1 internacional)",
        "provincias": [
            "Aguascalientes", "Baja California", "Baja California Sur", "Campeche", "Chiapas",
            "Chihuahua", "Ciudad de México", "Coahuila", "Colima", "Durango", "Estado de México",
            "Guanajuato", "Guerrero", "Hidalgo", "Jalisco", "Michoacán", "Morelos", "Nayarit",
            "Nuevo León", "Oaxaca", "Puebla", "Querétaro", "Quintana Roo", "San Luis Potosí",
            "Sinaloa", "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatán", "Zacatecas",
        ],
    },
}


def contains(text: str, term: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(folded(term)) + r"(?!\w)", folded(text)))


def normalize_scope(pais: str, provincias: list[str]) -> tuple[str, list[str]]:
    country = next((name for name, cfg in COUNTRIES.items() if any(folded(pais.strip()) == folded(a) for a in cfg["aliases"])), None)
    if country is None:
        raise ValueError("Selecciona Argentina, Brasil o México.")
    allowed = {folded(p): p for p in COUNTRIES[country]["provincias"]}
    normalized = []
    for province in provincias:
        key = folded(province.strip())
        if key not in allowed:
            raise ValueError(f"La provincia o estado '{province}' no pertenece a {country}.")
        if allowed[key] not in normalized:
            normalized.append(allowed[key])
    return country, normalized


def observed_region(text: str, country: str) -> str | None:
    # Primero los nombres largos: Mato Grosso do Sul antes de Mato Grosso.
    return next((p for p in sorted(COUNTRIES[country]["provincias"], key=len, reverse=True) if contains(text, p)), None)


def matches_scope(text: str, url: str, country: str, province: str | None) -> bool:
    """La consulta del usuario nunca se usa como evidencia de ubicación."""
    cfg = COUNTRIES[country]
    if province and not contains(text, province):
        return False
    other_aliases = [a for name, data in COUNTRIES.items() if name != country for a in data["aliases"]]
    if any(contains(text, alias) for alias in other_aliases):
        return False
    country_signal = any(contains(text, alias) for alias in cfg["aliases"])
    country_signal |= bool(observed_region(text, country))
    country_signal |= cfg["market"] in url
    country_signal |= bool(re.search(r"\+" + cfg["dial"] + r"[\s(\d]", text))
    country_signal |= contains(text, cfg["currency"])
    if country == "Brasil":
        country_signal |= "r$" in text.casefold()
    return country_signal
