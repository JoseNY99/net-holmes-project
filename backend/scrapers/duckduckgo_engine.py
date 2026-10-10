import asyncio
import re
from typing import AsyncGenerator, Dict, Any
from services.cron_logger import cron_logger

# Importación síncrona, ejecutaremos en thread para no bloquear
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

def _sync_ddg_search(query: str, limit: int):
    if not DDGS:
        raise ImportError("duckduckgo_search no está instalado.")
    with DDGS() as ddgs:
        # timelimit='w' para restringir a la última semana (temporalidad estricta)
        return list(ddgs.text(query, region='ar-es', safesearch='off', timelimit='w', max_results=limit))

async def search_duckduckgo(platform: str, keyword: str, limit: int, city_name: str = None) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Busca usando DuckDuckGo (Index-Based Scraping).
    platform: 'mercadolibre', 'facebook', 'instagram', 'tiktok'
    """
    def _build_dork(kw, loc, strict=True):
        kw_str = f'"{kw}"' if strict else kw
        fake_term = '("réplica" OR "replica" OR "G5" OR "AAA" OR "1.1" OR "clon" OR "espejo" OR "importadas" OR "showroom")'
        exclusiones = '-Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA'

        loc_str = loc or "Argentina"
        if loc_str.lower() in ("argentina", "todo el pais", "todas"):
            geo_term = '(Argentina OR "Buenos Aires" OR CABA OR Rosario OR Córdoba OR "envios a todo el pais")'
        else:
            geo_term = f'("{loc_str}" Argentina)'

        if platform == "mercadolibre":
            q = f'site:articulo.mercadolibre.com.ar {kw_str} {geo_term} -"tienda oficial" -"oficial"'
        elif platform == "facebook":
            q = f'site:facebook.com/marketplace/ {kw_str} {fake_term} {geo_term} {exclusiones}'
        elif platform == "instagram":
            q = f'(site:instagram.com/p/ OR site:instagram.com/reel/) {kw_str} {fake_term} {geo_term} {exclusiones}'
        elif platform == "tiktok":
            q = f'site:tiktok.com/@*/video/ {kw_str} {fake_term} {geo_term} {exclusiones}'
        else:
            q = f'{kw_str} {fake_term} {geo_term} {exclusiones}'
        return q

    # Intentos de búsqueda: 1) Estricto, 2) Holgado, 3) Dataset Kaggle (Demo)
    results = []
    
    # Intento 1: Estricto
    query_strict = _build_dork(keyword, city_name, strict=True)
    cron_logger.log(f"[DDG] Consultando Dork OSINT Estricto: {query_strict}")
    try:
        results = await asyncio.to_thread(_sync_ddg_search, query_strict, limit)
    except Exception as e:
        cron_logger.log(f"⚠️ [DDG] Error en búsqueda estricta: {e}")

    def _sync_loose(q, l):
        if not DDGS: return []
        with DDGS() as ddgs:
            return list(ddgs.text(q, region='ar-es', safesearch='off', max_results=l))

    # Intento 2: Holgado (sin timelimit, sin comillas exactas)
    if not results:
        query_loose = _build_dork(keyword, city_name, strict=False)
        cron_logger.log(f"[DDG] Consultando Dork OSINT Holgado: {query_loose}")
        try:
            results = await asyncio.to_thread(_sync_loose, query_loose, limit)
        except Exception as e:
            cron_logger.log(f"⚠️ [DDG] Error en búsqueda holgada: {e}")

    # Intento 3: Sin filtro de ubicación (Apertura total a todo Argentina)
    if not results and city_name:
        query_global = _build_dork(keyword, None, strict=False)
        cron_logger.log(f"[DDG] Consultando Dork OSINT Nacional (Sin provincia): {query_global}")
        try:
            results = await asyncio.to_thread(_sync_loose, query_global, limit)
        except Exception as e:
            cron_logger.log(f"⚠️ [DDG] Error en búsqueda nacional: {e}")

    # Intento 4 (Fase 3): Búsqueda genérica de productos asociados a la marca
    if not results:
        generic_brand = keyword.split(' ')[0] # Ej: "Adidas" de "Adidas Forum"
        query_imitacion = _build_dork(f"zapatillas {generic_brand} OR calzados {generic_brand} OR remeras {generic_brand} OR conjunto {generic_brand}", None, strict=False)
        cron_logger.log(f"[DDG] Iniciando 'Tercera Fase': Búsqueda genérica de artículos: {query_imitacion}")
        try:
            results = await asyncio.to_thread(_sync_loose, query_imitacion, limit)
        except Exception as e:
            cron_logger.log(f"⚠️ [DDG] Error en Tercera Fase (genérica): {e}")

    if not results:
        cron_logger.log(f"[DDG] ⚠️ Definitivamente no hay datos reales indexados para {keyword} en {platform}.")
        return

    valid_results = []
    for item in results:
        href = item.get("href", "")
        # Ignorar anuncios y redirecciones basura de DDG/Bing
        if "aclick" in href or "bing.com" in href or "duckduckgo.com" in href:
            continue
        valid_results.append(item)
        
    if not valid_results:
        cron_logger.log(f"[DDG] ⚠️ Solo se encontraron anuncios o redirecciones vacías.")
        return

    for item in valid_results:
            # Extraer precio posible (e.g. "$ 15.000" o "$15000")
            price = None
            price_match = re.search(r'\$\s?([\d\.]+)', item.get("body", ""))
            if price_match:
                price_str = price_match.group(1).replace(".", "")
                if price_str.isdigit():
                    price = float(price_str)
            
            # Obtener logo genérico según plataforma
            logo_url = ""
            if platform == "mercadolibre":
                logo_url = "https://http2.mlstatic.com/frontend-assets/ml-web-navigation/ui-navigation/6.6.73/mercadolibre/logo-pt__large_plus.png"
            elif platform == "facebook":
                logo_url = "https://upload.wikimedia.org/wikipedia/commons/b/b8/2021_Facebook_icon.svg"
            elif platform == "instagram":
                logo_url = "https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png"
            elif platform == "tiktok":
                logo_url = "https://upload.wikimedia.org/wikipedia/en/a/a9/TikTok_logo.svg"

            # Parsear username si es posible de la URL
            seller_name = "Usuario Desconocido"
            href = item.get("href", "")
            if href:
                try:
                    from urllib.parse import urlparse
                    path = urlparse(href).path.strip('/')
                    if path:
                        segments = [s for s in path.split('/') if s and s not in ('p', 'item', 'reel', 'explore', 'watch', 'groups', 'events', 'marketplace', 'discover', 'tag', 'search')]
                        if segments:
                            seller_name = f"@{segments[0]}"
                except:
                    pass

            if platform == "instagram" and "instagram.com/" in href:
                parts = href.split("instagram.com/")
                if len(parts) > 1:
                    possible_name = parts[1].split("/")[0]
                    if possible_name not in ["p", "reel", "explore", "tv"]:
                        seller_name = f"@{possible_name}"
            elif platform == "tiktok" and "@" in href:
                parts = href.split("@")
                if len(parts) > 1:
                    seller_name = "@" + parts[1].split("/")[0].split("?")[0]
            elif platform == "mercadolibre":
                seller_name = "Vendedor MeLi" # Default for ML
                body_lower = item.get("body", "").lower()
                if "por " in body_lower:
                    try:
                        idx = body_lower.index("por ") + 4
                        end_idx = body_lower.find(" ", idx)
                        if end_idx == -1: end_idx = len(body_lower)
                        extracted = item.get("body", "")[idx:end_idx]
                        if extracted and len(extracted) > 2:
                            seller_name = extracted
                    except:
                        pass
            
            # Try to extract phone numbers from description/body using regex directly
            # to avoid circular import issues if get_whatsapp_number is not accessible
            found_phone = None
            phone_match = re.search(r'(?:(?:00)?549?)?0?(11|[2368]\d)\d{8}', item.get("body", "").replace(" ", "").replace("-", ""))
            if phone_match:
                found_phone = phone_match.group(0)

            yield {
                "plataforma": platform,
                "title": item.get("title", "Sin Título"),
                "description": item.get("body", ""),
                "price": price,
                "url": href,
                "seguidores_infractor": None,
                "imagen_urls": f"['{logo_url}']" if logo_url else "[]",
                "seller_profile": {
                    "name": seller_name,
                    "url": href,
                    "phone": found_phone
                },
                "location": city_name or "Argentina",
                "raw_data": item,
                "platform_data": {
                    "snippet": item.get("body", ""),
                    "search_query": keyword,
                    "source_engine": "DuckDuckGo"
                }
            }
            # Pequeña pausa asíncrona entre yields
            await asyncio.sleep(0.1)
