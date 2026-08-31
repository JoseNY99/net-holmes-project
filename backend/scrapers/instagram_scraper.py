"""
Scraper Login-Free para Instagram usando Playwright (local) y Apify (cloud).
Busca hashtags directamente en la web sin login.
Extrae username, followers, teléfono y email de cada perfil detectado.
"""
import asyncio
import re
import random
import datetime
import json
from playwright.async_api import async_playwright
from apify_client import ApifyClientAsync
from services.cron_logger import cron_logger
from config import settings

class InstagramApifyScraper:
    def __init__(self):
        self.client = ApifyClientAsync(token=settings.APIFY_API_TOKEN)
        self.actor_id = settings.APIFY_ACTOR_IG  # "apify/instagram-scraper"
        
    async def scrape(self, keyword: str, city_name: str = None):
        """Ejecuta el actor de Apify para Instagram y normaliza los resultados."""
        results_count = 0
        target_city = city_name or settings.DEFAULT_CITY
        
        # Construir hashtag de búsqueda
        hashtag = keyword.strip().replace(" ", "").lower()
        
        cron_logger.log(f"[IG Apify] Iniciando búsqueda para '#{hashtag}' (Límite: {settings.APIFY_MAX_ITEMS} items)")
        
        if not settings.APIFY_API_TOKEN:
            cron_logger.log("[IG Apify] ❌ ERROR: Falta APIFY_API_TOKEN.")
            return

        fetch_limit = max(settings.APIFY_MAX_ITEMS * 2, 5)
        run_input = {
            "directUrls": [f"https://www.instagram.com/explore/tags/{hashtag}/"],
            "hashtags": [hashtag],
            "resultsType": "posts",
            "resultsLimit": fetch_limit,
            "searchLimit": 1,
            "addParentData": True,
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": settings.DEFAULT_PROXY_COUNTRY
            }
        }
        
        timeout_val = 60.0 if settings.APIFY_MAX_ITEMS <= 5 else (45.0 + (settings.APIFY_MAX_ITEMS * 3.0))
        
        try:
            run = await asyncio.wait_for(
                self.client.actor(self.actor_id).call(run_input=run_input),
                timeout=timeout_val
            )
            
            async for item in self.client.dataset(run.default_dataset_id).iterate_items():
                try:
                    # Extraer datos del post
                    caption = item.get("caption", "") or ""
                    owner_username = item.get("ownerUsername", "") or ""
                    # Extraer shortcode e ID del post
                    shortcode = item.get("shortCode") or item.get("shortcode") or item.get("code") or item.get("id") or ""
                    item_url_raw = item.get("url", "") or ""
                    
                    if "/p/" in item_url_raw or "/reel/" in item_url_raw:
                        post_url = item_url_raw
                    elif shortcode and not str(shortcode).startswith("http"):
                        post_url = f"https://www.instagram.com/p/{shortcode}/"
                    elif item_url_raw and "explore/tags" not in item_url_raw:
                        post_url = item_url_raw
                    else:
                        post_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else "N/A"
                    
                    # Fecha de publicación
                    pub_date = None
                    timestamp = item.get("timestamp") or item.get("takenAtTimestamp")
                    if timestamp:
                        try:
                            pub_date = datetime.datetime.fromtimestamp(int(timestamp), tz=datetime.timezone.utc)
                        except:
                            pass
                    
                    # Filtrar por antigüedad
                    if pub_date:
                        now = datetime.datetime.now(datetime.timezone.utc)
                        if (now - pub_date).days > settings.APIFY_MAX_DAYS:
                            continue
                    
                    # Imagen real del post
                    image_url = (
                        item.get("displayUrl") or 
                        item.get("display_url") or 
                        item.get("thumbnail_src") or 
                        item.get("imageUrl") or 
                        item.get("previewUrl") or 
                        ""
                    )
                    image_urls = [image_url] if image_url and image_url.startswith("http") else []
                    
                    # Seguidores del owner
                    followers = item.get("ownerFollowersCount")
                    
                    seller_profile = {
                        "id": str(item.get("ownerId", "N/A")),
                        "name": f"@{owner_username}" if owner_username else "Desconocido",
                        "url": f"https://www.instagram.com/{owner_username}/" if owner_username else "",
                        "followers": followers,
                    }
                    
                    standardized_item = {
                        "plataforma": "instagram",
                        "title": caption[:200] if caption else f"Post IG: #{hashtag}",
                        "price": "Consultar",
                        "description": caption[:3000] if caption else "",
                        "seller_profile": seller_profile,
                        "seguidores_infractor": followers,
                        "comments_audit": [],
                        "url": post_url,
                        "image_urls": image_urls,
                        "extraction_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "raw_data": json.dumps(item)[:3000],
                        "platform_data": {
                            "username": owner_username,
                            "followers": followers,
                            "caption_full": caption[:3000] if caption else "",
                            "hashtags": None,
                            "likes_count": item.get("likesCount"),
                            "comments_count": item.get("commentsCount"),
                            "image_urls": json.dumps(image_urls) if image_urls else None,
                            "post_type": item.get("type", "post"),
                            "source_engine": "Apify_Premium",
                        },
                    }
                    
                    results_count += 1
                    yield standardized_item
                    
                    if results_count >= settings.APIFY_MAX_ITEMS:
                        break
                except Exception as e:
                    cron_logger.log(f"[IG Apify] ⚠️ Item malformado ignorado: {e}")
                    continue
            
            cron_logger.log(f"[IG Apify] ✅ {results_count} items extraídos.")
            
        except Exception as e:
            cron_logger.log(f"[IG Apify] ❌ Error: {e}")
            raise e

async def _extract_ig_profile(page, username, cache):
    """Visita un perfil de IG y extrae followers/phone/email de las meta tags. Cachea resultados."""
    if username in cache:
        return cache[username]
    data = {"followers": None, "phone": None, "email": None, "full_name": None}
    try:
        await page.goto(f"https://www.instagram.com/{username}/", timeout=15000)
        await asyncio.sleep(random.uniform(2.0, 3.5))
        # Meta description: "123 Followers, 45 Following, 67 Posts..."
        meta_desc = await page.evaluate(
            "() => { const el = document.querySelector('meta[name=\"description\"]'); return el ? el.content : ''; }"
        )
        if meta_desc and "Followers" in meta_desc:
            fm = re.search(r'([\d,.]+[kKmM]?)\s*Followers', meta_desc, re.IGNORECASE)
            if fm:
                fstr = fm.group(1).replace(",", "")
                try:
                    if 'k' in fstr.lower():
                        data["followers"] = int(float(fstr.lower().replace('k', '')) * 1000)
                    elif 'm' in fstr.lower():
                        data["followers"] = int(float(fstr.lower().replace('m', '')) * 1000000)
                    else:
                        data["followers"] = int(fstr)
                except:
                    pass
        # og:title: "Nombre (@username) • Instagram..."
        og_title = await page.evaluate(
            "() => { const el = document.querySelector('meta[property=\"og:title\"]'); return el ? el.content : ''; }"
        )
        if og_title:
            nm = re.search(r'^(.+?)\s*\(@', og_title)
            if nm:
                data["full_name"] = nm.group(1).strip()
        # Bio text for phone/email
        try:
            body_text = await page.inner_text("header")
        except:
            body_text = ""
        if body_text:
            pm = re.search(r'(?:tel|phone|whatsapp|cel|wsp|wa\.me/)[:\s/]*[\+]?[\d\s\-\(\)]{8,15}', body_text, re.IGNORECASE)
            if not pm:
                pm = re.search(r'(?:\+?54)?[\s-]?(?:11|\d{2,4})[\s-]?\d{4}[\s-]?\d{4}', body_text)
            if pm:
                data["phone"] = pm.group(0).strip()
            em = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', body_text)
            if em:
                data["email"] = em.group(0)
    except Exception as ex:
        cron_logger.log(f"⚠️ [Instagram] Error leyendo perfil @{username}: {ex}")
    cache[username] = data
    return data

async def _scrape_instagram_async(keyword: str, max_results: int = 10, city_name: str = "Argentina"):
    results = []
    base_hashtag = keyword.strip().replace(" ", "").replace("-", "")
    cron_logger.log(f"[Instagram] Iniciando Playwright (Local). Buscando hashtag #{base_hashtag}...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        # Ocultar webdriver
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        tag_url = f"https://www.instagram.com/explore/tags/{base_hashtag}/"
        
        try:
            cron_logger.log(f"[Instagram] Navegando a URL: {tag_url}")
            await page.goto(tag_url, timeout=60000)
            await asyncio.sleep(random.uniform(4.0, 6.0))  # Chill Mode (Instagram es estricto)
            
            # Buscar links que contengan /p/ (posts)
            links = await page.query_selector_all("a[href*='/p/']")
            cron_logger.log(f"[Instagram] Se encontraron {len(links)} posts en la página. Procesando límite de {max_results}...")
            
            # Recoger URLs primero
            post_urls = []
            for link in links[:max_results]:
                href = await link.get_attribute("href")
                if href:
                    post_urls.append(f"https://www.instagram.com{href}")
            
            # Cache de perfiles ya visitados
            profile_cache = {}
            
            for count, url_evidencia in enumerate(post_urls, 1):
                try:
                    username = None
                    
                    # Visitar post y extraer username del og:title
                    try:
                        await page.goto(url_evidencia, timeout=15000)
                        await asyncio.sleep(random.uniform(2.0, 3.0))
                        
                        og_title = await page.evaluate(
                            "() => { const el = document.querySelector('meta[property=\"og:title\"]'); return el ? el.content : ''; }"
                        )
                        if og_title:
                            # Formato: "Nombre (@username) on Instagram: ..."
                            um = re.search(r'@(\w+)', og_title)
                            if um:
                                username = um.group(1)
                    except Exception:
                        pass
                    
                    # Obtener datos del perfil (followers, phone, email)
                    profile_data = {"followers": None, "phone": None, "email": None, "full_name": None}
                    if username:
                        profile_data = await _extract_ig_profile(page, username, profile_cache)
                    
                    titular = f"@{username}" if username else "Desconocido (Login-Free)"
                    
                    results.append({
                        "plataforma": "instagram",
                        "titular_cuenta": titular,
                        "producto_catalogo": keyword,
                        "url_evidencia": url_evidencia,
                        "descripcion_post": f"Post bajo hashtag #{base_hashtag}",
                        "seguidores_infractor": profile_data.get("followers"),
                        "telefono_publico": profile_data.get("phone"),
                        "seller_profile": {
                            "name": titular,
                            "url": f"https://www.instagram.com/{username}/" if username else "",
                            "followers": profile_data.get("followers"),
                            "phone": profile_data.get("phone"),
                        },
                        "platform_data": {
                            "instagram": {
                                "username": username or "",
                                "hashtags": f"#{base_hashtag}",
                                "post_type": "post",
                                "caption_full": f"Post bajo hashtag #{base_hashtag}",
                                "followers": profile_data.get("followers"),
                                "following": None,
                                "phone": profile_data.get("phone"),
                            }
                        }
                    })
                    cron_logger.log(f"[Instagram] 📸 Post extraído ({count}/{max_results}): {titular} | Followers: {profile_data.get('followers', '?')} | {url_evidencia}")
                except Exception as e:
                    cron_logger.log(f"⚠️ [Instagram] Error parseando post: {e}")
                    
            cron_logger.log(f"[Instagram] Extracción exitosa: {len(results)} posts parseados.")
        except Exception as e:
            cron_logger.log(f"❌ [Instagram] Error de scraping general para {keyword}: {e}")
        finally:
            cron_logger.log(f"[Instagram] Cerrando instancia de Chromium...")
            await browser.close()
            
    return results

def scrape_instagram_rapidapi(keyword: str, max_results: int = 10, city_name: str = "Argentina"):
    # Se mantiene el nombre de la función por retrocompatibilidad con el engine
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_scrape_instagram_async(keyword, max_results, city_name))
    finally:
        loop.close()

if __name__ == "__main__":
    res = scrape_instagram_rapidapi("falsificaciones", 2)
    print(res)
