"""
Nivel 1: Motor de Indexación OSINT vía DuckDuckGo HTML Clásico.
Construye queries de dorking con operadores site: restringidos a Argentina.
Realiza scraping puro y nativo sin dependencias frágiles de terceros.
Parsea título y snippet para extraer precio, seguidores y username de forma heurística.
"""

import asyncio
import re
import httpx
from bs4 import BeautifulSoup
import urllib.parse
from typing import AsyncGenerator, Dict, Any
from services.cron_logger import cron_logger
from scrapers.filtro_comercial import filtrar_item_comercial

# ─── Dorking Templates por plataforma ──────────────────────────────────────────

DORK_TEMPLATES = {
    "mercadolibre": {
        "strict": 'site:articulo.mercadolibre.com.ar "{kw}" {loc_term} -"tienda oficial"',
        "loose":  'site:mercadolibre.com.ar {kw} {loc_term} -"tienda oficial"',
        "ultra":  'site:mercadolibre.com.ar zapatillas OR remeras OR conjunto OR calzados {brand} {loc_term} -"tienda oficial"',
    },
    "facebook": {
        "strict": 'site:facebook.com/marketplace/ "{kw}" ("réplica" OR "replica" OR "G5" OR "AAA" OR "1.1" OR "clon" OR "espejo" OR "importadas") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
        "loose":  'site:facebook.com/marketplace/ "{kw}" ("envios" OR "showroom" OR "talles" OR "cuotas" OR "precio") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
        "ultra":  'site:facebook.com/marketplace/ "{brand}" ("réplica" OR "replica" OR "importadas" OR "G5") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
    },
    "instagram": {
        "strict": '(site:instagram.com/p/ OR site:instagram.com/reel/) "{kw}" ("réplica" OR "replica" OR "G5" OR "AAA" OR "1.1" OR "clon" OR "espejo" OR "importadas") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
        "loose":  '(site:instagram.com/p/ OR site:instagram.com/reel/) "{kw}" ("envios" OR "showroom" OR "talles" OR "cuotas" OR "stock") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
        "ultra":  'site:instagram.com "{brand}" ("réplica" OR "replica" OR "importadas" OR "G5") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
    },
    "tiktok": {
        "strict": 'site:tiktok.com/@*/video/ "{kw}" ("réplica" OR "replica" OR "G5" OR "AAA" OR "1.1" OR "clon" OR "importadas") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
        "loose":  'site:tiktok.com/@*/video/ "{kw}" ("talles" OR "envios" OR "precio" OR "stock" OR "cuotas" OR "showroom") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
        "ultra":  'site:tiktok.com "{brand}" ("réplica" OR "replica" OR "importadas" OR "G5") {loc_term} -Colombia -México -Mexico -Chile -España -Perú -Peru -Bogotá -Bogota -Medellín -Lima -Santiago -USA',
    },
}

PLATFORM_LOGOS = {
    "mercadolibre": "https://http2.mlstatic.com/frontend-assets/ml-web-navigation/ui-navigation/6.6.73/mercadolibre/logo-pt__large_plus.png",
    "facebook":     "https://upload.wikimedia.org/wikipedia/commons/b/b8/2021_Facebook_icon.svg",
    "instagram":    "https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png",
    "tiktok":       "https://upload.wikimedia.org/wikipedia/en/a/a9/TikTok_logo.svg",
}


# ─── Scraper Nativo DDG HTML ───────────────────────────────────────────────────

async def _fetch_ddg_html(query: str, limit: int = 30) -> list:
    """
    Usa el paquete ddgs oficial que maneja correctamente los tokens VQD y bypasses de TLS (curl_cffi)
    para evitar el agresivo anti-bot de DuckDuckGo (Error 202/302).
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        try:
            from ddgs import DDGS
        except ImportError:
            DDGS = None
            
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not DDGS:
        return []

    results = []
    try:
        def fetch():
            with DDGS() as ddgs:
                return list(ddgs.text(query, region="ar-es", max_results=limit))
        
        # Ejecutar en threadpool porque DDGS es síncrono
        raw_results = await asyncio.to_thread(fetch)
        
        for item in raw_results:
            results.append({
                "title": item.get("title", ""),
                "href": item.get("href", ""),
                "body": item.get("body", "")
            })
                
    except Exception as e:
        cron_logger.log(f"⚠️ [DDG OSINT] Error usando ddgs: {e}")
        
    valid_results = []
    for item in results:
        href = item.get("href", "")
        if "aclick" in href or "bing.com" in href or "duckduckgo.com" in href:
            continue
        valid_results.append(item)
        
    return valid_results


# ─── Heurísticas de Parsing ───────────────────────────────────────────────────

def _extract_price(text: str) -> float | None:
    """Extrae precio en pesos argentinos de un snippet."""
    match = re.search(r'\$\s?([\d\.]+(?:,\d{2})?)', text)
    if match:
        raw = match.group(1).replace(".", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            pass
    return None


def _extract_followers(text: str) -> int | None:
    """Extrae conteo de seguidores de un snippet usando la regex solicitada."""
    match = re.search(r'([\d\.,]+[kmKMsS]?)\s*(?:seguidores|followers)', text, re.IGNORECASE)
    if match:
        raw = match.group(1).lower().replace(",", ".")
        multiplier = 1
        if 'k' in raw:
            multiplier = 1000
            raw = raw.replace('k', '')
        elif 'm' in raw:
            multiplier = 1000000
            raw = raw.replace('m', '')
        elif 's' in raw:
            raw = raw.replace('s', '')
        try:
            return int(float(raw) * multiplier)
        except ValueError:
            pass
    return None


def _extract_username(platform: str, url: str, title: str = "") -> str:
    """Extrae el username de una URL y título según la plataforma."""
    if platform == "instagram":
        match = re.search(r'\(@([a-zA-Z0-9_.-]+)\)', title)
        if match: return f"@{match.group(1)}"
        match2 = re.search(r'^([a-zA-Z0-9_.-]+) on Instagram', title)
        if match2: return f"@{match2.group(1)}"
        if "instagram.com/" in url:
            path = url.split("instagram.com/")[1].split("?")[0].strip("/")
            segments = path.split("/")
            if segments:
                if segments[0] not in ("p", "reel", "explore", "accounts", "tags"):
                    return f"@{segments[0]}"
    elif platform == "tiktok":
        match = re.search(r'\(@([a-zA-Z0-9_.-]+)\)', title)
        if match: return f"@{match.group(1)}"
        match2 = re.search(r'(@[a-zA-Z0-9_.-]+)', title)
        if match2: return match2.group(1)
        if "tiktok.com/@" in url:
            path = url.split("tiktok.com/@")[1].split("?")[0]
            username = path.split("/")[0]
            if username:
                return f"@{username}"
    elif platform == "facebook":
        if "Marketplace" not in title and "marketplace" not in url.lower():
            match = re.search(r'^(.+?)\s*(?:\||-)\s*Facebook', title)
            if match: 
                clean = match.group(1).strip()
                return f"@{clean.replace(' ', '')}"
        if "facebook.com/" in url:
            parts = url.split("facebook.com/")
            if len(parts) > 1:
                segment = parts[1].split("/")[0].split("?")[0]
                if segment and segment not in ("marketplace", "watch", "groups", "events", "share", "login"):
                    return f"@{segment}"
    elif platform == "mercadolibre":
        return "Vendedor MeLi"
        
    # Fallback to URL path extraction
    if url:
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path.strip('/')
            if path:
                # Get the first meaningful segment
                segments = [s for s in path.split('/') if s and s not in ('p', 'item', 'reel', 'explore', 'watch', 'groups', 'events', 'marketplace')]
                if segments:
                    return f"@{segments[0]}"
        except:
            pass
            
    return "Usuario Desconocido"


def _build_platform_data(platform: str, item: dict, keyword: str) -> dict:
    """Construye el diccionario platform_data para mapear a tablas 1:1."""
    import json
    snippet = item.get("body", "")
    url = item.get("href", "")
    title = item.get("title", "")
    username = _extract_username(platform, url, title)
    
    img_urls_match = re.findall(r'(https?://\S+\.(?:jpg|jpeg|png|gif|webp))', snippet, re.IGNORECASE)
    image_urls = json.dumps(img_urls_match) if img_urls_match else None
    
    followers = _extract_followers(f"{title} {snippet}")

    if platform == "mercadolibre":
        seller_id = None
        item_id = None
        sid_match = re.search(r'MLA-?(\d+)', url)
        if sid_match:
            seller_id = sid_match.group(1)
            item_id = sid_match.group(0)
        return {
            "seller_id": seller_id,
            "seller_nickname": username,
            "seller_reputation_level": None,
            "seller_reputation_score": None,
            "seller_transactions_completed": None,
            "item_id": item_id,
            "item_condition": None,
            "category_id": None,
            "category_name": None,
            "shipping_mode": None,
            "available_stock": None,
            "sold_quantity": None,
            "questions_count": None,
            "warranty_text": None,
            "official_store_id": None,
            "image_urls": image_urls
        }
    elif platform == "instagram":
        return {
            "username": username.replace("@", ""),
            "followers": followers,
            "bio_text": snippet,
            "image_urls": image_urls,
            "likes_count": None,
            "comments_count": None,
            "profile_pic_url": None,
            "caption_full": title,
            "hashtags": None,
            "user_id_ig": None,
            "is_business_account": None,
            "post_type": None
        }
    elif platform == "tiktok":
        return {
            "username": username.replace("@", ""),
            "followers": followers,
            "bio_text": snippet,
            "image_urls": image_urls,
            "likes": None,
            "shares": None,
            "comments_count": None,
            "description_full": title,
            "video_views": None,
            "video_id": None,
            "hashtags": None,
            "sounds_used": None
        }
    elif platform == "facebook":
        return {
            "seller_name": username,
            "seller_profile_url": url,
            "seller_location_city": None,
            "seller_location_province": None,
            "image_urls": image_urls,
            "comments_count": None,
            "listing_id": None,
            "marketplace_category": None,
            "item_condition": None,
            "delivery_method": None,
            "comments_text": None
        }
    
    return {}


# ─── Función principal asíncrona ──────────────────────────────────────────────

async def ejecutar_motor_indexado(
    platform: str,
    keyword: str,
    limit: int = 15,
    provincias: list[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Nivel 1 de la cascada: DuckDuckGo Native HTML Scraper.
    
    Intenta 4 estrategias de dorking en orden de restricción decreciente:
      1. Estricto (comillas + provincia)
      2. Holgado  (sin comillas, Argentina genérico)
      3. Nacional (sin provincia, apertura total)
      4. Ultra    (búsqueda genérica de categorías de producto asociadas a la marca)
    
    Yields dicts normalizados listos para process_and_save_single_result().
    """
    templates = DORK_TEMPLATES.get(platform, DORK_TEMPLATES["facebook"])
    brand_word = keyword.split(" ")[0]  # e.g. "Adidas" de "Adidas Forum"
    
    requested_locations = provincias if isinstance(provincias, list) else [provincias]
    target_locations = [loc for loc in requested_locations if loc] or ["Argentina"]
    
    yielded_count = 0

    for loc_name in target_locations:
        loc = loc_name or "Argentina"
        if loc.lower() in ("argentina", "todo el pais", "todas"):
            loc_term = '(Argentina OR "Buenos Aires" OR CABA OR Rosario OR Córdoba OR "envios a todo el pais")'
        else:
            loc_term = f'("{loc}" Argentina)'
        
        # ── Estrategia 1: Estricto ──
        query = templates["strict"].format(kw=keyword, loc=loc, loc_term=loc_term, brand=brand_word)
        cron_logger.log(f"[DDG Native] 🔍 Nivel 1 Estricto: {query}")
        results = await _fetch_ddg_html(query, limit)

        # ── Estrategia 2: Holgado ──
        if not results:
            query = templates["loose"].format(kw=keyword, loc=loc, loc_term=loc_term, brand=brand_word)
            cron_logger.log(f"[DDG Native] 🔍 Nivel 1 Holgado: {query}")
            results = await _fetch_ddg_html(query, limit)

        # ── Estrategia 3: Ultra (categorías genéricas de la marca) ──
        if not results:
            query = templates["ultra"].format(kw=keyword, loc=loc, loc_term=loc_term, brand=brand_word)
            cron_logger.log(f"[DDG Native] 🔍 Nivel 1 Ultra (genérico): {query}")
            results = await _fetch_ddg_html(query, limit)

        if not results:
            cron_logger.log(f"[DDG Native] ❌ Sin resultados para '{keyword}' en {platform} ({loc}).")
            continue

        cron_logger.log(f"[DDG Native] ✅ {len(results)} resultados obtenidos para '{keyword}' en {platform} ({loc}).")

        logo = PLATFORM_LOGOS.get(platform, "")

        for item in results:
            href = item.get("href", "")
            body = item.get("body", "")
            title = item.get("title", "Sin Título")

            # ── Validación Estricta de Dominio por Plataforma ──
            href_low = href.lower()
            if platform == "facebook" and "facebook.com" not in href_low:
                continue
            if platform == "instagram" and "instagram.com" not in href_low:
                continue
            if platform == "tiktok" and ("tiktok.com/@" not in href_low and "vt.tiktok.com" not in href_low):
                continue
            if platform == "mercadolibre" and "mercadolibre.com" not in href_low:
                continue

            price = _extract_price(f"{title} {body}")
            followers = _extract_followers(f"{title} {body}")
            username = _extract_username(platform, href, title)

            # Omitir resultados de tiendas oficiales explícitamente
            if "tienda oficial" in title.lower() or (brand_word.lower() in username.lower() and "oficial" in username.lower()):
                continue

            # ── TikTok oEmbed Enrichment ──
            # Si DDG devolvió un video de TikTok pero sin username/thumbnail,
            # consultar la API gratuita oEmbed para extraer datos reales.
            product_image = None
            if platform == "tiktok" and href and "video/" in href:
                enriched = await _tiktok_oembed_enrich(href)
                if enriched:
                    if not username or username in ("Desconocido", "Usuario Desconocido"):
                        username = enriched.get("author_name", username) or username
                    if not title or title == "Sin Título":
                        title = enriched.get("title", title) or title
                    product_image = enriched.get("thumbnail_url")

            # Buscar imagen en snippet si no hay imagen de oEmbed
            if not product_image:
                img_match = re.search(r'(https?://\S+\.(?:jpg|jpeg|png|webp))', f"{title} {body}", re.IGNORECASE)
                if img_match:
                    product_image = img_match.group(1)

            final_img_urls = f'["{product_image}"]' if product_image else "[]"

            mapped_item = {
                "plataforma": platform,
                "title": title,
                "description": body,
                "price": price,
                "url": href,
                "imagen_urls": final_img_urls,
                "seller_profile": {
                    "name": username,
                    "url": href,
                    "followers": followers
                },
                "seguidores_infractor": followers,
                "location": loc_name,
                "raw_data": item,
                "platform_data": _build_platform_data(platform, item, keyword),
            }

            # Filtro de Relevancia Comercial: descartar memes, reviews, hauls sin venta
            # MercadoLibre y Facebook Marketplace son inherentemente comerciales, no filtrar
            # Filtro comercial MOVIDO a cron_manager.py para evitar triple filtrado
            # que descarta resultados legítimos antes de llegar a la DB

            yielded_count += 1
            yield mapped_item
            await asyncio.sleep(0.1)  # Chill micro-pausa

    # ── Fallback: MercadoLibre API Pública Gratuita ──
    # Si DDG no devolvió nada para ML, consultar directamente la API oficial
    if platform == "mercadolibre" and yielded_count == 0:
        cron_logger.log(f"[DDG Native] 📦 Fallback ML: DDG devolvió 0 resultados. Consultando API pública de MercadoLibre...")
        async for ml_item in _fallback_mercadolibre_api(keyword, limit):
            yield ml_item


async def _tiktok_oembed_enrich(video_url: str) -> dict | None:
    """
    Consulta la API pública gratuita oEmbed de TikTok para extraer
    @username, título del video y foto de portada sin navegador.
    """
    try:
        oembed_url = f"https://www.tiktok.com/oembed?url={urllib.parse.quote(video_url, safe='')}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                return {
                    "author_name": data.get("author_name", ""),
                    "title": data.get("title", ""),
                    "thumbnail_url": data.get("thumbnail_url", ""),
                }
    except Exception:
        pass
    return None


async def _fallback_mercadolibre_api(keyword: str, limit: int = 10) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Consulta directa a la API Pública Gratuita de MercadoLibre Argentina.
    Se usa como fallback cuando DDG no encuentra resultados para ML.
    """
    try:
        api_url = f"https://api.mercadolibre.com/sites/MLA/search?q={urllib.parse.quote(keyword)}&limit={limit}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                api_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("results", [])
            cron_logger.log(f"[Fallback ML API] ✅ {len(items)} items encontrados para '{keyword}'.")

            for api_item in items:
                seller = api_item.get("seller", {})
                seller_id = str(seller.get("id", "Desconocido"))
                precio = float(api_item.get("price", 0.0))
                title = api_item.get("title", "Desconocido")
                url_pub = api_item.get("permalink", "")
                thumbnail = api_item.get("thumbnail", "")

                yield {
                    "plataforma": "mercadolibre",
                    "title": title,
                    "description": title,
                    "price": precio,
                    "url": url_pub.split("#")[0] if url_pub else "",
                    "imagen_urls": f'["{thumbnail}"]' if thumbnail else "[]",
                    "seller_profile": {
                        "name": f"Seller ID: {seller_id}",
                        "url": url_pub,
                        "followers": None,
                    },
                    "location": "Argentina",
                    "raw_data": api_item,
                    "platform_data": {
                        "seller_id": seller_id,
                        "item_id": api_item.get("id"),
                        "category_name": api_item.get("category_id", "Desconocida"),
                        "available_stock": api_item.get("available_quantity"),
                        "sold_quantity": api_item.get("sold_quantity"),
                        "item_condition": api_item.get("condition"),
                        "image_urls": f'["{thumbnail}"]' if thumbnail else None,
                        "snippet": f"API ML — Precio: ${precio}",
                        "search_query": keyword,
                        "source_engine": "MercadoLibre API Pública (Fallback DDG)",
                    },
                }
                await asyncio.sleep(0.05)

    except Exception as e:
        err_str = str(e)
        if "403" in err_str or "Forbidden" in err_str:
            cron_logger.log(f"[Fallback ML API] ℹ️ Aviso: La API pública de Mercado Libre no está disponible temporalmente (403 Forbidden).")
        else:
            cron_logger.log(f"[Fallback ML API] ℹ️ Nota: {e}")
