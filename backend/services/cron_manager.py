import asyncio
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import re
import json
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from database import SessionLocal
from models.brand import Brand
from services.cron_logger import cron_logger
from services.keyword_generator import generate_keywords
from scrapers.scraper_engine import ScraperEngine
from models.reporte import ReporteBrandDefense
from models.facebook_data import ReporteFacebookData
from models.instagram_data import ReporteInstagramData
from models.tiktok_data import ReporteTiktokData
from models.mercadolibre_data import ReporteMercadoLibreData
from services.correlation_engine import CorrelationEngine
from scrapers.filtro_comercial import es_cuenta_oficial
from services.argentina_scope import (
    detect_foreign_content,
    has_non_argentina_content,
    is_explicitly_foreign_location,
    is_spanish_text,
)

# Instancia del scheduler con zona horaria de Argentina
scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")

# Bandera global para detención de emergencia inmediata
_stop_requested = False

def request_stop():
    """Señal inmediata para abortar cualquier escaneo en ejecución."""
    global _stop_requested
    _stop_requested = True
    cron_logger.log("🛑 [Detención de Emergencia] Señal recibida. Abortando escaneo inmediatamente...")

def get_whatsapp_number(text: str) -> str:
    """Extrae el primer número de WhatsApp o teléfono que encuentre usando regex."""
    if not text:
        return None
    # Regex básica para números de teléfono (Argentina u otros formatos comunes)
    match = re.search(r'(?:(?:00)?549?)?0?(11|[2368]\d)\d{8}', text.replace(" ", "").replace("-", ""))
    if match:
        return match.group(0)
    return None

def detect_counterfeit_indicators(text: str) -> dict:
    """
    Detecta indicadores de falsificación basado en palabras clave.
    Retorna: {
        'es_falsificacion': bool,
        'terminos_encontrados': list,
        'motivo': str
    }
    """
    if not text:
        return {'es_falsificacion': False, 'terminos_encontrados': [], 'motivo': 'Texto vacío'}
    
    text_lower = text.lower()

    counterfeit_high_confidence_terms = [
        r'\bcalidad\s*premium\b',
        r'\btailand[eé]s[a-z]*\b',
        r'\bimportad[oa]s?\s+premium\b',
    ]
    high_confidence_matches = [
        match.group(0)
        for term in counterfeit_high_confidence_terms
        for match in re.finditer(term, text_lower)
    ]
    if high_confidence_matches:
        terms = list(dict.fromkeys(high_confidence_matches))
        return {
            'es_falsificacion': True,
            'terminos_encontrados': terms,
            'motivo': f"Indicadores explícitos de falsificación: {', '.join(terms)}"
        }
    
    # Las declaraciones positivas de autenticidad prevalecen sobre menciones ambiguas.
    terminos_original = [
        r'\b100%\s*original\b',
        r'\boriginal(?:es)?\b',
        r'\baut[eé]ntic[oa]s?\b',
        r'\bperfecto\s*estado\b',
        r'\busado\b',
        r'\btienda\s*oficial\b',
        r'\boulet\s*oficial\b',
        r'\bstore\s*oficial\b',
        r'\bautenticidad\b',
        r'\bgarantía\s*oficial\b',
    ]
    
    # Términos que indican falsificación
    terminos_falsificacion = [
        r'\br[eé]plicas?\b',
        r'\brepliquero\b',
        r'\bg5\b',
        r'\bclones?\b',
        r'\baaa\b',
        r'\btailand[eé]s[a-z]*\b',
        r'\bimitaci[oó]n(?:es)?\b',
        r'\bcopias?\b',
        r'\bfalsificad[oa]s?\b',
        r'\bfalsificaci[oó]n\b',
        r'\bfals[oa]s?\b',
        r'\bpirata\b',
        r'\btruch[oa]s?\b',
        r'\bcalidad\s*premium\b',
        r'\btailand[eé]s[a-z]*\b',
        r'\bimportad[oa]s?\s+premium\b',
        r'\bno\s+(?:es\s+)?original(?:es)?\b',
        r'\b1\s*[:/.]\s*1\b',
    ]
    negaciones_falsificacion = [
        match.span()
        for match in re.finditer(
            r'\bno\s+(?:es\s+)?(?:un[oa]?\s+)?'
            r'(?:fake|falsificad[oa]s?|truch[oa]s?|r[eé]plicas?|'
            r'imitaci[oó]n(?:es)?|copias?|clones?|clon)\b',
            text_lower,
        )
    ]
    
    es_original = any(re.search(term, text_lower) for term in terminos_original)
    niega_originalidad = bool(re.search(r'\bno\s+(?:es\s+)?original(?:es)?\b', text_lower))
    if es_original and not niega_originalidad:
        return {
            'es_falsificacion': False,
            'terminos_encontrados': [],
            'motivo': 'Declara autenticidad, originalidad o condición usada'
        }
    
    # Detectar términos de falsificación
    terminos_detectados = []
    for term in terminos_falsificacion:
        matches = re.finditer(term, text_lower)
        terminos_detectados.extend(
            match.group(0)
            for match in matches
            if not any(start <= match.start() < end for start, end in negaciones_falsificacion)
        )
    
    if terminos_detectados:
        terminos_unicos = list(set(terminos_detectados))[:5]  # Máximo 5 términos para el log
        return {
            'es_falsificacion': True,
            'terminos_encontrados': terminos_unicos,
            'motivo': f"Encontrados términos de falsificación: {', '.join(terminos_unicos)}"
        }
    
    return {
        'es_falsificacion': False,
        'terminos_encontrados': [],
        'motivo': 'No hay indicadores claros de falsificación'
    }

def _normalize_url_for_dedup(url: str, plataforma: str = "") -> str:
    """
    Normalización robusta de URLs para deduplicación.
    Maneja: http/https, www/m subdominios, query params, trailing slashes,
    y extracción de IDs canónicos por plataforma.
    """
    import re as _re
    from urllib.parse import urlparse, urlunparse
    
    url = url.strip()
    
    # 1. Normalizar protocolo → https
    if url.startswith("http://"):
        url = "https://" + url[7:]
    elif not url.startswith("https://"):
        url = "https://" + url
    
    # 2. Quitar query params y fragments
    parsed = urlparse(url)
    clean_path = parsed.path
    
    # 3. Normalizar subdominios (www., m., l.) → sin prefijo
    host = parsed.netloc.lower()
    for prefix in ["www.", "m.", "l.", "lm."]:
        if host.startswith(prefix):
            host = host[len(prefix):]
    
    # 4. Quitar trailing slashes del path
    clean_path = clean_path.rstrip("/")
    
    # 5. Extracciones canónicas por plataforma
    plat = plataforma.lower() if plataforma else ""
    
    if plat == "mercadolibre" or "mercadolibre" in host:
        # Extraer solo código MLA: "MLA-123456789" del path
        mla_match = _re.search(r'(MLA-\d+)', clean_path, _re.IGNORECASE)
        if mla_match:
            return f"https://mercadolibre.com.ar/{mla_match.group(1).upper()}"
        host = "mercadolibre.com.ar"
        
    elif plat == "instagram" or "instagram" in host:
        # Extraer shortcode: /p/ABC123/ o /reel/ABC123/
        sc_match = _re.search(r'/(p|reel)/([A-Za-z0-9_-]+)', clean_path)
        if sc_match:
            return f"https://instagram.com/{sc_match.group(1)}/{sc_match.group(2)}"
        host = "instagram.com"
        
    elif plat == "tiktok" or "tiktok" in host:
        # Extraer @user y video ID: /@user/video/1234567890
        user_vid_match = _re.search(r'/@([^/]+)/video/(\d+)', clean_path)
        if user_vid_match:
            return f"https://tiktok.com/@{user_vid_match.group(1)}/video/{user_vid_match.group(2)}"
        vid_match = _re.search(r'/video/(\d+)', clean_path)
        if vid_match:
            return f"https://tiktok.com/@_/video/{vid_match.group(1)}"
        host = "tiktok.com"
        
    elif plat == "facebook" or "facebook" in host:
        # Extraer marketplace item ID o post ID
        item_match = _re.search(r'/marketplace/item/(\d+)', clean_path)
        if item_match:
            return f"https://facebook.com/marketplace/item/{item_match.group(1)}"
        post_match = _re.search(r'/posts/(\d+)', clean_path)
        if post_match:
            return f"https://facebook.com/posts/{post_match.group(1)}"
        host = "facebook.com"
    
    return f"https://{host}{clean_path}"

def _extract_single_clean_image_url(item: Dict[str, Any]) -> str | None:
    """
    Extrae exactamente UNA sola imagen válida de la publicación/producto.
    Descarta videos (.mp4, .mov, etc.) para ahorrar almacenamiento y tokens.
    Devuelve un JSON array con 1 URL o None: '["https://..."]'.
    """
    candidates = []
    
    # 1. Buscar en imagen_urls o image_urls
    raw = item.get("imagen_urls") or item.get("image_urls")
    if raw:
        if isinstance(raw, list):
            candidates.extend(raw)
        elif isinstance(raw, str):
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        candidates.extend(parsed)
                except Exception:
                    pass
            else:
                candidates.append(raw)
                
    # 2. Buscar en platform_data
    pd = item.get("platform_data", {})
    if isinstance(pd, dict):
        p_img = pd.get("image_urls") or pd.get("imageUrl") or pd.get("thumbnail") or pd.get("cover")
        if p_img:
            if isinstance(p_img, list):
                candidates.extend(p_img)
            elif isinstance(p_img, str):
                if p_img.startswith("["):
                    try:
                        parsed = json.loads(p_img)
                        if isinstance(parsed, list):
                            candidates.extend(parsed)
                    except Exception:
                        pass
                else:
                    candidates.append(p_img)

    # 3. Filtrar extensiones de video y URLs vacías/inválidas
    video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m3u8', '.ts')
    clean_images = []
    for c in candidates:
        if not c or not isinstance(c, str):
            continue
        c_clean = c.strip().strip('"').strip("'")
        if not c_clean.startswith("http"):
            continue
        lower_c = c_clean.lower()
        if any(lower_c.endswith(ext) or f"{ext}?" in lower_c for ext in video_extensions):
            continue
        if "video" in lower_c and not any(img_ext in lower_c for img_ext in ('.jpg', '.jpeg', '.png', '.webp')):
            continue
        clean_images.append(c_clean)
        
    if clean_images:
        # Tomar ESTRICTAMENTE 1 sola imagen
        return json.dumps([clean_images[0]])
    return None

def process_and_save_single_result(
    db: Session, item: Dict[str, Any], brand: Brand, keyword: str = ""
) -> bool:
    """Procesa, mapea a ScanResult y guarda un único resultado en la base de datos de inmediato."""

    platform_name = str(item.get("plataforma") or "").lower()
    social_platforms = {"facebook", "instagram", "tiktok"}
    title_text = str(item.get("title") or "")
    description_text = str(item.get("description") or "")
    platform_data = item.get("platform_data")
    platform_data = platform_data if isinstance(platform_data, dict) else {}
    result_location = item.get("location")

    description_parts = [
        description_text,
        str(platform_data.get("description_full") or ""),
        str(platform_data.get("caption_full") or ""),
    ]
    comments = [
        item.get("comments_audit"),
        item.get("comments"),
        platform_data.get("comments_text"),
        platform_data.get("comments"),
    ]
    for comment_group in comments:
        if isinstance(comment_group, str):
            description_parts.append(comment_group)
        elif isinstance(comment_group, (list, tuple)):
            description_parts.extend(
                str(comment) for comment in comment_group if isinstance(comment, str)
            )
    condition = str(platform_data.get("item_condition") or item.get("condition") or "")
    social_analysis_text = " ".join(
        part for part in [title_text, *description_parts, condition] if part
    )

    if platform_name in social_platforms and has_non_argentina_content(
        f"{title_text} {description_text}"
    ):
        cron_logger.log(
            f"🚫 [Filtro Argentina] País vecino o moneda extranjera en la publicación: "
            f"{title_text[:60]}"
        )
        return False

    if is_explicitly_foreign_location(result_location):
        cron_logger.log(
            f"🚫 [Filtro Ubicación] Resultado extranjero descartado: "
            f"{result_location} - {item.get('title', '')}"
        )
        return False

    social_text = (
        social_analysis_text
        if platform_name == "instagram"
        else f"{title_text} {description_text}"
    )
    deteccion_social = None
    if platform_name in social_platforms:
        if not is_spanish_text(social_text):
            cron_logger.log(
                f"🚫 [Filtro idioma] Publicación social no identificada como español: "
                f"{title_text[:60]}"
            )
            return False
        deteccion_social = detect_counterfeit_indicators(social_analysis_text)
        if not deteccion_social["es_falsificacion"]:
            cron_logger.log(
                f"🚫 [Filtro falsificación] Sin indicadores explícitos en título/descripción: "
                f"{title_text[:60]}"
            )
            return False
        if not re.search(rf"(?<!\w){re.escape(brand.nombre)}(?!\w)", social_text, re.IGNORECASE):
            cron_logger.log(
                f"🚫 [Filtro marca] La publicación no menciona la marca seleccionada "
                f"'{brand.nombre}' en título/descripción."
            )
            return False
    
    # Filtro de contenido extranjero (por moneda, idioma, términos locales)
    title = title_text.lower()
    desc = description_text.lower()
    seller_profile = item.get("seller_profile")
    seller_profile = seller_profile if isinstance(seller_profile, dict) else {}
    seller_name = str(seller_profile.get("name") or "").lower()
    raw_data_str = str(item.get("raw_data", "")).lower()
    combined_text = f"{title} {desc} {seller_name} {raw_data_str}"
    foreign_check_text = (
        f"{social_text} {result_location or ''}"
        if platform_name in social_platforms
        else combined_text
    )
    
    if detect_foreign_content(foreign_check_text):
        cron_logger.log(
            f"🚫 [Filtro País] Contenido extranjero detectado (moneda/idioma/términos locales): {title[:60]}"
        )
        return False
    
    # 1. Filtro Anti-Oficial / Filtro de País / Filtro de Marca
    title = title_text.lower()
    desc = description_text.lower()
    seller_name = str(seller_profile.get("name") or "").lower()
    raw_data_str = str(item.get("raw_data", "")).lower()
    
    combined_text = f"{title} {desc} {seller_name} {raw_data_str}"
    
    # a. Bloquear Tiendas Oficiales mediante Lista Negra Dinámica (DB) y Filtro Básico
    titular = str(
        seller_profile.get("name")
        or platform_data.get("seller_name")
        or platform_data.get("username")
        or "Vendedor No Identificado"
    )
    if titular.strip().casefold() in {
        "", "desconocido", "usuario desconocido", "vendedor no identificado",
    }:
        titular = str(
            platform_data.get("seller_name")
            or platform_data.get("username")
            or "Vendedor No Identificado"
        )
    if not seller_profile.get("name") or str(seller_profile.get("name")).casefold() in {
        "desconocido", "usuario desconocido", "vendedor no identificado",
    }:
        item["seller_profile"] = {**seller_profile, "name": titular}
    url = item.get("url", "")
    titulo = item.get("title", "")
    
    if es_cuenta_oficial(db, titular, url, titulo, brand.nombre):
        cron_logger.log(f"🚫 [Filtro Oficial DB] Descartado por ser cuenta oficial registrada de {brand.nombre}: {titular} ({url})")
        return False

    # Filtro duro extra (respaldo genérico)
    clean_seller = seller_name.replace("@", "").strip().lower()
    brand_lower = brand.nombre.lower()
    official_brand_handles = [
        brand_lower,
        f"{brand_lower}ar",
        f"{brand_lower}argentina",
        f"{brand_lower}oficial",
        f"{brand_lower}official",
        f"{brand_lower}football",
        f"{brand_lower}sport",
        f"{brand_lower}store",
        "commerce"
    ]
    if clean_seller in official_brand_handles:
        cron_logger.log(f"🚫 [Filtro Oficial DB] Descartado por parecer perfil genérico oficial ({clean_seller}): {titulo}")
        return False

    # b. Bloquear ubicaciones extranjeras mencionadas en el contenido.
    # Usa word boundaries (\b) para evitar falsos positivos como "usa" dentro de "usado"
    foreign_patterns = [
        r'\bbrasil\b', r'\bbrazil\b', r'\beeuu\b', r'\bestados unidos\b', r'\bunited states\b',
        r'\bmiami\b', r'\borlando\b', r'\bflorida\b', r'\bcalifornia\b', r'\btexas\b', r'\bnew york\b', r'\blos angeles\b',
        r'\bchile\b', r'\buruguay\b', r'\bmexico\b', r'\bespaña\b', r'\bcolombia\b',
        r'\bperu\b', r'\becuador\b', r'\bvenezuela\b', r'\bparaguay\b', r'\bbolivia\b',
        r'\bguatemala\b', r'\bcosta rica\b', r'\bpanama\b', r'\bhonduras\b', r'\bel salvador\b',
        r'\bnicaragua\b', r'\brepublica dominicana\b', r'\bpuerto rico\b',r'\bparaguay\b',
        r'\bmadrid\b', r'\bbarcelona\b', r'\bbogota\b', r'\blima\b', 
        r'\bsantiago de chile\b', r'\bmontevideo\b', r'\basuncion\b',
        r'\busa\b',  # Con word boundary para no matchear "usado", "causa", etc.
        r'\bgs\b', r'\bgs\.\b', r'\bpyg\b', r'\bguaranies\b', r'\bguaraníes\b', 
        r'\bsoles\b', r'\bpesos uruguayos\b', r'\bpesos chilenos\b', r'\bbolivianos\b'
    ]
    # Ciudades argentinas que funcionan como bypass (si aparecen, el item es argentino)
    ar_city_terms = [
        "argentina", "buenos aires", "córdoba", "cordoba", "rosario", "mendoza",
        "tucumán", "tucuman", "salta", "santa fe", "mar del plata", "la plata",
        "neuquén", "neuquen", "bahía blanca", "bahia blanca", "corrientes", 
        "resistencia", "posadas", "paraná", "parana", "san juan", "san luis",
        "jujuy", "formosa", "catamarca", "la rioja", "rio negro", "chubut",
        "caba", "capital federal", "gba", "zona sur", "zona norte", "zona oeste"
    ]
    has_foreign = any(re.search(pat, combined_text) for pat in foreign_patterns)
    if has_foreign:
        cron_logger.log(f"🚫 [Filtro País Estricto] Descartado por país/moneda extranjera detectada: {item.get('title')[:50]}")
        return False

    # c. Limpieza de "Basura" (Debe mencionar la marca o la palabra clave)
    brand_name = brand.nombre.lower()
    kw_lower = keyword.lower() if keyword else ""
    if brand_name not in combined_text and (not kw_lower or kw_lower not in combined_text):
        cron_logger.log(f"🚫 [Filtro] Descartado por no tener relación con '{brand.nombre}': {item.get('title')}")
        return False

    from services.product_relevance import matches_configured_product
    product_text = " ".join((title, desc, raw_data_str))
    if not matches_configured_product(product_text, brand.nombre, brand.products):
        cron_logger.log(
            f"[Filtro Producto] Resultado descartado por no coincidir con productos configurados de {brand.nombre}: "
            f"{item.get('title', '')}"
        )
        return False

    # d. Filtro de URLs — Validación PERMISIVA (solo rechazar URLs claramente genéricas)
    item_url_raw = item.get("url", "N/A").lower()
    plataforma = str(item.get("plataforma", "")).lower()
    if item_url_raw != "n/a":
        # Rechazar URLs genéricas comunes en todas las plataformas
        generic_reject = ["/discover/", "/search?", "/explore/", "/tag/", "/hashtag/", "/login", "/signup"]
        if any(p in item_url_raw for p in generic_reject):
            cron_logger.log(f"🚫 [Filtro URL] Descartado por URL genérica ({plataforma}): {item_url_raw}")
            return False

        # Validación permisiva por plataforma — solo rechazar lo que NO es contenido
        if plataforma == "instagram":
            # Aceptar /p/, /reel/, /stories/, perfiles (/username), etc.
            # Solo rechazar la raíz desnuda (instagram.com/) sin path útil
            if re.search(r'instagram\.com/?$', item_url_raw):
                cron_logger.log(f"🚫 [Filtro URL] Instagram descartado — URL raíz sin contenido: {item_url_raw}")
                return False
        elif plataforma == "tiktok":
            # Aceptar /@user/video/, vt.tiktok.com short links, perfiles
            if re.search(r'tiktok\.com/?$', item_url_raw):
                cron_logger.log(f"🚫 [Filtro URL] TikTok descartado — URL raíz sin contenido: {item_url_raw}")
                return False
        elif plataforma == "facebook":
            # Aceptar marketplace/, posts/, photo/, reel/, groups/, shop/, perfiles
            if re.search(r'facebook\.com/?$', item_url_raw):
                cron_logger.log(f"🚫 [Filtro URL] Facebook descartado — URL raíz sin contenido: {item_url_raw}")
                return False
        elif plataforma == "mercadolibre":
            # Aceptar articulo.mercadolibre, /p/MLA (catálogo), listado.mercadolibre
            if not re.search(r'mercadolibre\.com\.ar/', item_url_raw):
                cron_logger.log(f"🚫 [Filtro URL] MercadoLibre descartado — no es dominio MLA: {item_url_raw}")
                return False
        elif plataforma in ("web", "tienda_falsa"):
            # Aceptar cualquier dominio no oficial para análisis de phishing/tiendas falsas
            pass

    # Inspección profunda de comentarios para extraer WhatsApp/Phone
    found_phone = get_whatsapp_number(item.get("description", ""))
    if not found_phone:
        for comment in item.get("comments_audit", []):
            found_phone = get_whatsapp_number(comment)
            if found_phone:
                break
                
    if not found_phone:
        found_phone = get_whatsapp_number(str(item.get("seller_profile", {}).get("phone", "")))
    if not found_phone:
        found_phone = get_whatsapp_number(str(item.get("platform_data", {}).get("phone", "")))
    
    try:
        # Guardar en DB deduplicando por URL normalizada robustamente
        item_url = item.get("url", "N/A")
        if item_url != "N/A":
            from services.image_persistence import limpiar_url_canonica, persistir_imagen_local
            clean_url = limpiar_url_canonica(item_url)
            clean_dedup = _normalize_url_for_dedup(clean_url, plataforma)
            
            # Mapear URL limpia de vuelta al item para que se guarde limpia
            item["url"] = clean_url
            
            existing = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.url_evidencia == clean_dedup).first()
            if not existing:
                existing = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.url_evidencia == clean_url).first()
            if existing:
                cron_logger.log(f"🔄 [Duplicado] Item ya existe en base de datos: {clean_url}")
                return False
            
        from services.nlp_heuristics import extract_correlations
        correlaciones = extract_correlations(item)
        
        # Extraer imagen candidata directa
        candidate_img = _extract_single_clean_image_url(item)

        parsed_price = None
        raw_p = item.get("price")
        if raw_p is not None:
            try:
                clean_p = re.sub(r'[^0-9.]', '', str(raw_p).replace(',', '.'))
                if clean_p:
                    parsed_price = float(clean_p)
            except Exception:
                parsed_price = None

        parsed_followers = None
        raw_f = item.get("seguidores_infractor") or item.get("seller_profile", {}).get("followers") or item.get("platform_data", {}).get("followers")
        if raw_f is not None:
            try:
                clean_f = re.sub(r'[^0-9]', '', str(raw_f))
                if clean_f:
                    parsed_followers = int(clean_f)
            except Exception:
                parsed_followers = None

        # Detectar indicadores de falsificación
        condicion = str(platform_data.get("item_condition") or item.get("condition") or "")

        # El término de búsqueda nunca forma parte del texto evaluado como evidencia.
        texto_analisis = (
            social_analysis_text
            if platform_name in social_platforms
            else f"{title_text} {description_text} {condicion}"
        )
        
        if platform_name in social_platforms:
            deteccion = deteccion_social or detect_counterfeit_indicators(texto_analisis)
        else:
            deteccion = detect_counterfeit_indicators(texto_analisis)
        es_falsificacion = deteccion['es_falsificacion']
        motivo_falsificacion = deteccion['motivo']
        
        if es_falsificacion:
            cron_logger.log(f"🚩 [Falsificación Detectada] {brand.nombre}: {motivo_falsificacion}")
        else:
            cron_logger.log(f"❌ [Rechazado] {motivo_falsificacion}")
            return False  # Rechazar originales/sin indicadores.

        new_result = ReporteBrandDefense(
            pais=item.get("location", "Argentina"),
            producto_catalogo=keyword if keyword else "Desconocido",
            marca_afectada=brand.nombre,
            plataforma=item.get("plataforma") or "web",
            titular_cuenta=titular,
            url_evidencia=item.get("url"),
            descripcion_post=f"[FALSIFICACIÓN: {'SÍ' if es_falsificacion else 'NO'}] {motivo_falsificacion}\n\n{item.get('description') or item.get('title', '')}",
            precio_publico=parsed_price,
            direccion_publica=item.get("location", ""),
            telefono_publico=found_phone or item.get("phone") or item.get("platform_data", {}).get("phone"),
            seguidores_infractor=parsed_followers,
            estado="Investigando" if es_falsificacion else "Pendiente"
        )
        db.add(new_result)
        db.flush() # Obtain ID without committing entirely yet

        from services.phase_transition import start_phase_two_automatically
        start_phase_two_automatically(db, new_result)

        # 💾 Descargar físicamente la imagen al servidor local (/static/evidencias/reporte_{id}.jpg)
        local_img_path = None
        try:
            from services.image_persistence import persistir_imagen_local
            local_img_path = persistir_imagen_local(candidate_img, new_result.id, post_url=item.get("url"))
        except Exception:
            local_img_path = None
        
        # Platform specific data
        plat_data = item.get("platform_data", {})
        if not isinstance(plat_data, dict):
            plat_data = {}
            
        if local_img_path:
            plat_data["image_urls"] = json.dumps([local_img_path])

        if plat_data is not None:
            plat = str(item.get("plataforma", "")).lower()
            try:
                if plat == "facebook":
                    clean_data = {k: v for k, v in plat_data.items() if hasattr(ReporteFacebookData, k)}
                    clean_data["seller_name"] = clean_data.get("seller_name") or new_result.titular_cuenta
                    db.add(ReporteFacebookData(reporte_id=new_result.id, **clean_data))
                elif plat == "instagram":
                    clean_data = {k: v for k, v in plat_data.items() if hasattr(ReporteInstagramData, k)}
                    clean_data["username"] = clean_data.get("username") or new_result.titular_cuenta
                    db.add(ReporteInstagramData(reporte_id=new_result.id, **clean_data))
                elif plat == "tiktok":
                    clean_data = {k: v for k, v in plat_data.items() if hasattr(ReporteTiktokData, k)}
                    clean_data["username"] = clean_data.get("username") or new_result.titular_cuenta
                    db.add(ReporteTiktokData(reporte_id=new_result.id, **clean_data))
                elif plat == "mercadolibre":
                    clean_data = {k: v for k, v in plat_data.items() if hasattr(ReporteMercadoLibreData, k)}
                    db.add(ReporteMercadoLibreData(reporte_id=new_result.id, **clean_data))
            except Exception as pe:
                cron_logger.log(f"ℹ️ [Plataforma Data] {pe}")

        db.commit()
        cron_logger.log(f"✅ [Éxito] Reporte guardado y enviado a Fase 2: {brand.nombre} - {item.get('plataforma')} - {new_result.url_evidencia}")

        # Trigger correlación automática
        try:
            CorrelationEngine.analyze_new_reports(db, [new_result.id])
        except Exception as ce:
            cron_logger.log(f"ℹ️ [Correlación] {ce}")

        return True

    except Exception as e:
        db.rollback()
        cron_logger.log(f"⚠️ Error al guardar item de {item.get('plataforma')}: {e}")
        return False

async def run_automatic_scan(*args, **kwargs):
    """Ejecuta el ciclo de escaneo automático para todas las marcas."""
    global _stop_requested
    _stop_requested = False

    cron_logger.log("====== INICIANDO ESCANEO AUTOMÁTICO ======")
    cron_logger.set_status("running")
    
    db = SessionLocal()
    from services.cron_service import set_running
    set_running(db, True)
    try:
        from sqlalchemy import func
        brands = db.query(Brand).filter(func.lower(func.trim(Brand.estado)).like("%activa%")).all()
        if not brands:
            brands = db.query(Brand).all()
        if not brands:
            cron_logger.log("⚠️ No hay marcas registradas en el sistema. Registra marcas antes de escanear.")
            return

        from services import cron_service
        import json
        cron_config = cron_service.get_cron_config(db)
        
        try:
            marcas_ids = json.loads(cron_config.marcas_seleccionadas) if cron_config.marcas_seleccionadas else []
            if marcas_ids:
                filtered = [b for b in brands if b.id in marcas_ids]
                brands = filtered
                if not brands:
                    cron_logger.log("⚠️ Ninguna marca seleccionada está disponible para escanear.")
                    return
            else:
                cron_logger.log(f"ℹ️ Marcas seleccionadas en blanco: escaneando {len(brands)} marca(s) registradas.")
        except Exception as e:
            cron_logger.log(f"Error parseando marcas_seleccionadas, usando marcas activas: {e}")
        
        try:
            provincias = json.loads(cron_config.provincias_seleccionadas)
            from services.argentina_scope import normalize_argentina_locations
            provincias = normalize_argentina_locations(provincias)
        except:
            provincias = ["Argentina"]
            
        limite = cron_config.limite_extraccion or 10
        settings.APIFY_MAX_ITEMS = limite

        try:
            plataformas_activas = json.loads(cron_config.plataformas_activas)
        except:
            plataformas_activas = ["facebook", "instagram", "tiktok", "mercadolibre"]

        # Excluir 'web' de escaneos automáticos (las webs quedan reservadas exclusivamente para el escaneo manual)
        plataformas_activas = [p for p in plataformas_activas if p != "web"]

        proveedor = getattr(cron_config, 'proveedor', 'google_meli_osint') or 'google_meli_osint'

        # Si el proveedor es Apify o RapidAPI, excluir automáticamente MercadoLibre para evitar conflictos
        if proveedor in ("apify", "rapidapi"):
            plataformas_activas = [p for p in plataformas_activas if p != "mercadolibre"]

        engine = ScraperEngine()
        
        for brand in brands:
            if _stop_requested:
                cron_logger.log("🛑 [Detención de Emergencia] Escaneo cancelado.")
                break

            cron_logger.log(f"--- Procesando marca: {brand.nombre} ---")
            cron_logger.set_progress(marca=brand.nombre)
            
            for platform_name in plataformas_activas:
                if _stop_requested:
                    break

                platform_limits = {
                    "facebook": cron_config.limite_extraccion_fb,
                    "instagram": cron_config.limite_extraccion_ig,
                    "tiktok": cron_config.limite_extraccion_tt,
                    "mercadolibre": cron_config.limite_extraccion_ml,
                }
                platform_limit = max(1, int(platform_limits.get(platform_name) or 10))
                inserted_count = 0
                settings.APIFY_MAX_ITEMS = platform_limit
                already_reported = db.query(ReporteBrandDefense.url_evidencia).filter(
                    func.lower(ReporteBrandDefense.plataforma) == platform_name
                ).all()
                seen_urls = {
                    engine._item_url_key({"url": row[0]})
                    for row in already_reported
                    if row[0]
                }

                keywords = await generate_keywords(brand, platform_name)
                cron_logger.log(f"Keywords a buscar en {platform_name}: {keywords}")

                search_variants = ("", " réplica", " calidad premium", " importadas")
                for pass_number, search_suffix in enumerate(search_variants, start=1):
                    if _stop_requested or inserted_count >= platform_limit:
                        break

                    if pass_number > 1:
                        cron_logger.log(f"🔎 [Búsqueda ampliada] Variante: {search_suffix.strip()}")

                    for keyword in keywords:
                        if _stop_requested or inserted_count >= platform_limit:
                            break
                        search_query = f"{keyword}{search_suffix}"

                        # Las ubicaciones por provincia son solo para Facebook.
                        # El resto de plataformas barren a nivel país.
                        locs_to_search = provincias if platform_name == "facebook" else ["Argentina"]

                        for provincia in locs_to_search:
                            if _stop_requested or inserted_count >= platform_limit:
                                break

                            cron_logger.log(f"-> Escaneando {platform_name} para '{keyword}' en '{provincia}'")
                            cron_logger.set_progress(plataforma=platform_name)

                            try:
                                remaining = platform_limit - inserted_count
                                settings.APIFY_MAX_ITEMS = min(max(remaining * 3, remaining), 100)
                                if platform_name == "facebook":
                                    item_stream = engine.scrape_facebook(
                                        search_query, provincia, proveedor, exclude_urls=seen_urls
                                    )
                                elif platform_name == "instagram":
                                    item_stream = engine.scrape_instagram(
                                        search_query, provincia, proveedor, exclude_urls=seen_urls
                                    )
                                elif platform_name == "tiktok":
                                    item_stream = engine.scrape_tiktok(
                                        search_query, provincia, proveedor, exclude_urls=seen_urls
                                    )
                                elif platform_name == "mercadolibre":
                                    item_stream = engine.scrape_mercadolibre(
                                        search_query, provincia, proveedor
                                    )
                                else:
                                    continue

                                async for item in item_stream:
                                    if _stop_requested or inserted_count >= platform_limit:
                                        break
                                    url_key = engine._item_url_key(item)
                                    if url_key and url_key in seen_urls:
                                        continue
                                    if url_key:
                                        seen_urls.add(url_key)
                                    if process_and_save_single_result(db, item, brand, keyword):
                                        inserted_count += 1
                                        cron_logger.log(
                                            f"📊 [Límite] {platform_name}: "
                                            f"{inserted_count}/{platform_limit} reportes insertados."
                                        )

                                if _stop_requested:
                                    break
                                await asyncio.sleep(0.25)
                            except Exception as e:
                                cron_logger.log(
                                    f"Error en {platform_name} para {search_query} en {provincia}: {e}"
                                )

                    if inserted_count < platform_limit and pass_number < len(search_variants):
                        await asyncio.sleep(0.75)

                if inserted_count < platform_limit:
                    cron_logger.log(
                        f"ℹ️ [Cupo incompleto] {platform_name}: se insertaron "
                        f"{inserted_count}/{platform_limit}; se agotaron las variantes "
                        "de búsqueda sin encontrar más resultados únicos que pasen los filtros."
                    )

            if _stop_requested:
                break
                        
        if _stop_requested:
            cron_logger.log("🛑 ====== ESCANEO DETENIDO POR EMERGENCIA ======")
        else:
            cron_logger.log("====== ESCANEO AUTOMÁTICO FINALIZADO ======")
        
    except Exception as e:
        cron_logger.log(f"Error fatal en escaneo: {e}")
        db.rollback()
    finally:
        set_running(db, False)
        cron_logger.set_status("idle")
        db.close()

def update_job_schedule(db: Session = None):
    """Actualiza la programación del trabajo en el scheduler usando la config de DB o config.py."""
    scheduler.remove_all_jobs()
    
    if db:
        from services import cron_service
        config = cron_service.get_cron_config(db)
        is_enabled = bool(config.is_active)
        hour = config.hora if config.hora is not None else 2
        minute = config.minuto if config.minuto is not None else 0
    else:
        is_enabled = settings.CRON_ENABLED
        minute = settings.CRON_MINUTE
        hour = settings.CRON_HOUR
    
    if is_enabled:
        scheduler.add_job(
            run_automatic_scan,
            'cron',
            hour=hour,
            minute=minute,
            id='main_scan_job',
            replace_existing=True
        )
        cron_logger.log(f"⏰ [Cron Programado] ACTIVO: Programado para ejecutarse a las {hour:02d}:{minute:02d} (Hora Argentina)")
    else:
        cron_logger.log("⏸️ [Cron Programado] Motor programado desactivado.")

async def trigger_manual_scan():
    """Lanza el escaneo desde el panel (sin esperar al cron)."""
    cron_logger.log("🚀 [Manual] Inicio de escaneo forzado solicitado.")
    await run_automatic_scan()
