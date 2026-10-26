"""Filtros y claves de identidad exclusivos de la búsqueda del dashboard."""

import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from services.dashboard_scope import COUNTRIES, contains, folded

UNKNOWN_SELLERS = {"", "desconocido", "vendedor no identificado", "usuario desconocido", "@vendedor_tiktok"}


def canonical_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        for prefix in ("www.", "m.", "web.", "mobile."):
            if host.startswith(prefix):
                host = host[len(prefix):]
                break
        if parsed.scheme not in ("https", "http") or not host or parsed.username or parsed.password:
            return ""
        query = parse_qs(parsed.query)
        # Facebook identifica publicaciones antiguas con estos parámetros.
        retained = {k: query[k][0] for k in ("story_fbid", "id", "v") if k in query} if host == "facebook.com" else {}
        return urlunsplit(("https", host, parsed.path.rstrip("/"), urlencode(retained), ""))
    except ValueError:
        return ""


def evidence_key(url: str) -> str:
    url = canonical_url(url)
    parsed = urlsplit(url)
    path = parsed.path
    if parsed.hostname == "instagram.com":
        match = re.match(r"/(?:p|reel|reels)/([^/]+)", path)
        if match:
            return "instagram:" + match[1]
    if parsed.hostname == "facebook.com":
        match = re.search(r"/(?:marketplace/item|posts|videos)/(\w+)", path)
        if match:
            return "facebook:" + match[1]
        query = parse_qs(parsed.query)
        if query.get("story_fbid"):
            return "facebook:" + query["story_fbid"][0]
    if parsed.hostname == "tiktok.com":
        match = re.search(r"/(?:video|photo)/(\d+)", path)
        if match:
            return "tiktok:" + match[1]
    if parsed.hostname and ("mercadolibre" in parsed.hostname or "mercadolivre" in parsed.hostname):
        match = re.search(r"\b(ML[ABM])-?(\d+)", url, re.I)
        if match:
            return match[1].upper() + match[2]
    return url


def direct_link(url: str, platform: str, country: str) -> bool:
    parsed = urlsplit(canonical_url(url))
    host, path = parsed.hostname or "", parsed.path
    if platform == "facebook":
        return host == "facebook.com" and (bool(re.search(r"/(?:marketplace/item|posts|videos)/[^/]+", path)) or (path == "/story.php" and "story_fbid=" in parsed.query))
    if platform == "instagram":
        return host == "instagram.com" and bool(re.match(r"/(?:p|reel|reels)/[\w-]+$", path))
    if platform == "tiktok":
        return host == "tiktok.com" and bool(re.match(r"/@[\w.-]+/(?:video|photo)/\d+$", path))
    market = COUNTRIES[country]["market"]
    return (host == market or host.endswith("." + market)) and bool(re.search(r"ML[ABM]-?\d+", path, re.I))


def seller_handle(url: str, text: str = "") -> str | None:
    parsed = urlsplit(canonical_url(url))
    match = re.search(r"tiktok\.com/@([\w.-]+)", canonical_url(url))
    if match:
        return "@" + match[1].casefold()
    if parsed.hostname == "facebook.com":
        match = re.match(r"/([^/]+)/(?:posts|videos)/", parsed.path)
        if match and match[1] not in ("groups", "marketplace"):
            return "@" + match[1].casefold()
    # @cuenta en los snippets de Instagram: no usar menciones de terceros.
    if parsed.hostname == "instagram.com":
        match = re.search(r"\((@[\w.]+)\)|^(@[\w.]+)\s|([\w.]+) on Instagram", text, re.I)
        if match:
            return ("@" + next(g for g in match.groups() if g).lstrip("@")).casefold()
    return None


def account_key(platform: str, brand: str, seller: str) -> tuple | None:
    # Solo usuarios inequívocos; nunca agrupar por un nombre de persona común.
    if not seller.startswith("@") or folded(seller) in UNKNOWN_SELLERS:
        return None
    return platform.casefold(), folded(brand), seller.casefold()


def counterfeit_terms(text: str) -> list[str]:
    value = folded(text)
    # Premium, barato o importado por sí solos no acreditan una réplica.
    pattern = r"\b(?:replicas?|imitaciones?|imitacao|imitacoes|falsificad[oa]s?|fakes?|truch[oa]s?|clones?|clon|g5|aaa)\b|(?<!\d)1\s*:\s*1(?!\d)"
    found = []
    for match in re.finditer(pattern, value):
        prefix = value[max(0, match.start() - 55):match.start()]
        if re.search(r"\b(?:no|nao|sin|sem|not|ni)\s+(?:(?:es|son|sao|e|vendemos|vendo|vende|trabajamos con|trabalhamos com)\s+)?$", prefix):
            continue
        found.append(match[0])
    if re.search(r"\b(?:como (?:identificar|detectar|reconocer)|como saber|denuncia|alerta de estafa|combate a falsificacao)\b", value):
        return []
    direct_terms = [term for term in found if term not in {"aaa", "g5", "1:1", "1 : 1"}]
    if not direct_terms and re.search(r"\b(?:original(?:es)?|autentic[oa]s?)\b", value):
        return []
    return list(dict.fromkeys(found))


def is_official(brand: dict, platform: str, seller: str, url: str, text: str) -> bool:
    handle = seller.lstrip("@").casefold()
    parsed = urlsplit(url)
    parts = {p.lstrip("@").casefold() for p in parsed.path.split("/") if p}
    for entry in brand["official"]:
        if entry["platform"].casefold() not in ("todas", platform):
            continue
        registered = entry["handle"].strip().rstrip("/")
        if "://" in registered:
            registered = urlsplit(registered).path.strip("/").lstrip("@")
        registered = registered.lstrip("@").casefold()
        if registered and (registered == handle or registered in parts):
            return True
    root = re.sub(r"\W", "", folded(brand["name"]))
    official_handles = {root + suffix for suffix in ("", "ar", "br", "mx", "argentina", "brasil", "mexico", "oficial", "official", "store")}
    if handle and re.sub(r"\W", "", folded(handle)) in official_handles:
        return True
    return bool(re.search(r"\b(?:tienda|loja|store)\s+oficial\b", folded(text)))


def qualifies(item: dict, brand: dict) -> list[str]:
    text = f"{item['title']} {item['description']}"
    if not contains(text, brand["name"]):
        return []
    if brand["products"] and not any(contains(text, product) for product in brand["products"]):
        return []
    if is_official(brand, item["plataforma"], item["seller"], item["url"], text):
        return []
    terms = counterfeit_terms(text)
    if not terms:
        return []
    sales = r"\b(?:venta|vendo|vendemos|venda|preco|precio|stock|estoque|envios?|entrega|frete|comprar|compra|catalogo|disponible|disponivel|pedidos?|whatsapp|tallas?|talles?|tamanhos?|zapatillas?|tenis|camisetas?|remeras?|calzados?)\b|[$]"
    if item["plataforma"] not in ("facebook", "mercadolibre") and not re.search(sales, folded(text)):
        return []
    return terms
