"""Normalización del alcance geográfico de las búsquedas."""

import re

ARGENTINA = "Argentina"

ARGENTINA_PROVINCES = {
    "CABA",
    "Buenos Aires",
    "Catamarca",
    "Chaco",
    "Chubut",
    "Córdoba",
    "Corrientes",
    "Entre Ríos",
    "Formosa",
    "Jujuy",
    "La Pampa",
    "La Rioja",
    "Mendoza",
    "Misiones",
    "Neuquén",
    "Río Negro",
    "Salta",
    "San Juan",
    "San Luis",
    "Santa Cruz",
    "Santa Fe",
    "Santiago del Estero",
    "Tierra del Fuego",
    "Tucumán",
}

FOREIGN_LOCATION_PATTERNS = (
    r"\bbrasil\b", r"\bbrazil\b", r"\beeuu\b", r"\bestados unidos\b",
    r"\bunited states\b", r"\bmiami\b", r"\borlando\b", r"\bflorida\b",
    r"\bcalifornia\b", r"\btexas\b", r"\bnew york\b", r"\blos angeles\b",
    r"\bchile\b", r"\buruguay\b", r"\bmexico\b", r"\bespaña\b",
    r"\bcolombia\b", r"\bperu\b", r"\becuador\b", r"\bvenezuela\b",
    r"\bparaguay\b", r"\bbolivia\b", r"\bguatemala\b", r"\bcosta rica\b",
    r"\bpanama\b", r"\bhonduras\b", r"\bel salvador\b", r"\bnicaragua\b",
    r"\brepublica dominicana\b", r"\bpuerto rico\b", r"\bmadrid\b",
    r"\bbarcelona\b", r"\bbogota\b", r"\blima\b", r"\bsantiago de chile\b",
    r"\bmontevideo\b", r"\basunci[oó]n\b", r"\busa\b",
)

# Patrones de monedas extranjeras
FOREIGN_CURRENCY_PATTERNS = (
    r"\busd\b", r"\bu\$", r"\bdolar\b", r"\breal\b", r"\br\$",
    r"\bsol\b", r"\bpeso mx\b", r"\bmxn\b", r"\bcop\b",
    r"\bcrc\b", r"\bpen\b", r"\buyu\b", r"\beur\b", r"\b€\b",
)

# Patrones de idiomas extranjeros (español de otros países)
FOREIGN_LANGUAGE_PATTERNS = (
    # Portugués (Brasil)
    r"\bvocê\b", r"\btem\b", r"\bpor favor\b", r"\bmuito\b",
    # Inglés
    r"\bthank you\b", r"\bplease\b", r"\bprice\b",
)

SPANISH_TEXT_PATTERNS = (
    r"\b(?:venta|vendo|vendemos|env[ií]o|env[ií]os|talle|talles|talla|"
    r"precio|pesos|cuotas|consult[aá]|disponible|stock|compr[aá]|"
    r"zapatillas?|calzados?|ropa|remeras?|camperas?|buzos?|conjuntos?|"
    r"botines|medias|gorras?|mochilas?|cat[aá]logo|mujer|dama|blancas?|"
    r"negras?|beige|original(?:es)?|importad[oa]s?|"
    r"calidad\s+premium|importad[oa]s?\s+premium|"
    r"r[eé]plica|imitaci[oó]n|falsificad[oa]|truch[oa]|copia|clon|espejo)\b",
)

NON_SPANISH_TEXT_PATTERNS = (
    # Indicadores distintivos de portugués
    r"\b(?:você|frete|tamanho|pix|promoção|preço|entrega|estoque)\b",
    # Indicadores distintivos de inglés
    r"\b(?:shipping|size|price|available|buy now|for sale|free delivery|"
    r"dm to order|new arrivals)\b",
)

NON_ARGENTINA_CONTENT_PATTERNS = FOREIGN_LOCATION_PATTERNS + (
    r"\bpyg\b",
    r"\bgs\b\.?",
    r"\bguaran[ií](?:es)?\b",
    r"\bsoles\b",
    r"\bpen\b",
    r"\bs/\s*\d",
    r"\bclp\b",
    r"\bpesos?\s+chilenos?\b",
    r"\buyu\b",
    r"\bpesos?\s+uruguayos?\b",
)


def normalize_argentina_locations(locations) -> list[str]:
    """Permite solo Argentina o sus provincias y descarta ubicaciones externas."""
    if isinstance(locations, str):
        locations = [locations]

    normalized = []
    for location in locations or []:
        if not isinstance(location, str):
            continue
        value = location.strip()
        if not value:
            continue
        if value.casefold() == ARGENTINA.casefold():
            return [ARGENTINA]
        province = next(
            (candidate for candidate in ARGENTINA_PROVINCES if candidate.casefold() == value.casefold()),
            None,
        )
        if province and province not in normalized:
            normalized.append(province)

    return normalized or [ARGENTINA]


def is_explicitly_foreign_location(location) -> bool:
    """Return true only when the provider's location names a known foreign place."""
    if not isinstance(location, str) or not location.strip():
        return False
    normalized = " ".join(location.casefold().split())
    return any(re.search(pattern, normalized) for pattern in FOREIGN_LOCATION_PATTERNS)


def has_non_argentina_content(text: str) -> bool:
    """Detect neighboring-country locations and currencies in a listing's text."""
    if not isinstance(text, str) or not text.strip():
        return False
    normalized = " ".join(text.casefold().split())
    return any(re.search(pattern, normalized) for pattern in NON_ARGENTINA_CONTENT_PATTERNS)


def is_spanish_text(text: str) -> bool:
    """Require Spanish sales/counterfeit language and reject clear English or Portuguese."""
    if not isinstance(text, str) or not text.strip():
        return False
    normalized = " ".join(text.casefold().split())
    if any(re.search(pattern, normalized) for pattern in NON_SPANISH_TEXT_PATTERNS):
        return False
    return any(re.search(pattern, normalized) for pattern in SPANISH_TEXT_PATTERNS)


def detect_foreign_content(text: str) -> bool:
    """
    Detecta si el contenido es de otros países por:
    - Monedas extranjeras (USD, Real, Sol, etc.)
    - Idiomas extranjeros (Portugués, Inglés, etc.)
    - Términos locales de otros países
    
    Retorna True si detecta contenido extranjero.
    MÁS AGRESIVO: rechaza cualquier cosa que parezca no-argentina
    """
    if not isinstance(text, str) or not text.strip():
        return False
    
    normalized = " ".join(text.casefold().split())
    
    # Detectar monedas extranjeras (agresivo)
    if any(re.search(pattern, normalized) for pattern in FOREIGN_CURRENCY_PATTERNS):
        return True
    
    # Detectar palabras clave ENGLISH (muy común en otros países)
    english_patterns = [
        r"\bfor\b", r"\byou\b", r"\bsize\b", r"\bcolor\b", r"\bshipping\b",
        r"\bprice\b", r"\bcustom\b", r"\bfree\b", r"\bnew\b", r"\boriginal\b",
        r"\bauthenticated\b", r"\boffer\b", r"\bbrand new\b", r"\bunused\b",
    ]
    english_count = sum(1 for pattern in english_patterns if re.search(pattern, normalized))
    if english_count >= 3:  # Si tiene 3+ palabras en inglés, es extranjero
        return True
    
    # Detectar palabras clave PORTUGUÉS (muy común en Brasil)
    portuguese_patterns = [
        r"\bvocê\b", r"\btem\b", r"\bpara\b", r"\bmais\b",
        r"\bnovo\b", r"\boriginal\b", r"\bcor\b", r"\btamanho\b",
        r"\bfrete\b", r"\bencomenda\b", r"\bmercado\b", r"\bbrazil\b",
        r"\breal\b", r"\br\s*\$", r"\bvezes\b",
    ]
    portuguese_count = sum(1 for pattern in portuguese_patterns if re.search(pattern, normalized))
    if portuguese_count >= 2:  # Si tiene 2+ palabras en portugués, es Brasil
        return True
    
    # Detectar términos colombianos/mexicanos
    colombian_patterns = [
        r"\bcop\b", r"\bpesos\b", r"\bmexicano\b", r"\bchileno\b",
        r"\bperuana\b", r"\bboliviana\b",
    ]
    if any(re.search(pattern, normalized) for pattern in colombian_patterns):
        return True
    
    # Detectar nombres de ciudades extranjeras
    foreign_cities = [
        r"\bsão paulo\b", r"\brio\b", r"\brecife\b", r"\bmanaus\b",
        r"\bmexico city\b", r"\bcdmx\b", r"\blima\b", r"\bcusco\b",
        r"\bcolombia\b", r"\briojaneiro\b",
    ]
    if any(re.search(pattern, normalized) for pattern in foreign_cities):
        return True
    
    return False