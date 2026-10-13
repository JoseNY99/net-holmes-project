"""
Scraper Login-Free para TikTok usando Playwright.
Busca hashtags directamente en la web sin login.
"""
import asyncio
import random
from playwright.async_api import async_playwright
from services.cron_logger import cron_logger

async def _scrape_tiktok_async(keyword: str, max_results: int = 10, city_name: str = "Argentina"):
    results = []
    base_hashtag = keyword.strip().replace(" ", "").replace("-", "")
    cron_logger.log(f"[TikTok] Iniciando Playwright (Local). Buscando hashtag #{base_hashtag}...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        # Ocultar webdriver
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        url = f"https://www.tiktok.com/tag/{base_hashtag}"
        
        try:
            cron_logger.log(f"[TikTok] Navegando a URL: {url}")
            await page.goto(url, timeout=60000)
            await asyncio.sleep(random.uniform(4.0, 7.0)) # Chill Mode
            
            # Buscar links que contengan /video/
            links = await page.query_selector_all("a[href*='/video/']")
            cron_logger.log(f"[TikTok] Se encontraron {len(links)} videos en la página. Procesando límite de {max_results}...")
            
            for count, link in enumerate(links[:max_results], 1):
                try:
                    href = await link.get_attribute("href")
                    # href usually looks like "https://www.tiktok.com/@username/video/123456789"
                    url_evidencia = href if href and href.startswith('http') else f"https://www.tiktok.com{href}"
                    
                    # Extract username from URL if possible
                    import re
                    username_match = re.search(r'@([^/]+)/', url_evidencia)
                    username = username_match.group(1) if username_match else "Desconocido"
                    
                    results.append({
                        "plataforma": "tiktok",
                        "titular_cuenta": username,
                        "producto_catalogo": keyword,
                        "url_evidencia": url_evidencia,
                        "descripcion_post": f"Video bajo hashtag #{base_hashtag}",
                        "seguidores_infractor": None,
                        "platform_data": {
                            "tiktok": {
                                "username": username,
                                "hashtags": f"#{base_hashtag}",
                                "description_full": f"Video bajo hashtag #{base_hashtag}"
                            }
                        }
                    })
                    cron_logger.log(f"[TikTok] 📹 Video extraído ({count}/{max_results}): {url_evidencia}")
                except Exception as e:
                    cron_logger.log(f" [TikTok] Error parseando video: {e}")
                    
            cron_logger.log(f"[TikTok] Extracción exitosa: {len(results)} videos parseados.")
        except Exception as e:
            cron_logger.log(f" [TikTok] Error de scraping general para {keyword}: {e}")
        finally:
            cron_logger.log(f"[TikTok] Cerrando instancia de Chromium...")
            await browser.close()
            
    return results

def scrape_tiktok(keyword: str, max_results: int = 10, city_name: str = "Argentina"):
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_scrape_tiktok_async(keyword, max_results, city_name))
    finally:
        loop.close()

if __name__ == "__main__":
    # Test manual
    res = scrape_tiktok("falsificaciones", 2)
    print(res)
