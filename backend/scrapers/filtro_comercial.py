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
from urllib.parse import urlparse

from sqlalchemy.orm import Session
from sqlalchemy import func

from services.cron_logger import cron_logger
from models.brand import Brand
from models.marca_cuenta_oficial import MarcaCuentaOficial


# ─── Dominios y patrones de relevancia ────────────────────────────────────────

_DOMINIOS_EDITORIALES = {
    "infobae.com",
    "clarin.com",
    "lanacion.com.ar",
    "pagina12.com.ar",
    "perfil.com",
    "ambito.com",
}

_CATEGORIA_RE = re.compile(
    r"\b(?:zapatillas?|calzados?|indumentaria|ropa|remeras?|camperas?|"
    r"buzos?|conjuntos?|joggings?|pantalones?|shorts?|musculosas?|"
    r"camisetas?|bermudas?|gorras?|mochilas?|riñoneras?|bolsos?|"
    r"medias|calzas?|tops?|vestidos?|camisas?|sweaters?|botines?|"
    r"sandalias?|sneakers?|pilusos?)\b",
    re.IGNORECASE,
)

# REGLAS DE EVALUACIÓN (FALSIFICACIÓN - RECHAZAR / NO ES FAKE)
_ORIGINAL_RE = re.compile(
    r"\b(?:100%\s*original|aut[eé]ntic[oa]s?|tienda\s+oficial|distribuidor\s+autorizado|"
    r"importado\s+oficial|usad[oa]s?|pre-loved|segunda\s+mano|vendo\s+mis\s+zapatillas)\b",
    re.IGNORECASE,
)

# REGLAS DE EVALUACIÓN (FALSIFICACIÓN - ES FAKE)
_FAKE_RE = re.compile(
    r"(?<!no\s)(?<!no\ses\s)\b(?:fake|falsificad[oa]s?|falsificaci[oó]n|truch[oa]s?|"
    r"r[eé]plicas?|imitaci[oó]n|copias?|clones?|clon|aaa|triple\s+a|g5|"
    r"1\s*[:/.]\s*1|1\.1|mirror|espejo|super\s+fake|importadas?|"
    r"calidad\s+(?:de\s+)?r[eé]plica)\b",
    re.IGNORECASE,
)

_EDITORIAL_RE = re.compile(
    r"\b(?:noticias?|reportajes?|entrevistas?|gu[ií]as?|tutoriales?|"
    r"reseñas?|reviews?|comparativas?|blog|opini[oó]n|"
    r"c[oó]mo\s+(?:reconocer|identificar|detectar))\b",
    re.IGNORECASE,
)

_PRECIO_RE = re.compile(
    r"(?:\$\s?\d|\b\d[\d.,]*\s?(?:ars|pesos)\b|\bprecio\b)",
    re.IGNORECASE,
)

_COMPRA_RE = re.compile(
    r"\b(?:vendo|venta|compr[aá]|pedidos?|stock|disponible|"
    r"cat[aá]logo|consult[aá]\s+(?:por\s+)?precio|whatsapp|wsp|"
    r"inbox|env[ií]os?|oferta|mayorista|showroom)\b",
    re.IGNORECASE,
)

_VARIANTE_RE = re.compile(
    r"\b(?:talles?|colores?|variantes?)\b",
    re.IGNORECASE,
)

# NUEVO: Indicadores para detectar y rechazar textos en Inglés o Portugués
_IDIOMA_EXTRANJERO_RE = re.compile(
    r"\b(?:shipping|frete|tamanho|the|and|with|for|shoes|cartão|promoção|preço)\b",
    re.IGNORECASE,
)

# NUEVO: Indicadores base para confirmar que el texto está en Español
_IDIOMA_ESPANOL_RE = re.compile(
    r"\b(?:el|la|los|las|de|que|en|y|talle|env[ií]o|precio|pesos|cuotas|tarjeta)\b",
    re.IGNORECASE,
)

_MARCAS_CONOCIDAS = (
    "Nike", "Adidas", "Puma", "Reebok", "New Balance",
    "Converse", "Vans", "Jordan", "Under Armour",
)

_UBICACIONES_AR = {
    "buenos aires", "caba", "capital federal", "la plata",
    "córdoba", "cordoba", "rosario", "santa fe", "mendoza",
    "tucumán", "tucuman", "salta", "neuquén", "neuquen",
    "mar del plata", "san juan", "misiones", "entre ríos",
    "entre rios", "chaco", "corrientes", "jujuy", "formosa",
    "río negro", "rio negro", "chubut", "santa cruz",
    "tierra del fuego", "la pampa", "san luis", "catamarca",
    "santiago del estero",
}

# ACTUALIZADO: Paises homónimos y en inglés agregados para descartar falsos positivos
_PAISES_NO_AR = (
    "paraguay", "república dominicana", "republica dominicana",
    "dominican republic", "uruguay", "chile", "brasil", "brazil",
    "bolivia", "perú", "peru", "ecuador", "colombia",
    "méxico", "mexico", "españa", "spain", "usa", "eeuu", "ee.uu.", 
    "united states", "puerto rico", "nuevo méxico", "new mexico", 
    "bogotá", "bogota"
)


def _valor_texto(valor) -> str:
    return valor if isinstance(valor, str) else ""


def _contiene_marca(texto: str, marca: str) -> bool:
    texto = re.sub(r"#\w+", " ", texto.lower())
    marca = marca.strip().lower()
    return bool(marca and re.search(rf"(?<!\w){re.escape(marca)}(?!\w)", texto))


def _obtener_dominio(url: str) -> str:
    try:
        host = urlparse(url or "").hostname or ""
        return host.lower().rstrip(".").removeprefix("www.")
    except (ValueError, AttributeError):
        return ""


def _evaluar_ubicacion_ar(item: dict) -> tuple[str, str]:
    """
    Usa exclusivamente campos de ubicación de la fuente para evitar falsos positivos de títulos.
    """
    datos = item.get("platform_data")
    datos = datos if isinstance(datos, dict) else {}

    campos = ("country", "country_code", "location", "seller_location", "seller_country", "city", "province", "region")
    valores = [_valor_texto(origen.get(campo)) for origen in (item, datos) for campo in campos]
    ubicacion = " ".join(v for v in valores if v).strip().lower()

    codigos = [_valor_texto(origen.get("country_code")).strip().lower() for origen in (item, datos)]

    # Un país explícitamente extranjero o región homónima tiene prioridad
    if any(re.search(rf"\b{re.escape(pais)}\b", ubicacion) for pais in _PAISES_NO_AR):
        return "DESCARTADO_PAIS", ubicacion

    if not ubicacion:
        return "UBICACION_DESCONOCIDA", ""

    if any(codigo in ("ar", "arg") for codigo in codigos):
        return "AR", ubicacion

    if re.search(r"\bargentina\b", ubicacion):
        return "AR", ubicacion

    if any(re.search(rf"\b{re.escape(ciudad)}\b", ubicacion) for ciudad in _UBICACIONES_AR):
        return "AR", ubicacion

    return "DESCARTADO_PAIS", ubicacion


def evaluar_relevancia(item: dict, marca_buscada: str, platform: str = "desconocida") -> dict:
    """Clasifica ofertas sospechosas; no confirma falsificación definitiva."""

    titulo = _valor_texto(item.get("title")).strip()
    descripcion = _valor_texto(item.get("description"))
    datos = item.get("platform_data")
    datos = datos if isinstance(datos, dict) else {}
    snippet = _valor_texto(datos.get("snippet"))
    
    texto = " ".join((titulo, descripcion, snippet))
    url = _valor_texto(item.get("url"))
    dominio = _obtener_dominio(url)

    resultado = {
        "estado": "",
        "marca_buscada": marca_buscada,
        "marca_identificada": "",
        "pais": "",
        "evidencia_geografica": "",
        "evidencia_comercial": [],
        "senales_fake": [],
        "url": url,
        "plataforma": platform,
    }

    def descartar(estado: str, motivo: str) -> dict:
        resultado["estado"] = estado
        cron_logger.log(f"[RelevanceFilter] {estado} | motivo={motivo} | marca={marca_buscada or 'no_informada'} | url={url}")
        return resultado

    # 1. Marca obligatoria.
    if not marca_buscada:
        return descartar("DESCARTADO_MARCA", "MARCA_BUSCADA_NO_INFORMADA")

    # 2. Excluir medios editoriales conocidos.
    if any(dominio == d or dominio.endswith("." + d) for d in _DOMINIOS_EDITORIALES):
        return descartar("DESCARTADO_NO_COMERCIAL", "MEDIO_PERIODISTICO")

    if not titulo or not _CATEGORIA_RE.search(titulo):
        return descartar("DESCARTADO_NO_COMERCIAL", "PRODUCTO_NO_IDENTIFICABLE")

    if not _contiene_marca(titulo, marca_buscada):
        return descartar("DESCARTADO_MARCA", "MARCA_NO_IDENTIFICADA_EN_TITULO")

    otras_marcas = [m for m in _MARCAS_CONOCIDAS if m.lower() != marca_buscada.lower() and _contiene_marca(titulo, m)]
    if otras_marcas:
        resultado["marca_identificada"] = otras_marcas[0]
        return descartar("DESCARTADO_MARCA", f"MARCA_ADICIONAL_AMBIGUA:{otras_marcas[0]}")

    resultado["marca_identificada"] = marca_buscada

    # 3. Validar Idioma (Rechazar si está en árabe, ruso u otros idiomas no latinos, o inglés/portugués)
    if re.search(r'[\u0600-\u06FF\u0400-\u04FF\u4E00-\u9FFF]', texto):
        return descartar("DESCARTADO_IDIOMA", "TEXTO_EN_ARABE_RUSO_U_OTRO_IDIOMA")

    matches_extranjero = len(_IDIOMA_EXTRANJERO_RE.findall(texto))
    matches_espanol = len(_IDIOMA_ESPANOL_RE.findall(texto))
    
    # Si detecta más palabras en inglés/portugués que en español, lo rechaza.
    if matches_extranjero > 0 and matches_extranjero > matches_espanol:
        return descartar("DESCARTADO_IDIOMA", "TEXTO_NO_ESPANOL_O_EXTRANJERO")

    # 4. Detectar si declara ser un producto explícitamente original, usado o de segunda mano
    if _ORIGINAL_RE.search(texto) and not _FAKE_RE.search(texto):
        return descartar("DESCARTADO_ORIGINAL", "DECLARA_SER_ORIGINAL_O_USADO")

    # 5. Buscar señales explícitas de falsificación (AHORA INCLUYE HASHTAGS)
    resultado["senales_fake"] = sorted({
        coincidencia.group(0).lower()
        for coincidencia in _FAKE_RE.finditer(texto)
    })

    if not resultado["senales_fake"]:
        return descartar("DESCARTADO_SIN_SENALES_FAKE", "SIN_EVIDENCIA_DE_FALSIFICACION")

    # 6. Buscar evidencia comercial.
    evidencias = []
    if _PRECIO_RE.search(texto): evidencias.append("precio")
    if _COMPRA_RE.search(texto): evidencias.append("compra_o_disponibilidad")
    if _VARIANTE_RE.search(texto): evidencias.append("talles_o_variantes")

    campos_vendedor = ("seller", "seller_name", "seller_id", "vendor")
    tiene_vendedor = any(item.get(c) or datos.get(c) for c in campos_vendedor)
    if tiene_vendedor: evidencias.append("vendedor")

    campos_disponibilidad = ("availability", "stock", "sizes", "variants")
    if any(item.get(c) or datos.get(c) for c in campos_disponibilidad): evidencias.append("disponibilidad_o_variantes")

    tiene_imagen = any(item.get(c) or datos.get(c) for c in ("image", "image_url", "images", "image_urls"))
    if tiene_imagen and tiene_vendedor: evidencias.append("imagen_y_vendedor")

    resultado["evidencia_comercial"] = evidencias

    if not evidencias:
        return descartar("DESCARTADO_NO_COMERCIAL", "NO_ES_OFERTA_COMERCIAL")

    # 7. Validar ubicación argentina
    estado_geo, evidencia_geo = _evaluar_ubicacion_ar(item)
    resultado["evidencia_geografica"] = evidencia_geo

    if estado_geo != "AR":
        resultado["pais"] = "desconocido" if not evidencia_geo else evidencia_geo
        return descartar(estado_geo, "UBICACION_NO_VERIFICADA_EN_ARGENTINA")

    resultado["pais"] = "Argentina"
    resultado["estado"] = "ACEPTADO_SOSPECHOSO"

    cron_logger.log(
        f"[RelevanceFilter] ACEPTADO_SOSPECHOSO "
        f"| marca={marca_buscada} | pais=Argentina "
        f"| oferta={','.join(evidencias)} "
        f"| fake={','.join(resultado['senales_fake'])} "
        f"| url={url} | plataforma={platform}"
    )

    return resultado


def es_publicacion_comercial(texto: str) -> bool:
    if not texto or not _CATEGORIA_RE.search(texto):
        return False
    return bool(_PRECIO_RE.search(texto) or _COMPRA_RE.search(texto) or _VARIANTE_RE.search(texto))


def filtrar_item_comercial(item: dict, platform: str = "desconocida", marca_buscada: str = None) -> bool:
    marca = marca_buscada or _valor_texto(item.get("marca_buscada"))
    if not marca:
        cron_logger.log("[RelevanceFilter] DESCARTADO | motivo=MARCA_BUSCADA_NO_INFORMADA")
        return False
    resultado = evaluar_relevancia(item, marca, platform)
    return resultado["estado"] == "ACEPTADO_SOSPECHOSO"


def es_cuenta_oficial(db: Session, titular: str, url: str, titulo: str, marca_nombre: str) -> bool:
    titular_val = str(titular or "").lower().strip()
    url_val = str(url or "").lower().strip()
    titulo_val = str(titulo or "").lower().strip()
    marca_val = str(marca_nombre or "").lower().strip()

    if not titular_val and not url_val and not titulo_val:
        return False

    if "tienda oficial" in titulo_val or "tienda oficial" in titular_val:
        return True

    marca_obj = db.query(Brand).filter(func.lower(Brand.nombre) == marca_val).first()
    if not marca_obj:
        return False

    oficiales = db.query(MarcaCuentaOficial).filter(MarcaCuentaOficial.marca_id == marca_obj.id).all()
    
    for oficial in oficiales:
        handle = str(oficial.handle_oficial).lower().strip()
        if not handle: continue
        handle_clean = handle.replace("@", "")
        if handle_clean in titular_val or (url_val and handle_clean in url_val):
            return True

    return False


def evaluar_publicacion_osint(
    plataforma: str = "",
    descripcion: str = "",
    comentarios: str | list = "",
    ubicacion: str = "",
    precio: str | float = ""
) -> dict:
    """
    Evalúa una publicación con las reglas estrictas de Brand Protection y OSINT.
    Retorna:
    {
      "es_falsificacion": bool,
      "es_argentina": bool,
      "motivo": str
    }
    """
    from services.llm_client import _evaluate_publication_heuristics
    if isinstance(comentarios, (list, tuple)):
        comentarios_str = " | ".join(str(c) for c in comentarios if c)
    else:
        comentarios_str = str(comentarios or "")

    return _evaluate_publication_heuristics(
        plataforma=plataforma,
        descripcion=descripcion,
        comentarios=comentarios_str,
        ubicacion=ubicacion,
        precio=str(precio or "")
    )