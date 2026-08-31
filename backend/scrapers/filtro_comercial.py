"""
Filtro de Relevancia Comercial para Net Holmes.

Evalúa si un snippet, descripción o título de publicación contiene indicadores
de que se trata de una oferta comercial real (venta de producto), descartando
ruido como memes, opiniones, reviews y hauls sin intención de venta.

Regla: El texto debe contener al menos 1 indicador de CUALQUIER categoría
para ser considerado una publicación comercial relevante.

Categorías:
  1. Indicadores Financieros / Precio
  2. Llamados a la Acción (CTA Comercial)
  3. Jerga de Réplicas / Infracción
"""

import re
from sqlalchemy.orm import Session
from sqlalchemy import func
from services.cron_logger import cron_logger
from models.brand import Brand
from models.marca_cuenta_oficial import MarcaCuentaOficial


# ─── Diccionarios de Indicadores ──────────────────────────────────────────────

# 1. Indicadores Financieros / Precio
INDICADORES_PRECIO = [
    r'\$\s?\d',             # Símbolo $ seguido de dígito (ej: $15000, $ 2500)
    r'\busd\b',             # USD
    r'\bars\b',             # ARS (pesos argentinos)
    r'\bprecio\b',          # "precio"
    r'\bcotizaci[oó]n\b',   # "cotización"
    r'\bvalor\b',           # "valor"
    r'\bmonto\b',           # "monto"
    r'\bcuotas?\b',         # "cuota" / "cuotas"
    r'\btransferencia\b',   # "transferencia"
    r'\befectivo\b',        # "efectivo"
    r'\bmercadopago\b',     # "mercadopago"
    r'\bmp\b',              # "MP" (abreviatura MercadoPago)
    r'\bpesos\b',           # "pesos"
    r'\bconsultar precio\b',
    r'\ba consultar\b',
]

# 2. Llamados a la Acción (CTA Comercial)
INDICADORES_CTA = [
    r'\bvendo\b',           # "vendo"
    r'\bventa\b',           # "venta"
    r'\bse vende\b',        # "se vende"
    r'\bcompr[aá]\b',       # "compra" / "comprá"
    r'\benv[ií]os?\b',      # "envío" / "envios" / "envio"
    r'\ba todo el pa[ií]s\b',  # "a todo el país"
    r'\bpedidos?\b',        # "pedido" / "pedidos"
    r'\b(?:dm|md)\b',       # "DM" / "MD" (mensaje directo)
    r'\binbox\b',           # "inbox"
    r'\bwhatsapp\b',        # "whatsapp"
    r'\bwsp\b',             # "wsp" (abreviatura whatsapp)
    r'\bwa\.me\b',          # "wa.me" (link whatsapp)
    r'\blink en bio\b',     # "link en bio"
    r'\bstock\b',           # "stock"
    r'\bdisponible\b',      # "disponible"
    r'\bshowroom\b',        # "showroom"
    r'\bmayorista\b',       # "mayorista"
    r'\bcat[aá]logo\b',     # "catálogo"
    r'\bencarg[aá]\b',      # "encargá" / "encarga"
    r'\bpor mayor\b',       # "por mayor"
    r'\bpor menor\b',       # "por menor"
    r'\btal+a?s?\b.*\b\d{2}\b',  # "talle 42", "talles 38 al 44"
    r'\bpregunt[aá]\b',     # "preguntá" / "pregunta" (en contexto de venta)
    r'\bconsult[aá]\b',     # "consultá" / "consulta"
    r'\bsumá\b',            # "sumá" (sumate, comprá)
    r'\boferta\b',          # "oferta"
    r'\bpromo\b',           # "promo"
    r'\bpromoci[oó]n\b',    # "promoción"
    r'\bliquidaci[oó]n\b',  # "liquidación"
    r'\bsale\b',            # "sale" (remate)
]

# 3. Jerga de Réplicas / Infracción
INDICADORES_REPLICA = [
    r'\br[eé]plica\b',      # "réplica" / "replica"
    r'\bg5\b',              # "G5" (calidad de réplica)
    r'\bquality\s*g5\b',    # "quality G5"
    r'\baaa\b',             # "AAA" (calidad de réplica)
    r'\bimportadas?\b',     # "importada" / "importadas"
    r'\bcalidad premium\b', # "calidad premium"
    r'\btop quality\b',     # "top quality"
    r'\b1[:.]1\b',          # "1:1" (réplica exacta)
    r'\bimitaci[oó]n\b',    # "imitación"
    r'\bgenérica\b',        # "genérica"
    r'\binspirada\b',       # "inspirada" (en la marca X)
    r'\balternativa\b',     # "alternativa" (a la original)
    r'\bno original\b',     # "no original"
    r'\bfalsificad[ao]\b',  # "falsificado/a"
    r'\bpirata\b',          # "pirata"
    r'\btrucho\b',          # "trucho" (jerga argentina)
]


def es_publicacion_comercial(texto: str) -> bool:
    """
    Evalúa si un texto (snippet, descripción o título de publicación)
    contiene indicadores de que se trata de una oferta comercial real.
    
    Retorna True si encuentra al menos 1 indicador de CUALQUIER categoría.
    Retorna False si el texto es ruido (meme, opinión, review sin venta).
    
    Args:
        texto: El texto a evaluar (título + descripción + snippet concatenados).
    
    Returns:
        True si es una publicación comercial relevante, False en caso contrario.
    """
    if not texto or not texto.strip():
        return False
    
    texto_lower = texto.lower().strip()
    
    # Buscar en cada categoría
    for pattern in INDICADORES_PRECIO:
        if re.search(pattern, texto_lower):
            return True
    
    for pattern in INDICADORES_CTA:
        if re.search(pattern, texto_lower):
            return True
    
    for pattern in INDICADORES_REPLICA:
        if re.search(pattern, texto_lower):
            return True
    
    return False


def filtrar_item_comercial(item: dict, platform: str = "desconocida") -> bool:
    """
    Wrapper de alto nivel que extrae todos los campos de texto relevantes
    de un item scrapeado y los pasa por el filtro comercial.
    
    Retorna True si el item debe CONSERVARSE (es comercial).
    Retorna False si el item debe DESCARTARSE (es ruido).
    
    También loguea el descarte para la terminal de actividad.
    """
    # Concatenar todos los campos de texto disponibles
    campos_texto = [
        item.get("title", ""),
        item.get("description", ""),
        str(item.get("raw_data", "")),
        item.get("platform_data", {}).get("snippet", "") if isinstance(item.get("platform_data"), dict) else "",
    ]
    
    texto_completo = " ".join(str(c) for c in campos_texto if c)
    
    # ── Check 1: Indicadores comerciales estándar ──
    if es_publicacion_comercial(texto_completo):
        return True
    
    # ── Check 2: Excepción para Links Directos de Producto ──
    # Si la URL ya es una publicación/producto confirmado, aplicar filtro ampliado
    # con términos de indumentaria/calzado (que DuckDuckGo pudo haber truncado)
    url = str(item.get("url", "")).lower()
    es_link_directo = any(pattern in url for pattern in [
        "/p/", "/reel/", "/marketplace/item/", "/video/", "MLA-", "mla-"
    ])
    
    if es_link_directo:
        # Términos de producto indumentaria/calzado/accesorios argentinos
        TERMINOS_PRODUCTO = [
            r'\bzapatillas?\b', r'\bcalzados?\b', r'\bindumentaria\b',
            r'\bremeras?\b', r'\bcamperas?\b', r'\bbuzos?\b',
            r'\bconjuntos?\b', r'\btal+e?s?\b', r'\bjogging\b',
            r'\bpantalon(?:es)?\b', r'\bshorts?\b', r'\bmusculosas?\b',
            r'\bcamisetas?\b', r'\bbermudas?\b', r'\bpiluso\b',
            r'\bgorras?\b', r'\bmochila\b', r'\briñonera\b',
            r'\bbolsos?\b', r'\bmedias\b', r'\bconjuntitos?\b',
            r'\bcalzas?\b', r'\btops?\b', r'\bvestidos?\b',
            r'\bcamisas?\b', r'\bsweaters?\b', r'\bcamperon(?:es)?\b',
            r'\bbotines?\b', r'\bsandalias?\b', r'\bojotas?\b',
            r'\bslippers?\b', r'\bcrocs?\b', r'\bsneakers?\b',
            r'\brunning\b', r'\btraining\b', r'\bfútbol\b',
            r'\btalle\s+(?:s|m|l|xl|xxl|\d{2})\b',
        ]
        texto_lower = texto_completo.lower()
        for pattern in TERMINOS_PRODUCTO:
            if re.search(pattern, texto_lower):
                cron_logger.log(
                    f"✅ [Filtro Comercial] Aceptado por Link Directo + Término de producto ({platform})"
                )
                return True
    
    # Loguear el descarte
    titulo_corto = (item.get("title", "") or "Sin título")[:60]
    url_corta = (item.get("url", "") or "Sin URL")[:80]
    cron_logger.log(
        f"🚫 [Filtro Comercial] Descartado ({platform}): "
        f"No contiene indicadores de venta → {titulo_corto} | {url_corta}"
    )
    return False


def es_cuenta_oficial(db: Session, titular: str, url: str, titulo: str, marca_nombre: str) -> bool:
    """
    Verifica si la cuenta pertenece a la marca oficial.
    Utiliza una búsqueda flexible y la lista de handles oficiales de la base de datos.
    """
    titular_val = str(titular or "").lower().strip()
    url_val = str(url or "").lower().strip()
    titulo_val = str(titulo or "").lower().strip()
    marca_val = str(marca_nombre or "").lower().strip()

    if not titular_val and not url_val and not titulo_val:
        return False

    # Filtro duro básico en título o titular ("tienda oficial")
    if "tienda oficial" in titulo_val or "tienda oficial" in titular_val:
        return True

    # Consultar DB
    marca_obj = db.query(Brand).filter(func.lower(Brand.nombre) == marca_val).first()
    if not marca_obj:
        return False

    oficiales = db.query(MarcaCuentaOficial).filter(MarcaCuentaOficial.marca_id == marca_obj.id).all()
    
    for oficial in oficiales:
        handle = str(oficial.handle_oficial).lower().strip()
        if not handle:
            continue
            
        # Limpiar el handle de @
        handle_clean = handle.replace("@", "")
        
        if handle_clean in titular_val:
            return True
        if url_val and handle_clean in url_val:
            return True

    return False
