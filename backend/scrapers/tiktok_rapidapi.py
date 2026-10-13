import datetime
import json
import httpx
from typing import Dict, Any, List
from config import settings
from services.cron_logger import cron_logger
import urllib.parse

class TikTokScraper:
    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host = "tiktok-api23.p.rapidapi.com"

    async def scrape(self, keyword: str, city_name: str = None) -> List[Dict[str, Any]]:
        results_count = 0
        target_city = city_name or settings.DEFAULT_CITY
        query = f"{keyword} {target_city}"
        
        cron_logger.log(f"[TT RapidAPI] Iniciando búsqueda de texto para '{query}' (Límite: {settings.APIFY_MAX_ITEMS} items)")
        
        if not self.api_key:
            cron_logger.log("[TT RapidAPI] ❌ ERROR: Falta RAPIDAPI_KEY.")
            return

        encoded_query = urllib.parse.quote(query)
        url = f"https://{self.host}/api/search/video?keyword={encoded_query}"
        
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.host
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                items = data.get("item_list", [])
                
                if not items:
                    cron_logger.log(f"[TT RapidAPI] ⚠️ No se encontraron resultados o formato inesperado.")
                    return
                    
                for item in items:
                    try:
                        pub_date = None
                        if item.get("createTime"):
                            try:
                                pub_date = datetime.datetime.fromtimestamp(int(item.get("createTime")), tz=datetime.timezone.utc)
                            except:
                                pass
                                
                        if pub_date:
                            now = datetime.datetime.now(datetime.timezone.utc)
                            if (now - pub_date).days > settings.APIFY_MAX_DAYS:
                                continue

                        author = item.get("author", {})
                        seller_profile = {
                            "id": str(author.get("id", "N/A")),
                            "name": str(author.get("nickname", author.get("uniqueId", "Desconocido"))),
                            "url": f"https://www.tiktok.com/@{author.get('uniqueId', '')}" if author.get("uniqueId") else ""
                        }
                        
                        video_data = item.get("video", {})
                        image_urls = []
                        if video_data.get("cover"):
                            image_urls.append(video_data.get("cover"))
                        elif video_data.get("origin_cover"):
                            image_urls.append(video_data.get("origin_cover"))

                        # Asegurar URL de la publicación
                        video_url = f"https://www.tiktok.com/@{author.get('uniqueId')}/video/{item.get('id')}" if author.get('uniqueId') and item.get('id') else "N/A"
                        
                        standardized_item = {
                            "plataforma": "tiktok",
                            "title": str(item.get("desc", "N/A"))[:200],
                            "price": "Consultar",
                            "description": str(item.get("desc", ""))[:3000],
                            "seller_profile": seller_profile,
                            "comments_audit": [],
                            "url": video_url,
                            "image_urls": image_urls,
                            "extraction_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "raw_data": json.dumps(item)[:3000]
                        }
                        
                        results_count += 1
                        yield standardized_item
                        
                        if results_count >= settings.APIFY_MAX_ITEMS:
                            break
                    except Exception as e:
                        cron_logger.log(f"[TT RapidAPI] ⚠️ Item malformado ignorado: {e}")
                        continue
            
            cron_logger.log(f"[TT RapidAPI] ✅ {results_count} items extraídos.")
            
        except httpx.HTTPError as e:
            cron_logger.log(f"[TT RapidAPI] ❌ Error HTTP en ejecución: {e}")
        except Exception as e:
            cron_logger.log(f"[TT RapidAPI] ❌ Error: {e}")
