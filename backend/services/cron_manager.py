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

# Instancia del scheduler (reemplaza a cron_engine.py)
scheduler = AsyncIOScheduler()

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

def process_and_save_single_result(db: Session, item: Dict[str, Any], brand: Brand, keyword: str = ""):
    """Procesa, mapea a ScanResult y guarda un único resultado en la base de datos de inmediato."""
    
    # 1. Filtro Anti-Oficial / Filtro de País / Filtro de Marca
    title = item.get("title", "").lower()
    desc = item.get("description", "").lower()
    seller_name = item.get("seller_profile", {}).get("name", "").lower()
    raw_data_str = str(item.get("raw_data", "")).lower()
    
    combined_text = f"{title} {desc} {seller_name} {raw_data_str}"
    
    # a. Bloquear Tiendas Oficiales mediante Lista Negra Dinámica (DB) y Filtro Básico
    titular = item.get("seller_profile", {}).get("name", "")
    url = item.get("url", "")
    titulo = item.get("title", "")
    
    if es_cuenta_oficial(db, titular, url, titulo, brand.nombre):
        cron_logger.log(f"🚫 [Filtro Oficial DB] Descartado por ser cuenta oficial registrada de {brand.nombre}: {titular} ({url})")
        return

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
        return

    # b. Bloquear Países Extranjeros y Afianzar Localidad
    # Usa word boundaries (\b) para evitar falsos positivos como "usa" dentro de "usado"
    foreign_patterns = [
        r'\bbrasil\b', r'\bbrazil\b', r'\beeuu\b', r'\bestados unidos\b', r'\bunited states\b',
        r'\bmiami\b', r'\borlando\b', r'\bflorida\b', r'\bcalifornia\b', r'\btexas\b', r'\bnew york\b', r'\blos angeles\b',
        r'\bchile\b', r'\buruguay\b', r'\bmexico\b', r'\bespaña\b', r'\bcolombia\b',
        r'\bperu\b', r'\becuador\b', r'\bvenezuela\b', r'\bparaguay\b', r'\bbolivia\b',
        r'\bguatemala\b', r'\bcosta rica\b', r'\bpanama\b', r'\bhonduras\b', r'\bel salvador\b',
        r'\bnicaragua\b', r'\brepublica dominicana\b', r'\bpuerto rico\b',
        r'\bmadrid\b', r'\bbarcelona\b', r'\bbogota\b', r'\blima\b', 
        r'\bsantiago de chile\b', r'\bmontevideo\b', r'\basuncion\b',
        r'\busa\b'  # Con word boundary para no matchear "usado", "causa", etc.
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
        has_argentine = any(city in combined_text for city in ar_city_terms)
        if not has_argentine:
            cron_logger.log(f"🚫 [Filtro] Descartado por ubicación extranjera evidente: {item.get('title')}")
            return

    # c. Limpieza de "Basura" (Debe mencionar la marca o la palabra clave)
    brand_name = brand.nombre.lower()
    kw_lower = keyword.lower() if keyword else ""
    if brand_name not in combined_text and (not kw_lower or kw_lower not in combined_text):
        cron_logger.log(f"🚫 [Filtro] Descartado por no tener relación con '{brand.nombre}': {item.get('title')}")
        return

    # d. Filtro de URLs — Validación PERMISIVA (solo rechazar URLs claramente genéricas)
    item_url_raw = item.get("url", "N/A").lower()
    plataforma = str(item.get("plataforma", "")).lower()
    if item_url_raw != "n/a":
        # Rechazar URLs genéricas comunes en todas las plataformas
        generic_reject = ["/discover/", "/search?", "/explore/", "/tag/", "/hashtag/", "/login", "/signup"]
        if any(p in item_url_raw for p in generic_reject):
            cron_logger.log(f"🚫 [Filtro URL] Descartado por URL genérica ({plataforma}): {item_url_raw}")
            return

        # Validación permisiva por plataforma — solo rechazar lo que NO es contenido
        if plataforma == "instagram":
            # Aceptar /p/, /reel/, /stories/, perfiles (/username), etc.
            # Solo rechazar la raíz desnuda (instagram.com/) sin path útil
            if re.search(r'instagram\.com/?$', item_url_raw):
                cron_logger.log(f"🚫 [Filtro URL] Instagram descartado — URL raíz sin contenido: {item_url_raw}")
                return
        elif plataforma == "tiktok":
            # Aceptar /@user/video/, vt.tiktok.com short links, perfiles
            if re.search(r'tiktok\.com/?$', item_url_raw):
                cron_logger.log(f"🚫 [Filtro URL] TikTok descartado — URL raíz sin contenido: {item_url_raw}")
                return
        elif plataforma == "facebook":
            # Aceptar marketplace/, posts/, photo/, reel/, groups/, shop/, perfiles
            if re.search(r'facebook\.com/?$', item_url_raw):
                cron_logger.log(f"🚫 [Filtro URL] Facebook descartado — URL raíz sin contenido: {item_url_raw}")
                return
        elif plataforma == "mercadolibre":
            # Aceptar articulo.mercadolibre, /p/MLA (catálogo), listado.mercadolibre
            if not re.search(r'mercadolibre\.com\.ar/', item_url_raw):
                cron_logger.log(f"🚫 [Filtro URL] MercadoLibre descartado — no es dominio MLA: {item_url_raw}")
                return
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
                return
            
        from services.nlp_heuristics import extract_correlations
        correlaciones = extract_correlations(item)
        
        # Extraer imagen candidata directa
        candidate_img = _extract_single_clean_image_url(item)

        new_result = ReporteBrandDefense(
            pais=item.get("location", "Argentina"),
            producto_catalogo=keyword if keyword else "Desconocido",
            marca_afectada=brand.nombre,
            plataforma=item.get("plataforma"),
            titular_cuenta=item.get("seller_profile", {}).get("name", "Desconocido"),
            url_evidencia=item.get("url"),
            descripcion_post=item.get("description") or item.get("title", ""),
            precio_publico=float(item.get("price")) if item.get("price") and str(item.get("price")).replace('.','',1).isdigit() else None,
            direccion_publica=item.get("location", ""),
            telefono_publico=found_phone or item.get("phone") or item.get("platform_data", {}).get("phone"),
            seguidores_infractor=item.get("seguidores_infractor") or item.get("seller_profile", {}).get("followers") or item.get("platform_data", {}).get("followers"),
            estado="Pendiente"
        )
        db.add(new_result)
        db.flush() # Obtain ID without committing entirely yet

        # 💾 Descargar físicamente la imagen al servidor local (/static/evidencias/reporte_{id}.jpg)
        local_img_path = persistir_imagen_local(candidate_img, new_result.id, post_url=item.get("url"))
        
        # Platform specific data
        plat_data = item.get("platform_data", {})
        if not isinstance(plat_data, dict):
            plat_data = {}
            
        if local_img_path:
            plat_data["image_urls"] = json.dumps([local_img_path])

        if plat_data is not None:
            plat = item.get("plataforma", "").lower()
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

        db.commit()
        db.refresh(new_result)
        cron_logger.log(f"✅ [Éxito] Reporte guardado: {brand.nombre} - {item.get('plataforma')} - {new_result.url_evidencia}")

        # Trigger correlación automática
        try:
            CorrelationEngine.analyze_new_reports(db, [new_result.id])
        except Exception as ce:
            db.rollback()
            cron_logger.log(f"⚠️ Error en correlación automática: {ce}")

    except Exception as e:
        db.rollback()
        cron_logger.log(f"⚠️ Error al guardar item de {item.get('plataforma')}: {e}")

async def run_automatic_scan():
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
                if filtered:
                    brands = filtered
            else:
                cron_logger.log(f"ℹ️ Marcas seleccionadas en blanco: escaneando {len(brands)} marca(s) registradas.")
        except Exception as e:
            cron_logger.log(f"Error parseando marcas_seleccionadas, usando marcas activas: {e}")
        
        try:
            provincias = json.loads(cron_config.provincias_seleccionadas)
            if not provincias: # Si el usuario lo dejó vacío, busca a nivel país
                provincias = ["Argentina"]
            elif isinstance(provincias, str):
                provincias = [provincias]
        except:
            provincias = ["Argentina"]
            
        limite = cron_config.limite_extraccion or 10
        settings.APIFY_MAX_ITEMS = limite

        try:
            plataformas_activas = json.loads(cron_config.plataformas_activas)
        except:
            plataformas_activas = ["facebook", "instagram", "tiktok", "mercadolibre"]

        proveedor = getattr(cron_config, 'proveedor', 'apify')

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

                keywords = await generate_keywords(brand, platform_name)
                cron_logger.log(f"Keywords a buscar en {platform_name}: {keywords}")
                
                for keyword in keywords:
                    if _stop_requested:
                        break

                    # Las ubicaciones por provincia son solo para Facebook.
                    # El resto de plataformas barren a nivel país.
                    locs_to_search = provincias if platform_name == "facebook" else ["Argentina"]
                    
                    for provincia in locs_to_search:
                        if _stop_requested:
                            break

                        cron_logger.log(f"-> Escaneando {platform_name} para '{keyword}' en '{provincia}'")
                        cron_logger.set_progress(plataforma=platform_name)
                        
                        try:
                            if platform_name == "facebook":
                                settings.APIFY_MAX_ITEMS = cron_config.limite_extraccion_fb or 10
                                async for item in engine.scrape_facebook(keyword, provincia, proveedor):
                                    if _stop_requested:
                                        break
                                    process_and_save_single_result(db, item, brand, keyword)
                            elif platform_name == "instagram":
                                settings.APIFY_MAX_ITEMS = cron_config.limite_extraccion_ig or 10
                                async for item in engine.scrape_instagram(keyword, provincia, proveedor):
                                    if _stop_requested:
                                        break
                                    process_and_save_single_result(db, item, brand, keyword)
                            elif platform_name == "tiktok":
                                settings.APIFY_MAX_ITEMS = cron_config.limite_extraccion_tt or 10
                                async for item in engine.scrape_tiktok(keyword, provincia, proveedor):
                                    if _stop_requested:
                                        break
                                    process_and_save_single_result(db, item, brand, keyword)
                            elif platform_name == "mercadolibre":
                                settings.APIFY_MAX_ITEMS = cron_config.limite_extraccion_ml or 10
                                async for item in engine.scrape_mercadolibre(keyword, provincia, proveedor):
                                    if _stop_requested:
                                        break
                                    process_and_save_single_result(db, item, brand, keyword)
                            
                            if _stop_requested:
                                break
                            # Pequeña pausa entre llamadas a API
                            await asyncio.sleep(1)
                        except Exception as e:
                            cron_logger.log(f"Error en {platform_name} para {keyword} en {provincia}: {e}")

            # Escaneo de Tiendas Falsas y Phishing (Certstream / SSL) para el proveedor OSINT
            if not _stop_requested and proveedor == "google_meli_osint" and getattr(settings, "ENABLE_CERTSTREAM_SCAN", True):
                try:
                    cron_logger.log(f"🛡️ [Certstream Scanner] Analizando dominios y tiendas falsas para {brand.nombre}...")
                    async for item in engine.scan_certstream_domains(brand.nombre, limit=3):
                        if _stop_requested:
                            break
                        process_and_save_single_result(db, item, brand, brand.nombre)
                except Exception as e_cs:
                    cron_logger.log(f"⚠️ [Certstream Scanner] Error en escaneo de dominios: {e_cs}")
                        
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
    
    # Try to load from DB if provided, else use settings
    is_enabled = settings.CRON_ENABLED
    minute = settings.CRON_MINUTE
    hour = settings.CRON_HOUR
    
    if db:
        from services import cron_service
        config = cron_service.get_cron_config(db)
        is_enabled = config.is_active
        hour = config.hora
        minute = config.minuto
        # Si la config de BD tiene los campos, úsalos; si no, asume valores fijos o los de config.py
        # asumiendo que cron_service devuelve la config real.
    
    if is_enabled:
        scheduler.add_job(
            run_automatic_scan,
            'cron',
            hour=hour,
            minute=minute,
            id='main_scan_job',
            replace_existing=True
        )
        cron_logger.log(f"Cron ACTIVO: Programado para la hora {hour}:{minute}")
    else:
        cron_logger.log("Cron deshabilitado.")

async def trigger_manual_scan():
    """Lanza el escaneo desde el panel (sin esperar al cron)."""
    if cron_logger.get_status().get("status") == "running":
        cron_logger.log("⚠️ Intento de inicio manual ignorado: Ya hay un escaneo en curso.")
        return
    cron_logger.log("🚀 Inicio manual solicitado por el usuario.")
    asyncio.create_task(run_automatic_scan())
