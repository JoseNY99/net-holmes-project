import asyncio
import httpx
from services.cron_logger import cron_logger

class MercadoLibreScraper:
    def __init__(self):
        pass

    async def scrape(self, keyword: str, city_name: str = None, max_results: int = 100):
        # API de MercadoLibre no bloquea para consultas públicas
        results = await _scrape_mercadolibre_async(keyword, max_results, city_name)
        for res in results:
            yield res

async def _scrape_mercadolibre_async(keyword: str, max_results: int = 10, city_name: str = "Argentina"):
    """
    Usa la API pública de Mercado Libre (Sin token).
    Extremadamente rápida y precisa.
    """
    results = []
    cron_logger.log(f"[MercadoLibre] Iniciando API Request. Buscando '{keyword}' (max {max_results} res)...")
    
    import urllib.parse
    query = urllib.parse.urlencode({"q": keyword.strip(), "limit": max_results})
    url = f"https://api.mercadolibre.com/sites/MLA/search?{query}"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("results", [])
            cron_logger.log(f"[MercadoLibre] Se encontraron {len(items)} items en la API. Procesando...")
            
            for item in items:
                try:
                    seller_id = str(item.get("seller", {}).get("id", "Desconocido"))
                    seller_nickname = item.get("seller", {}).get("nickname")
                    
                    if not seller_nickname and seller_id != "Desconocido":
                        try:
                            user_url = f"https://api.mercadolibre.com/users/{seller_id}"
                            user_response = await client.get(user_url)
                            if user_response.status_code == 200:
                                seller_nickname = user_response.json().get("nickname")
                        except Exception as e:
                            pass
                            
                    seller_name = seller_nickname or f"Seller ID: {seller_id}"
                    
                    seller_reputation = item.get("seller", {}).get("seller_reputation", {}).get("level_id", "")
                    sold_quantity = item.get("sold_quantity", 0)
                    
                    precio = float(item.get("price", 0.0))
                    title = item.get("title", "Desconocido")
                    url_pub = item.get("permalink", "")
                    
                    results.append({
                        "plataforma": "mercadolibre",
                        "titular_cuenta": seller_name,
                        "producto_catalogo": keyword,
                        "url_evidencia": url_pub.split('#')[0] if url_pub else "",
                        "precio_publico": precio,
                        "descripcion_post": title,
                        "seller_profile": {
                            "name": seller_name,
                            "url": f"https://perfil.mercadolibre.com.ar/{seller_name}" if seller_nickname else ""
                        },
                        "platform_data": {
                            "seller_id": seller_id,
                            "seller_reputation": seller_reputation,
                            "sold_quantity": sold_quantity,
                            "item_id": item.get("id"),
                            "post_date": item.get("stop_time"), 
                            "category_name": item.get("category_id", "Desconocida"),
                            "image_urls": f'["{item.get("thumbnail", "")}"]'
                        }
                    })
                except Exception as e:
                    cron_logger.log(f" [MercadoLibre] Error parseando item {item.get('id')}: {e}")
                    continue
                    
            cron_logger.log(f"[MercadoLibre] Extracción exitosa: {len(results)} items parseados.")
    except Exception as e:
        cron_logger.log(f" [MercadoLibre] Error de scraping API para {keyword}: {e}")
        
    return results

def scrape_mercadolibre(keyword: str, max_results: int = 10, city_name: str = "Argentina"):
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_scrape_mercadolibre_async(keyword, max_results, city_name))
    finally:
        loop.close()

if __name__ == "__main__":
    res = scrape_mercadolibre("zapatillas nike falsas", 2)
    print(res)
