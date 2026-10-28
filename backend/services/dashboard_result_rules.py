"""Filtros y claves de identidad exclusivos de la búsqueda del dashboard."""

import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from services.dashboard_scope import COUNTRIES, contains, folded

UNKNOWN_SELLERS = {"", "desconocido", "vendedor no identificado", "usuario desconocido", "@vendedor_tiktok"}
APPAREL_PRODUCT = re.compile(
    r"\b(?:vestuario|vestuário|indumentaria|ropa|roupas?|zapatillas?|calzados?|calçados?|remeras?|camperas?|chaquetas?|"
    r"buzos?|conjuntos?|joggings?|pantalones?|shorts?|musculosas?|camisetas?|"
    r"playeras?|sudaderas?|bermudas?|gorras?|bonés?|mochilas?|riñoneras?|bolsos?|bolsas?|medias|meias|calzas?|tops?|"
    r"vestidos?|camisas?|sweaters?|botines?|chuteiras?|sandalias?|t[eê]nis|sneakers?|pilusos?|peças?)\b",
    re.IGNORECASE,
)


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
        return host == "facebook.com" and (
            bool(re.search(r"/(?:marketplace/item|posts|videos|reel|reels)/[^/]+", path))
            or bool(re.search(r"/groups/[^/]+/(?:posts|permalink)/[^/]+", path))
            or (path == "/story.php" and "story_fbid=" in parsed.query)
        )
    if platform == "instagram":
        if host != "instagram.com":
            return False
        if re.match(r"/(?:p|reel|reels)/[\w-]+$", path):
            return True
        # Los perfiles pueden ser objetivos válidos si su contenido indexado
        # supera luego los mismos filtros de marca, producto, falsificación y país.
        match = re.fullmatch(r"/([A-Za-z0-9._]{2,30})", path)
        return bool(match and match.group(1).casefold() not in {
            "explore", "accounts", "tags", "stories", "direct", "about", "legal", "privacy",
        })
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
        from services.listing_fields import instagram_url_identity
        result_type, profile_username = instagram_url_identity(url)
        if result_type == "profile" and profile_username:
            return profile_username.casefold()
        match = re.search(r"\((@[\w.]+)\)|^(@[\w.]+)\s|([\w.]+) on Instagram", text, re.I)
        if match:
            return ("@" + next(g for g in match.groups() if g).lstrip("@")).casefold()
    return None


def valid_seller_identity(value: str | None) -> bool:
    """Impide utilizar IDs de publicaciones o cuentas numéricas como vendedor."""
    clean = " ".join(str(value or "").split()).strip()
    if not clean or folded(clean) in UNKNOWN_SELLERS:
        return False
    return re.fullmatch(r"@?[\d\s._-]+", clean) is None


def account_key(platform: str, brand: str, seller: str) -> tuple | None:
    # Solo usuarios inequívocos; nunca agrupar por un nombre de persona común.
    if not seller.startswith("@") or folded(seller) in UNKNOWN_SELLERS:
        return None
    return platform.casefold(), folded(brand), seller.casefold()


def counterfeit_terms(text: str, country: str | None = None) -> list[str]:
    value = folded(text)
    if country == "Brasil":
        # Lista cerrada solicitada para Brasil. No aceptar "loja", ofertas,
        # precios ni otros términos comerciales como prueba de falsificación.
        pattern = (
            r"\b(?:replicas?|falsificad[oa]s?|primeira\s+linha\s+premium|linha\s+premium|espelhad[oa]s?|"
            r"qualidade\s+1\s*:\s*1|ua|importad[oa]s?)\b|"
            r"\binspirad[oa]s?\b(?!\s+(?:em|no|na|nos|nas|por|pelo|pela|pelos|pelas)\b)"
        )
    else:
        # Premium, barato o importado por sí solos no acreditan una réplica fuera de Brasil.
        pattern = (
            r"\b(?:replicas?|imitaciones?|imitacao|imitacoes|falsificad[oa]s?|fakes?|truch[oa]s?|pirata|clones?|clon|"
            r"g5|aaa|triple\s+a|pk|top\s+quality|primeira\s+linha(?:\s+premium)?|linha\s+premium|espelhad[oa]|"
            r"super\s+clon|calidad\s+espejo|simil\s+original)\b|(?<!\d)1\s*:\s*1(?!\d)"
        )
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


def editorial_or_educational(text: str) -> bool:
    """Detecta notas, comparativas y consejos aunque mencionen la palabra fake."""
    value = folded(text)
    patterns = (
        r"\b(?:como|cómo)\s+(?:identificar|detectar|reconocer|saber|descubrir|distinguir)\b",
        r"\b(?:tips?|consejos?|gu[ií]as?|tutorial(?:es)?|reseñas?|reviews?|noticias?|reportajes?|documentales?)\b",
        r"\b(?:diferencias?|comparativa|comparaci[oó]n|señales?)\s+(?:entre|de|para)\b",
        r"\b(?:fake|falso|r[eé]plica)\s+o\s+(?:no|original|aut[eé]ntic[oa])\b",
        r"\b(?:son|es)\s+(?:fake|fals[oa])\s+o\s+no\b",
        r"\b(?:evitar|denuncia|alerta|combate)\s+(?:de|a|la|las)?\s*(?:estafa|falsificaci[oó]n|falsifica[cç][aã]o)\b",
        r"\b(?:reparar|reparaci[oó]n|restaurar|hospital)\b.{0,30}\b(?:tenis|zapatillas?|calzado)\b",
        r"\binteligencia\s+artificial\b",
        r"\b(?:nuevo\s+)?(?:lanzamiento|colecci[oó]n|modelo)\b.{0,45}\b(?:marca|puma|nike|adidas|tenis|calzado)\b",
        r"\b(?:ya\s+lo\s+hizo\s+posible|presenta\s+(?:su|el)\s+nuevo|innovaci[oó]n\s+en)\b",
        r"\b(?:continua\s+)?ganhando\s+espaco\s+(?:dentro\s+)?do\s+catalogo\b",
        r"\binspirad[oa]s?\s+(?:em|no|na|nos|nas|por|pelo|pela|pelos|pelas)\b",
        r"\bo\s+modelo\s+chega\s+(?:agora|em)\b",
        r"\b(?:versoes?|novas?\s+cores?)\b.{0,60}\b(?:disponiveis?|site)\b",
        r"\bdisponiveis?\s+no\s+site\s+d[ao]\s+\w+\b",
    )
    return any(re.search(pattern, value) for pattern in patterns)


def asks_for_authentication(text: str) -> bool:
    """Descarta consultas de compradores que piden validar un producto."""
    value = folded(text)
    patterns = (
        r"\b(?:alguien|quien)\s+(?:ha|a|sabe|conoce|pidio|compr[oó])\b",
        r"\b(?:sabr[aá]n|saben|me\s+pueden\s+ayudar|ayuda(?:r|me)?|qu[eé]\s+opinan)\b",
        r"\b(?:son|sera|ser[aá]|es)\s+(?:clon|fake|fals[oa]|r[eé]plica)\s+(?:o|\?|que\s+onda)\b",
        r"\b(?:cliente|vendedor)\s+me\s+(?:dice|dijo|asegura)\b",
        r"\b(?:qr|c[oó]digo)\b.{0,35}\b(?:no|sin)\b.{0,25}\b(?:informaci[oó]n|datos?)\b",
    )
    return any(re.search(pattern, value) for pattern in patterns)


def buyer_request(text: str) -> bool:
    """Distingue pedidos de compra/proveedor de ofertas publicadas por vendedores."""
    value = folded(text)
    patterns = (
        r"\b(?:alguien|qui[eé]n)\s+que\s+vend[ae]\b",
        r"\bbusco\s+(?:un\s+|una\s+)?(?:proveedor|vendedor|mayorista)\b",
        r"\bnecesito\s+(?:un\s+|una\s+)?(?:proveedor|vendedor|mayorista)\b",
        r"\b(?:d[oó]nde|donde)\s+(?:puedo\s+)?comprar\b",
    )
    return any(re.search(pattern, value) for pattern in patterns)


def legitimate_brand_promotion(text: str) -> bool:
    """Reconoce outlets y promociones comerciales que no ofrecen falsificaciones."""
    value = folded(text)
    patterns = (
        r"\boutlet\b",
        r"\boferta\s+exclusiva\b",
        r"\bpromocion\s+valida\b",
        r"\btiendas?\s+participantes?\b",
        r"\b(?:lleva|estrena|compra)\s*\d+\b.{0,30}\b(?:paga(?:ndo)?|precio)\b",
        r"\b\d+\s*(?:x|por)\s*\d+\b",
    )
    return any(re.search(pattern, value) for pattern in patterns)


def claims_authenticity(text: str) -> bool:
    value = folded(text)
    # Primero se quitan expresiones inequívocas como "no original".
    value = re.sub(r"\b(?:no|nao|não|sem|sin)\s+(?:es\s+|son\s+|ser\s+)?(?:original(?:es)?|originais|autentic[oa]s?)\b", " ", value)
    # "símil original" es jerga de réplica, no una afirmación de autenticidad.
    value = re.sub(r"\bsimil\s+original(?:es)?\b", " ", value)
    return bool(re.search(
        r"\b(?:100\s*%\s*)?(?:producto\s+|produtos?\s+|articulo\s+)?(?:original(?:es)?|originais|autentic[oa]s?)\b",
        value,
    ))


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


def evaluate_result(item: dict, brand: dict) -> tuple[list[str], str]:
    text = f"{item['title']} {item['description']}"
    if editorial_or_educational(text):
        return [], "contenido educativo, comparativo o informativo"
    if asks_for_authentication(text):
        return [], "consulta de un cliente para verificar autenticidad"
    if buyer_request(text):
        return [], "solicitud de comprador, no oferta de vendedor"
    if legitimate_brand_promotion(text):
        return [], "outlet o promoción comercial legítima"
    if claims_authenticity(text):
        return [], "afirma que el producto es original"
    if not APPAREL_PRODUCT.search(text):
        return [], "fuera de vestimenta y calzado"
    if not contains(text, brand["name"]):
        return [], "no menciona la marca seleccionada"
    if brand["products"] and not any(contains(text, product) for product in brand["products"]):
        return [], "no coincide con los productos configurados"
    if is_official(brand, item["plataforma"], item["seller"], item["url"], text):
        return [], "cuenta o tienda oficial"
    terms = counterfeit_terms(text, item.get("searched_country"))
    if not terms:
        return [], "sin indicios explícitos de falsificación"
    sales = (
        r"\b(?:venta|vendo|vendemos|vende|venda|preco|precio|stock|estoque|envios?|entrega|frete|comprar|compra|"
        r"catalogo|catálogo|disponible|disponivel|pedidos?|whatsapp|tallas?|talles?|tamanhos?|mayorista|minorista|"
        r"atacado|varejo|oferta|ofertas|promo(?:cion|ción)?|inbox|consultas?|encargos?|encomendas?|chama(?:r)?|"
        r"mandame|mándame|escribime|escr[ií]benos|dm)\b|(?:R\$|ARS|MXN|BRL|\$)\s*\d"
    )
    if not re.search(sales, folded(text)):
        return [], "sin intención de venta"
    return terms, "indicios explícitos de falsificación e intención de venta"


def qualifies(item: dict, brand: dict) -> list[str]:
    return evaluate_result(item, brand)[0]
