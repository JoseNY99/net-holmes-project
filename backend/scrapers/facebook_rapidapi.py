import datetime
import json
import httpx
from typing import Dict, Any, List
from config import settings
from services.cron_logger import cron_logger
import urllib.parse

class FacebookMarketplaceScraper:
    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host = "facebook-scraper3.p.rapidapi.com"

    async def scrape(self, keyword: str, city_name: str = None) -> List[Dict[str, Any]]:
        results_count = 0
        target_city = city_name or settings.DEFAULT_CITY
        
        cron_logger.log(f"[FB RapidAPI] Iniciando búsqueda para '{keyword}' en {target_city} (Límite: {settings.APIFY_MAX_ITEMS} items)")
        
        if not self.api_key:
            cron_logger.log("[FB RapidAPI]  ERROR: Falta RAPIDAPI_KEY en el entorno.")
            return

        encoded_query = urllib.parse.quote(keyword)
        encoded_city = urllib.parse.quote(target_city)
        
        url = f"https://{self.host}/marketplace/search?query={encoded_query}&city={encoded_city}"
        
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.host
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("results", [])
                if not isinstance(results, list):
                    cron_logger.log(f"[FB RapidAPI]  Formato inesperado. Se esperaba una lista en 'results'.")
                    return
                
                for item in results:
                    try:
                        seller_profile = {
                            "id": "N/A",
                            "name": "Desconocido",
                            "url": ""
                        }
                        
                        image_urls = []
                        if item.get("image") and isinstance(item["image"], dict) and item["image"].get("uri"):
                            image_urls.append(item["image"]["uri"])

                        listing_id = item.get("listing_id")
                        item_url = f"https://www.facebook.com/marketplace/item/{listing_id}" if listing_id else "N/A"

                        title_val = item.get("title") or "N/A"
                        
                        price_obj = item.get("price", {})
                        price_val = price_obj.get("formatted_amount") if isinstance(price_obj, dict) else "Consultar"
                        
                        desc_val = item.get("description", title_val)
                        
                        standardized_item = {
                            "plataforma": "facebook",
                            "title": str(title_val)[:200],
                            "price": str(price_val),
                            "description": str(desc_val)[:3000],
                            "seller_profile": seller_profile,
                            "comments_audit": [],
                            "url": item_url,
                            "image_urls": image_urls,
                            "extraction_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "raw_data": json.dumps(item)[:3000]
                        }
                        
                        results_count += 1
                        yield standardized_item
                        
                        if results_count >= settings.APIFY_MAX_ITEMS:
                            break
                    except Exception as e:
                        cron_logger.log(f"[FB RapidAPI]  Item malformado ignorado: {e}")
                        continue
                
            cron_logger.log(f"[FB RapidAPI]  Búsqueda completada. {results_count} items extraídos.")
            
        except httpx.HTTPError as e:
            cron_logger.log(f"[FB RapidAPI]  Error HTTP en ejecución: {e}")
        except Exception as e:
            cron_logger.log(f"[FB RapidAPI]  Error inesperado: {e}")
