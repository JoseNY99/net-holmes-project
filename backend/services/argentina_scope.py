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
    r"\bmontevideo\b", r"\basuncion\b", r"\busa\b",
)

# Patrones de monedas extranjeras
FOREIGN_CURRENCY_PATTERNS = (
    r"\br\$", r"\breais\b", r"\bpeso mx\b", r"\bmxn\b", r"\bcop\b",
    r"\buyu\b", r"\beur\b", r"€", r"\binr\b", r"₹", r"\bgbp\b", r"£",
)

# Patrones de idiomas extranjeros (español de otros países)
FOREIGN_LANGUAGE_PATTERNS = (
    # Portugués (Brasil)
    r"\bvocê\b", r"\btem\b", r"\bpor favor\b", r"\bmuito\b",
    # Inglés
    r"\bthank you\b", r"\bplease\b", r"\bprice\b",
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


_ES_WORDS = {
    "de","la","el","en","y","que","los","las","con","por","para","un","una","es","se","del","al",
    "lo","mas","más","muy","tu","te","mi","me","su","hay","tengo","precio","envios","envíos",
    "talle","consultar","consulta","disponible","calidad","zapatillas","remera","camiseta","camisetas",
}
_PT_WORDS = {
    "você","voce","não","nao","uma","mais","muito","para","com","são","tem","paixão","paixao",
    "camisa","tênis","tenis","frete","entrega","comprar","aqui","nosso","nossa","obrigado","também",
    "tambem","pra","dos","das","isso","está","esta","ele","ela","seu","sua","tamanho","encomenda",
}
_EN_WORDS = {
    "the","and","for","with","you","your","this","that","are","is","in","on","at","of","to","they",
    "their","these","opening","discount","brands","giving","price","shipping","size","free","available",
    "likes","comments","on","from","our","we","new","sale","shop","store","order","dm",
}

ARGENTINA_SIGNALS = (
    r"\bargentin[ao]s?\b", r"\barg\b", r"\bcaba\b", r"\bbs\.?\s?as\b", r"\bbuenos aires\b",
    r"\bgba\b", r"\bzona (norte|sur|oeste)\b", r"\bconurbano\b",
    r"\b(catamarca|chaco|chubut|c[oó]rdoba|corrientes|entre r[ií]os|formosa|jujuy|la pampa|la rioja|mendoza|misiones|neuqu[eé]n|r[ií]o negro|salta|san juan|san luis|santa cruz|santa fe|santiago del estero|tierra del fuego|tucum[aá]n|rosario|mar del plata|la plata|bah[ií]a blanca)\b",
    r"\bars\b", r"\bpesos\b", r"\bluca(s)?\b", r"\bmil pesos\b", r"\btalle(s)?\b",
    r"\bandreani\b", r"\boca\b", r"\bcorreo argentino\b", r"\bmercado\s?pago\b", r"\bcbu\b",
    r"\balias\b", r"\benv[ií]os? a todo el pa[ií]s\b", r"\+?54\s?9?\s?\d{2,4}",
    r"\bretiro por\b", r"\bpibe\b", r"\bcurr[oa]\b", r"\bbarato\b", r"\btrucho\b", r"\bbondi\b",
    r"\$\s?\d{1,3}(\.\d{3})+",
)


def _language_scores(text: str) -> tuple[int, int, int]:
    words = re.findall(r"[a-záéíóúñãõçê]+", text.casefold())
    es = sum(1 for w in words if w in _ES_WORDS)
    pt = sum(1 for w in words if w in _PT_WORDS)
    en = sum(1 for w in words if w in _EN_WORDS)
    return es, pt, en


def has_argentine_signal(text: str) -> bool:
    """True si el texto contiene jerga, lugares, moneda o logística típicamente argentinos."""
    if not isinstance(text, str) or not text.strip():
        return False
    normalized = " ".join(text.casefold().split())
    return any(re.search(p, normalized) for p in ARGENTINA_SIGNALS)


def detect_foreign_content(text: str) -> bool:
    """
    True si el contenido es claramente de otro país: idioma portugués/inglés dominante,
    moneda extranjera o ciudades/países extranjeros.
    """
    if not isinstance(text, str) or not text.strip():
        return False

    normalized = " ".join(text.casefold().split())

    if any(re.search(p, normalized) for p in FOREIGN_CURRENCY_PATTERNS):
        return True
    if any(re.search(p, normalized) for p in FOREIGN_LOCATION_PATTERNS):
        return True

    es, pt, en = _language_scores(normalized)
    if pt >= 2 and pt >= es:
        return True
    if en >= 3 and en > es:
        return True
    # Texto sin una sola palabra española y con vocabulario extranjero
    if es == 0 and (pt + en) >= 2:
        return True
    return False
