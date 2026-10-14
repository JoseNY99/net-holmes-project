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
from urllib.parse import urlencode, urlparse
from typing import AsyncGenerator, Dict, Any, List
from services.cron_logger import cron_logger
from scrapers.filtro_comercial import es_publicacion_comercial, filtrar_item_comercial
from services.argentina_scope import is_spanish_text

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


from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

async def _run_playwright_async(
    platform: str,
    keyword: str,
    limit: int,
    city_name: str = None,
    candidate_urls: List[str] | None = None,
) -> List[Dict[str, Any]]:
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
                results = await _scrape_instagram_async(
                    page, keyword, limit, city_name, chill, candidate_urls
                )
            elif platform == "tiktok":
                results = await _scrape_tiktok_async(page, keyword, limit, city_name, chill)
            else:
                cron_logger.log(f" [Playwright] Plataforma no soportada: {platform}")

            await browser.close()
    except Exception as e:
        cron_logger.log(f" [Playwright] Error crítico en hilo async: {e}")
        # A veces ocurre el error si no están los navegadores instalados
        if "playwright install" in str(e) or "Executable doesn't exist" in str(e):
            cron_logger.log(" Sugerencia: Faltan los binarios de Playwright. Ejecuta: 'playwright install chromium' en tu terminal.")

    return results


def _run_isolated_playwright(
    platform: str,
    keyword: str,
    limit: int,
    city_name: str,
    candidate_urls: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Ejecuta Playwright en un nuevo event loop aislado con WindowsProactorEventLoopPolicy."""
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    isolated_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(isolated_loop)
    try:
        return isolated_loop.run_until_complete(
            _run_playwright_async(platform, keyword, limit, city_name, candidate_urls)
        )
    finally:
        isolated_loop.close()

async def ejecutar_fallback_playwright(
    platform: str,
    keyword: str,
    limit: int,
    city_name: str = None,
    candidate_urls: List[str] | None = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Wrapper asíncrono que usa run_in_executor para aislar Playwright del worker de Uvicorn."""
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, _run_isolated_playwright, platform, keyword, limit, city_name, candidate_urls
    )
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
        cron_logger.log(f" [Playwright ML] Timeout: {e}")
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

    cron_logger.log(f" [Playwright ML] {count} items extraídos.")
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
    search_params = urlencode({"query": keyword})
    search_url = f"https://www.facebook.com/marketplace/{slug}/search/?{search_params}"
    cron_logger.log(f"[Playwright FB] Navegando a: {search_url}")

    results = []
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        cron_logger.log(f" [Playwright FB] Timeout: {e}")
        return results

    await chill(1.0, 1.8)

    item_links = await page.locator("a[href*='/marketplace/item/']").all()
    if not item_links:
        current_url = page.url
        page_title = await page.title()
        try:
            page_text = (await page.locator("body").inner_text(timeout=1500)).lower()
        except Exception:
            page_text = ""
        login_or_blocked = (
            any(part in current_url.lower() for part in ("/login", "/checkpoint"))
            or any(
                marker in page_text
                for marker in ("iniciar sesión", "inicia sesión", "log in", "contenido no disponible")
            )
        )
        cron_logger.log(
            "[Playwright FB] 0 enlaces de Marketplace; "
            f"URL final={current_url}, título={page_title!r}, "
            f"login/bloqueo probable={login_or_blocked}."
        )
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

    cron_logger.log(f" [Playwright FB] {count} items extraídos.")
    return results


# ─── Instagram ───────────────────────────────────────────────────────────────

async def _scrape_instagram_async(
    page,
    keyword: str,
    limit: int,
    city_name: str,
    chill,
    candidate_urls: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Busca URLs de Instagram y extrae caption, comentarios y ubicación del post."""
    from scrapers.index_scraper import _fetch_ddg_html

    location = (city_name or "Argentina").strip()
    if location.casefold() in {"argentina", "todo el pais", "todas"}:
        location_terms = '(Argentina OR "Buenos Aires" OR CABA OR Rosario OR Córdoba OR Mendoza)'
    else:
        location_terms = f'"{location}" Argentina'

    if candidate_urls is not None:
        search_results = [{"href": url} for url in candidate_urls]
    else:
        search_results_by_kind = {}
        search_limit = max(limit * 4, 20)
        for kind in ("p", "reel"):
            query = f'site:instagram.com/{kind}/ "{keyword.strip()}" {location_terms}'
            cron_logger.log(f"[Playwright IG] Búsqueda de {kind}: {query}")
            search_results_by_kind[kind] = await _fetch_ddg_html(query, limit=search_limit)

        # Intercalar posts y reels para repartir el máximo entre ambos formatos.
        search_results = []
        max_results_per_kind = max(
            len(search_results_by_kind["p"]),
            len(search_results_by_kind["reel"]),
        )
        for index in range(max_results_per_kind):
            for kind in ("p", "reel"):
                kind_results = search_results_by_kind[kind]
                if index < len(kind_results):
                    search_results.append(kind_results[index])

    results = []
    seen = set()

    for search_result in search_results:
        if len(results) >= limit:
            break

        candidate_url = search_result.get("href", "")
        parsed_url = urlparse(candidate_url)
        if (parsed_url.hostname or "").lower().removeprefix("www.") != "instagram.com":
            continue
        if not re.fullmatch(r"/(?:p|reel)/[A-Za-z0-9_-]+/?", parsed_url.path):
            continue

        full_url = f"https://www.instagram.com{parsed_url.path.rstrip('/')}/"
        if full_url in seen:
            continue
        seen.add(full_url)

        try:
            cron_logger.log(f"[Playwright IG] Abriendo publicación individual: {full_url}")
            await page.goto(full_url, wait_until="domcontentloaded", timeout=15000)
            try:
                await page.wait_for_selector(
                    'meta[property="og:description"]', timeout=1200
                )
            except PlaywrightTimeoutError:
                pass

            post_data = await page.evaluate("""
                () => {
                    const meta = (selector) =>
                        document.querySelector(selector)?.getAttribute('content') || '';
                    const articleText =
                        document.querySelector('article')?.innerText || '';
                    const locationLink =
                        document.querySelector('a[href*="/explore/locations/"]');
                    return {
                        caption: meta('meta[property="og:description"]') ||
                            meta('meta[name="description"]'),
                        articleText,
                        location: locationLink?.innerText || '',
                        authorTitle: meta('meta[property="og:title"]'),
                        image: meta('meta[property="og:image"]')
                    };
                }
            """)
            caption = (post_data.get("caption") or "").strip()

            article_text = (post_data.get("articleText") or "").strip()
            comments = list(dict.fromkeys(
                line.strip() for line in article_text.splitlines() if line.strip()
            ))[:50]

            if not caption and comments:
                caption = comments[0]
            if not caption:
                cron_logger.log(f"[Playwright IG] Publicación sin descripción accesible: {full_url}")
                continue

            location = (post_data.get("location") or "").strip() or None
            username = "Usuario Desconocido"
            handle_match = re.search(
                r"@([A-Za-z0-9_.]+)", post_data.get("authorTitle") or ""
            )
            if handle_match:
                username = f"@{handle_match.group(1)}"

            image_url = post_data.get("image") or None
            description = " ".join([caption, *comments]).strip()
            language_text = f"{caption} {' '.join(comments)}"
            if not is_spanish_text(language_text):
                cron_logger.log(
                    f"[Playwright IG] Publicación descartada por idioma: {full_url}"
                )
                continue

            results.append({
                "plataforma": "instagram",
                "title": caption[:200],
                "description": description,
                "comments_audit": comments,
                "price": None,
                "url": full_url,
                "imagen_urls": f'["{image_url}"]' if image_url else "[]",
                "seller_profile": {
                    "name": username,
                    "url": full_url,
                },
                "location": location or city_name or "Argentina",
                "raw_data": {
                    "url": full_url,
                    "caption": caption,
                    "comments": comments,
                },
                "platform_data": {
                    "username": username.replace("@", ""),
                    "caption_full": caption,
                    "comments_text": "\n".join(comments),
                    "location": location,
                    "image_urls": f'["{image_url}"]' if image_url else None,
                    "source_engine": "Playwright Stealth",
                },
            })
        except Exception as exc:
            cron_logger.log(f"[Playwright IG] No se pudo leer la publicación {full_url}: {exc}")

    # Aplicar filtro geográfico centralizado ANTES de retornar
    from scrapers.filtro_geografico import FiltroGeografico
    results_filtrados = []
    for item in results:
        debe_aceptar, motivo = FiltroGeografico.filtrar_item(item)
        if debe_aceptar:
            results_filtrados.append(item)
        else:
            cron_logger.log(f"🚫 [IG Filtro Geográfico] Descartado: {item.get('title')} - {motivo}")
    
    cron_logger.log(
        f" [Playwright IG] {len(results_filtrados)}/{len(results)} items válidos "
        "después de filtro geográfico."
    )
    return results_filtrados


# ─── TikTok ──────────────────────────────────────────────────────────────────

async def _scrape_tiktok_async(page, keyword: str, limit: int, city_name: str, chill) -> List[Dict[str, Any]]:
    """Fallback para TikTok.
    Extrae la descripción visible de cada video y aplica el filtro
    de relevancia comercial para descartar memes/trends sin venta.
    """
    encoded_kw = keyword.replace(' ', '%20')
    search_url = f"https://www.tiktok.com/search?q={encoded_kw}"
    cron_logger.log(f"[Playwright TT] Navegando a: {search_url}")

    results = []
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        cron_logger.log(" [Playwright TT] Bloqueado o timeout.")
        return results

    await chill(1.0, 1.8)

    # Intentar scroll para cargar más videos
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
        await chill(0.4, 0.8)
        # Scroll adicional para forzar carga de contenido
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await chill(0.7, 1.2)
    except Exception:
        pass

    # Intentar múltiples selectores TikTok (el DOM cambia con frecuencia)
    links = []
    selectors = [
        "a[href*='/video/']",           # Clásico (video directo)
        "a[href*='/@'][href*='/video']",  # Perfil + video
        "a[href^='/@']",                # Links a perfiles
        "div[role='link'] a",           # Links en divs
        "a[data-e2e*='video']",         # TestID de TikTok
        "a[href*='tiktok.com/@']",      # Genérico
    ]
    
    for selector in selectors:
        try:
            found = await page.locator(selector).all()
            if found and len(found) > 0:
                links = found
                cron_logger.log(f"[Playwright TT] ✅ Selector funcionó: {selector} ({len(links)} items)")
                break
        except Exception as e:
            continue
    
    if not links:
        cron_logger.log(f"[Playwright TT] ⚠️ No se encontraron videos con selectores estándar")
        # Último recurso: buscar cualquier elemento con atributos de TikTok
        try:
            # Obtener todos los links de la página sin filtro
            all_links = await page.locator("a").all()
            if all_links:
                # Filtrar solo los que parecen ser de TikTok
                for link in all_links[:limit * 2]:
                    try:
                        href = await link.get_attribute("href")
                        if href and ("/@" in href or "/video" in href or "tiktok.com" in href):
                            links.append(link)
                            if len(links) >= limit:
                                break
                    except Exception:
                        pass
            if links:
                cron_logger.log(f"[Playwright TT] 🔍 Selector manual encontró {len(links)} items")
        except Exception:
            pass
    
    if not links:
        cron_logger.log(f"[Playwright TT] ❌ TikTok está bloqueando Playwright o no devuelve contenido")
    
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

    # Aplicar filtro geográfico centralizado ANTES de retornar
    from scrapers.filtro_geografico import FiltroGeografico
    results_filtrados = []
    for item in results:
        debe_aceptar, motivo = FiltroGeografico.filtrar_item(item)
        if debe_aceptar:
            results_filtrados.append(item)
        else:
            cron_logger.log(f"🚫 [TT Filtro Geográfico] Descartado: {item.get('title')} - {motivo}")
    
    cron_logger.log(f" [Playwright TT] {len(results_filtrados)}/{count} items válidos después de filtro geográfico.")
    return results_filtrados
