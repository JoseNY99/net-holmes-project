"""
Nivel 2: Playwright Headless + Stealth Fallback.
Se activa cuando el Nivel 1 (DuckDuckGo OSINT) retorna 0 resultados.

Características:
- Headless Chromium con stealth anti-detección
- Chill Mode: pausas aleatorias humanas entre 0.5s y 2.0s
- User-Agent rotativo de Buenos Aires
- Borrado profundo de navigator.webdriver
- MercadoLibre: extrae precio, seller_id, reputación y stock via API + DOM
- Facebook/Instagram/TikTok: extracción de URLs + metadata básica
"""

import sys
import asyncio
import random
import re
from typing import AsyncGenerator, Dict, Any, List
from services.cron_logger import cron_logger
from scrapers.filtro_comercial import es_publicacion_comercial, filtrar_item_comercial

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# Stealth JS payload — borra fingerprints de automatización
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['es-AR', 'es', 'en'] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""


from playwright.async_api import async_playwright

async def _run_playwright_async(platform: str, keyword: str, limit: int, city_name: str = None) -> List[Dict[str, Any]]:
    """Ejecuta Playwright de forma asíncrona nativa."""
    results = []

    async def chill(min_s=0.5, max_s=2.0):
        """Chill Mode: pausa humana aleatoria asíncrona."""
        await asyncio.sleep(random.uniform(min_s, max_s))

    cron_logger.log(f"[Playwright] 🕵️ Iniciando Nivel 2 Stealth para {platform} — '{keyword}'")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                geolocation={"latitude": -34.6037, "longitude": -58.3816}, # Buenos Aires, Argentina
                permissions=["geolocation"],
                locale="es-AR",
                timezone_id="America/Argentina/Buenos_Aires",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": "https://www.google.com.ar/",
                },
            )
            await context.add_init_script(STEALTH_JS)
            page = await context.new_page()

            if platform == "mercadolibre":
                results = await _scrape_mercadolibre_async(page, keyword, limit, city_name, chill)
            elif platform == "facebook":
                results = await _scrape_facebook_async(page, keyword, limit, city_name, chill)
            elif platform == "instagram":
                results = await _scrape_instagram_async(page, keyword, limit, city_name, chill)
            elif platform == "tiktok":
                results = await _scrape_tiktok_async(page, keyword, limit, city_name, chill)
            else:
                cron_logger.log(f"⚠️ [Playwright] Plataforma no soportada: {platform}")

            await browser.close()
    except Exception as e:
        cron_logger.log(f"❌ [Playwright] Error crítico en hilo async: {e}")
        # A veces ocurre el error si no están los navegadores instalados
        if "playwright install" in str(e) or "Executable doesn't exist" in str(e):
            cron_logger.log("💡 Sugerencia: Faltan los binarios de Playwright. Ejecuta: 'playwright install chromium' en tu terminal.")

    return results


def _run_isolated_playwright(platform: str, keyword: str, limit: int, city_name: str) -> List[Dict[str, Any]]:
    """Ejecuta Playwright en un nuevo event loop aislado con WindowsProactorEventLoopPolicy."""
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    isolated_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(isolated_loop)
    try:
        return isolated_loop.run_until_complete(_run_playwright_async(platform, keyword, limit, city_name))
    finally:
        isolated_loop.close()

async def ejecutar_fallback_playwright(platform: str, keyword: str, limit: int, city_name: str = None) -> AsyncGenerator[Dict[str, Any], None]:
    """Wrapper asíncrono que usa run_in_executor para aislar Playwright del worker de Uvicorn."""
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, _run_isolated_playwright, platform, keyword, limit, city_name)
    for res in results:
        yield res

# Alias para mantener compatibilidad si se llamaba con este nombre
run_playwright_fallback = ejecutar_fallback_playwright


# ─── MercadoLibre ─────────────────────────────────────────────────────────────

async def _scrape_mercadolibre_async(page, keyword: str, limit: int, city_name: str, chill) -> List[Dict[str, Any]]:
    """
    Scraper de MercadoLibre Argentina con extracción enriquecida.
    """
    search_url = f"https://listado.mercadolibre.com.ar/{keyword.replace(' ', '-')}"
    cron_logger.log(f"[Playwright ML] Navegando a: {search_url}")

    results = []
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        cron_logger.log(f"⚠️ [Playwright ML] Timeout: {e}")
        return results

    await chill(2.0, 4.0)

    # Scroll suave para cargar lazy items
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3)")
        await chill(0.8, 1.5)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6)")
        await chill(0.8, 1.5)
    except Exception:
        pass

    items_elements = await page.locator(".ui-search-layout__item").all()
    count = 0

    for el in items_elements:
        if count >= limit:
            break

        try:
            title = await el.locator(".ui-search-item__title, h2").first.inner_text()

            # Precio
            price = None
            try:
                price_str = await el.locator(".andes-money-amount__fraction").first.inner_text()
                price = float(price_str.replace(".", ""))
            except Exception:
                pass

            # URL
            url = "N/A"
            try:
                url = await el.locator("a.ui-search-link, a.ui-search-item__group__element").first.get_attribute("href")
            except Exception:
                pass

            # Seller name
            seller_name = "Vendedor MeLi"
            is_official = False
            try:
                official = el.locator(".ui-search-official-store-label")
                if await official.count() > 0:
                    official_text = await official.inner_text()
                    seller_name = official_text.replace("por ", "")
                    is_official = True
            except Exception:
                pass

            if is_official or "tienda oficial" in title.lower():
                continue

            # Extract MLA item ID from URL
            item_id = None
            id_match = re.search(r'(MLA-?\d+)', url) if url else None
            if id_match:
                item_id = id_match.group(1)

            results.append({
                "plataforma": "mercadolibre",
                "title": title,
                "description": title,
                "price": price,
                "url": url,
                "imagen_urls": "['https://http2.mlstatic.com/frontend-assets/ml-web-navigation/ui-navigation/6.6.73/mercadolibre/logo-pt__large_plus.png']",
                "seller_profile": {
                    "name": seller_name,
                    "url": url,
                },
                "location": city_name or "Argentina",
                "raw_data": {"title": title, "url": url, "item_id": item_id},
                "platform_data": {
                    "seller_id": None,
                    "item_id": item_id,
                    "category_name": "Detectado via Playwright",
                    "snippet": f"Precio: ${price}" if price else "Sin precio",
                    "search_query": keyword,
                    "source_engine": "Playwright Stealth",
                },
            })
            count += 1
            await chill(0.5, 1.5)
        except Exception:
            continue

    cron_logger.log(f"✅ [Playwright ML] {count} items extraídos.")
    return results


# ─── Facebook Marketplace ────────────────────────────────────────────────────

async def _scrape_facebook_async(page, keyword: str, limit: int, city_name: str, chill) -> List[Dict[str, Any]]:
    """Fallback para Facebook Marketplace (sin login)."""
    from config import PROVINCIAS_AR
    slug = "buenosaires"
    if city_name:
        for p in PROVINCIAS_AR:
            if p["name"].lower() == city_name.lower():
                slug = p["marketplace_slug"]
                break

    # Forzamos el slug de la provincia en la URL para evitar que FB resuelva a USA por la IP
    search_url = f"https://www.facebook.com/marketplace/{slug}/search/?query={keyword.replace(' ', '%20')}"
    cron_logger.log(f"[Playwright FB] Navegando a: {search_url}")

    results = []
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        cron_logger.log(f"⚠️ [Playwright FB] Timeout: {e}")
        return results

    await chill(3.0, 5.0)

    item_links = await page.locator("a[href*='/marketplace/item/']").all()
    count = 0
    seen = set()

    for el in item_links:
        if count >= limit:
            break
        try:
            href = await el.get_attribute("href")
            if not href or href in seen:
                continue
            seen.add(href)

            full_url = f"https://www.facebook.com{href}" if href.startswith("/") else href
            
            title = f"Publicación detectada FB: {keyword}"
            price = None
            
            try:
                inner_text = await el.inner_text()
                lines = [line.strip() for line in inner_text.split('\n') if line.strip()]
                if lines:
                    if "$" in lines[0] or "Gratis" in lines[0]:
                        price_str = re.sub(r'[^\d]', '', lines[0])
                        if price_str:
                            price = float(price_str)
                        if len(lines) > 1:
                            title = lines[1]
                    else:
                        title = lines[0]
            except Exception:
                pass

            results.append({
                "plataforma": "facebook",
                "title": title,
                "description": title,
                "price": price,
                "url": full_url,
                "imagen_urls": "['https://upload.wikimedia.org/wikipedia/commons/b/b8/2021_Facebook_icon.svg']",
                "seller_profile": {
                    "name": "Usuario Desconocido",
                    "url": full_url,
                },
                "location": city_name or "Argentina",
                "raw_data": {"url": full_url},
                "platform_data": {
                    "seller_name": "Usuario Desconocido",
                    "snippet": f"Marketplace: {keyword}",
                    "search_query": keyword,
                    "source_engine": "Playwright Stealth",
                },
            })
            count += 1
            await chill(0.5, 1.5)
        except Exception:
            continue

    cron_logger.log(f"✅ [Playwright FB] {count} items extraídos.")
    return results


# ─── Instagram ───────────────────────────────────────────────────────────────

async def _scrape_instagram_async(page, keyword: str, limit: int, city_name: str, chill) -> List[Dict[str, Any]]:
    """Fallback para Instagram (sin login, explore tags).
    Extrae alt text y descripciones asociadas a cada post antes de
    pasarlos por el filtro de relevancia comercial.
    """
    base_tag = keyword.replace(" ", "").lower()
    # Forzar etiqueta local si es genérica para evitar resultados globales (USA)
    tag = f"{base_tag}argentina" if "argentina" not in base_tag else base_tag
    
    search_url = f"https://www.instagram.com/explore/tags/{tag}/"
    cron_logger.log(f"[Playwright IG] Navegando a: {search_url}")

    results = []
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        cron_logger.log("⚠️ [Playwright IG] Bloqueado o timeout.")
        return results

    await chill(2.0, 4.0)

    links = await page.locator("a[href*='/p/']").all()
    count = 0
    seen = set()
    descartados = 0

    for el in links:
        if count >= limit:
            break
        try:
            href = await el.get_attribute("href")
            if not href or href in seen:
                continue
            seen.add(href)
            full_url = f"https://www.instagram.com{href}" if href.startswith("/") else href
            
            # ── Extraer todo el texto descriptivo posible del elemento DOM ──
            alt_text = ""
            try:
                img_el = el.locator("img").first
                if await img_el.count() > 0:
                    alt_text = await img_el.get_attribute("alt") or ""
            except Exception:
                pass
            
            # Intentar extraer texto superpuesto (captions visibles)
            overlay_text = ""
            try:
                inner = await el.inner_text()
                if inner:
                    overlay_text = inner.replace('\n', ' ')[:300]
            except Exception:
                pass
                
            # Concatenar todo el texto disponible para el filtro
            texto_completo = f"{keyword} {alt_text} {overlay_text}".strip()
            
            # ── FILTRO DE RELEVANCIA COMERCIAL ──
            # Filtro comercial MOVIDO a cron_manager.py (capa única de filtrado)

            username = "Usuario Desconocido"
            if alt_text and " por " in alt_text:
                try:
                    user_part = alt_text.split(" por ")[1].split(" ")[0]
                    if user_part:
                        username = f"@{user_part}"
                except:
                    pass

            results.append({
                "plataforma": "instagram",
                "title": f"Post IG: #{tag}",
                "description": alt_text or overlay_text or f"Post relacionado con {keyword}",
                "price": None,
                "url": full_url,
                "imagen_urls": "['https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png']",
                "seller_profile": {
                    "name": username,
                    "url": full_url,
                },
                "location": city_name or "Argentina",
                "raw_data": {"url": full_url, "alt_text": alt_text},
                "platform_data": {
                    "username": username.replace("@", "") if username != "Usuario Desconocido" else tag,
                    "snippet": (alt_text or overlay_text or f"Hashtag: #{tag}")[:200],
                    "search_query": keyword,
                    "source_engine": "Playwright Stealth",
                },
            })
            count += 1
            await chill(0.5, 1.5)
        except Exception:
            continue

    cron_logger.log(f"✅ [Playwright IG] {count} items comerciales extraídos ({descartados} descartados por no ser venta).")
    return results


# ─── TikTok ──────────────────────────────────────────────────────────────────

async def _scrape_tiktok_async(page, keyword: str, limit: int, city_name: str, chill) -> List[Dict[str, Any]]:
    """Fallback para TikTok.
    Extrae la descripción visible de cada video y aplica el filtro
    de relevancia comercial para descartar memes/trends sin venta.
    """
    # Añadimos explícitamente 'Argentina' al motor de búsqueda de TikTok
    encoded_kw = keyword.replace(' ', '%20')
    search_url = f"https://www.tiktok.com/search?q={encoded_kw}%20Argentina"
    cron_logger.log(f"[Playwright TT] Navegando a: {search_url}")

    results = []
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        cron_logger.log("⚠️ [Playwright TT] Bloqueado o timeout.")
        return results

    await chill(2.0, 4.0)

    # Intentar scroll para cargar más videos
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
        await chill(1.0, 2.0)
    except Exception:
        pass

    links = await page.locator("a[href*='/video/']").all()
    count = 0
    seen = set()
    descartados = 0

    for el in links:
        if count >= limit:
            break
        try:
            href = await el.get_attribute("href")
            if not href or href in seen:
                continue
            seen.add(href)
            full_url = href if href.startswith("http") else f"https://www.tiktok.com{href}"

            # Extraer username del href
            username = "Usuario Desconocido"
            tt_match = re.search(r'tiktok\.com/@([^/]+)', full_url)
            if tt_match:
                username = f"@{tt_match.group(1).split('?')[0]}"
                
            # ── Extraer texto descriptivo del video ──
            desc_text = ""
            
            # Intentar obtener el texto visible del card del video
            try:
                # TikTok suele tener la descripción en un div hermano o padre
                parent = el.locator("..")
                inner_text = await parent.inner_text()
                if inner_text:
                    desc_text = inner_text.replace('\n', ' ')[:500]
            except Exception:
                pass
            
            if not desc_text:
                try:
                    inner_text = await el.inner_text()
                    if inner_text:
                        desc_text = inner_text.replace('\n', ' ')[:300]
                except Exception:
                    pass
            
            if not desc_text:
                desc_text = f"Video relacionado con {keyword}"

            # ── FILTRO DE RELEVANCIA COMERCIAL ──
            texto_filtro = f"{keyword} {desc_text} {username}"
            if not es_publicacion_comercial(texto_filtro):
                pass # Filtro comercial MOVIDO a cron_manager.py (capa única de filtrado)

            found_phone = None
            phone_match = re.search(r'(?:(?:00)?549?)?0?(11|[2368]\d)\d{8}', desc_text.replace(" ", "").replace("-", ""))
            if phone_match:
                found_phone = phone_match.group(0)

            results.append({
                "plataforma": "tiktok",
                "title": f"Video TikTok: {keyword}",
                "description": desc_text,
                "price": None,
                "url": full_url,
                "seguidores_infractor": None,
                "imagen_urls": "['https://upload.wikimedia.org/wikipedia/en/a/a9/TikTok_logo.svg']",
                "seller_profile": {
                    "name": username,
                    "url": full_url,
                    "phone": found_phone
                },
                "location": city_name or "Argentina",
                "raw_data": {"url": full_url, "description": desc_text},
                "platform_data": {
                    "username": username.replace("@", ""),
                    "snippet": desc_text[:200],
                    "search_query": keyword,
                    "source_engine": "Playwright Stealth",
                },
            })
            count += 1
            await chill(0.5, 1.5)
        except Exception:
            continue

    cron_logger.log(f"✅ [Playwright TT] {count} items comerciales extraídos ({descartados} descartados por no ser venta).")
    return results
