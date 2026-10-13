import re
import unicodedata


_STOP_WORDS = {
    "a", "al", "con", "de", "del", "el", "en", "la", "las", "los",
    "para", "por", "sin", "un", "una", "y",
}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def matches_configured_product(text: str, brand_name: str, products) -> bool:
    """Return whether scraped text refers to a configured product, not just its brand."""
    active_products = [
        product for product in products or []
        if getattr(product, "estado", "activa") == "activa"
    ]
    brand_tokens = set(_normalize(brand_name).split())
    searchable_text = _normalize(text)
    if not searchable_text:
        return not active_products

    configured_descriptors = []
    for product in active_products:
        name = _normalize(getattr(product, "nombre", "") or "")
        description = _normalize(getattr(product, "descripcion", "") or "")
        name_tokens = [
            token for token in name.split()
            if token not in brand_tokens and token not in _STOP_WORDS
        ]
        description_tokens = [
            token for token in description.split()
            if token not in brand_tokens and token not in _STOP_WORDS
        ]
        descriptors = list(dict.fromkeys(name_tokens + description_tokens))
        if descriptors:
            configured_descriptors.append((name_tokens, descriptors))

    if not configured_descriptors:
        return True

    text_tokens = set(searchable_text.split())
    for name_tokens, descriptors in configured_descriptors:
        name_phrase = " ".join(name_tokens)
        if name_phrase and f" {name_phrase} " in f" {searchable_text} ":
            return True

        matched_count = sum(token in text_tokens for token in descriptors)
        required_matches = 1 if len(descriptors) == 1 else 2
        if matched_count >= required_matches:
            return True

    return False