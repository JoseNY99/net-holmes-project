"""Extracción conservadora de campos comerciales publicados por el vendedor."""

import re
from typing import Any
from urllib.parse import urlsplit


_PRICE_PATTERNS = (
    # Exige etiqueta o moneda para no confundir teléfonos, talles o fechas con precios.
    r"(?:precio|preço|price)\s*(?:de|:|=|-)?\s*(?:ars|ar\$|mxn|brl|r\$|\$)?\s*([0-9]+(?:[.,][0-9]{1,3})*)",
    r"(?:ars|ar\$|mxn|brl|r\$|\$)\s*([0-9]+(?:[.,][0-9]{1,3})*)",
)


def _number_from_price(raw: str) -> float | None:
    value = re.sub(r"\s+", "", raw).rstrip(".,")
    if not value or not re.search(r"\d", value):
        return None

    if "." in value and "," in value:
        decimal = "." if value.rfind(".") > value.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        value = value.replace(thousands, "").replace(decimal, ".")
    elif "," in value or "." in value:
        separator = "," if "," in value else "."
        groups = value.split(separator)
        # En publicaciones regionales 25.000 y 1,299 representan miles.
        if len(groups) > 1 and all(len(group) == 3 for group in groups[1:]):
            value = "".join(groups)
        else:
            value = value.replace(separator, ".", 1).replace(separator, "")

    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except ValueError:
        return None


def extract_price(*values: Any) -> float | None:
    """Devuelve el primer precio explícito, incluso si solo figura en la descripción."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value) if value > 0 else None
        text = str(value)
        for pattern in _PRICE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and (parsed := _number_from_price(match.group(1))) is not None:
                return parsed
        # Un campo técnico price puede contener solo el número.
        if len(values) == 1 and (parsed := _number_from_price(text)) is not None:
            return parsed
    return None


def extract_facebook_author(item: dict, title: str = "", description: str = "") -> str | None:
    """Prioriza al autor del post sobre el grupo o página que lo contiene."""
    nested_fields = ("author", "user", "owner", "actor", "profile", "publisher")
    direct_fields = (
        "authorName", "author_name", "postAuthor", "post_author",
        "userName", "username", "ownerName", "owner_name",
    )
    for field in direct_fields:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for field in nested_fields:
        value = item.get(field)
        if isinstance(value, dict):
            name = value.get("name") or value.get("fullName") or value.get("username")
            if isinstance(name, str) and name.strip():
                return name.strip()

    text = f"{title}\n{description}"
    explicit = re.search(
        r"\b(?:vendido\s+por|publicado\s+por|vendedor|seller|autor)\s*:?\s*"
        r"([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñÑ.'-]*(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñÑ.'-]*){1,3})",
        text, re.IGNORECASE,
    )
    if explicit:
        return explicit.group(1).strip()

    # Formato habitual de snippets de posts de grupos: Nombre Apellido · fecha · texto.
    byline = re.search(
        r"(?:^|\n|[|—-]\s*)([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúñÑ.'-]+"
        r"(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúñÑ.'-]+){1,3})\s*[·•]\s*"
        r"(?:\d{1,2}(?:\s+de\s+|/|-)|hace\s+|ayer\b|\d+[\s\w]*ago\b)",
        text, re.IGNORECASE,
    )
    return byline.group(1).strip() if byline else None


def extract_instagram_author(*texts: str) -> str | None:
    """Extrae la cuenta propietaria de formatos indexados y OpenGraph de Instagram."""
    patterns = (
        r"\b([A-Za-z0-9_.]{2,30})['’]s\s+profile\s+picture\b",
        r"\bfoto\s+del\s+perfil\s+de\s+([A-Za-z0-9_.]{2,30})\b",
        r"\((@[A-Za-z0-9_.]{2,30})\)",
        r"(?:^|\s)(@[A-Za-z0-9_.]{2,30})\s+(?:on|en)\s+Instagram\b",
        r"\b([A-Za-z0-9_.]{2,30})\s+on\s+Instagram\b",
        r"-\s*([A-Za-z0-9_.]{2,30})\s+on\s+Instagram\b",
    )
    for text in texts:
        if not text:
            continue
        for pattern in patterns:
            match = re.search(pattern, str(text), re.IGNORECASE)
            if match:
                return "@" + match.group(1).lstrip("@")
    return None


_INSTAGRAM_RESERVED = {
    "p", "reel", "reels", "explore", "accounts", "tags", "stories",
    "direct", "about", "legal", "privacy", "developer", "web",
}


def instagram_url_identity(url: str) -> tuple[str | None, str | None]:
    """Devuelve (tipo, username) sin inferir autor desde IDs de posts o reels."""
    parsed = urlsplit(str(url or ""))
    if (parsed.hostname or "").casefold().removeprefix("www.") != "instagram.com":
        return None, None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None, None
    first = parts[0].casefold()
    if first in {"p", "reel", "reels"}:
        return ("reel" if first in {"reel", "reels"} else "post"), None
    if first in _INSTAGRAM_RESERVED or not re.fullmatch(r"[A-Za-z0-9._]{2,30}", parts[0]):
        return None, None
    return "profile", "@" + parts[0]


