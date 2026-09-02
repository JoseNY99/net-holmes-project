import datetime
import json
import asyncio
from typing import Dict, Any, List
from apify_client import ApifyClientAsync
from config import settings
from services.cron_logger import cron_logger

class TikTokApifyScraper:
    def __init__(self):
        self.actor_id = settings.APIFY_ACTOR_TT

    def _get_client(self):
        from services.api_key_service import get_active_api_key
        token = get_active_api_key("apify") or settings.APIFY_API_TOKEN
        if not token:
            return None
        return ApifyClientAsync(token=token)

    async def scrape(self, keyword: str, city_name: str = None):
        results_count = 0
        target_city = city_name or settings.DEFAULT_CITY
        query = f"{keyword} {target_city}"
        
        cron_logger.log(f"[TT Apify] Iniciando búsqueda para '{query}' (Límite: {settings.APIFY_MAX_ITEMS} items)")
        
        client = self._get_client()
        if not client:
            cron_logger.log("[TT Apify] ❌ ERROR: Falta APIFY_API_TOKEN en DB o .env.")
            return

        fetch_limit = max(settings.APIFY_MAX_ITEMS * 2, 6)
        run_input = {
            "searchQueries": [query],
            "resultsPerPage": fetch_limit,
            "resultsLimit": fetch_limit,
            "shouldDownloadVideos": False,
            "proxy": {"useApifyProxy": True},
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": settings.DEFAULT_PROXY_COUNTRY
            }
        }
        
        timeout_val = 45.0 if settings.APIFY_MAX_ITEMS <= 5 else (30.0 + (settings.APIFY_MAX_ITEMS * 3.0))
        
        try:
            run = await asyncio.wait_for(
                client.actor(self.actor_id).call(run_input=run_input),
                timeout=timeout_val
            )
            
            async for item in client.dataset(run.default_dataset_id).iterate_items():
                try:
                    pub_date = None
                    if item.get("createTimeISO"):
                        try:
                            pub_date = datetime.datetime.fromisoformat(str(item.get("createTimeISO")).replace("Z", "+00:00"))
                        except:
                            pass
                            
                    if pub_date:
                        now = datetime.datetime.now(datetime.timezone.utc)
                        if (now - pub_date).days > settings.APIFY_MAX_DAYS:
                            continue

                    author = item.get("authorMeta") or item.get("author") or {}
                    author_name = str(author.get("uniqueId") or author.get("name") or author.get("nickname") or "Desconocido")
                    author_url = author.get("profileUrl") or (f"https://www.tiktok.com/@{author_name}" if author_name != "Desconocido" else "")
                    
                    seller_profile = {
                        "id": str(author.get("id", "N/A")),
                        "name": author_name,
                        "url": author_url,
                        "followers": author.get("fans") or author.get("followers")
                    }
                    
                    # Extraer portada/thumbnail real del video
                    covers = item.get("covers") or (item.get("video") or {}).get("covers") or {}
                    video_dict = item.get("video") or {}
                    video_meta = item.get("videoMeta") or {}
                    
                    cover_img = (
                        covers.get("default") or 
                        covers.get("origin") or 
                        covers.get("dynamic") or 
                        video_dict.get("cover") or 
                        video_dict.get("originCover") or 
                        video_meta.get("coverUrl") or 
                        item.get("coverUrl") or 
                        item.get("imageUrl") or 
                        ""
                    )
                    image_urls = [cover_img] if cover_img and isinstance(cover_img, str) and cover_img.startswith("http") else []
                    
                    video_id = str(item.get("id") or item.get("videoId") or "")
                    video_url = (
                        item.get("webVideoUrl") or 
                        item.get("videoUrl") or 
                        item.get("url") or 
                        (f"https://www.tiktok.com/@{author_name}/video/{video_id}" if video_id and author_name != "Desconocido" else "N/A")
                    )
                    
                    standardized_item = {
                        "plataforma": "tiktok",
                        "title": str(item.get("text", "Video TikTok"))[:200],
                        "price": "Consultar",
                        "description": str(item.get("text", ""))[:3000],
                        "seller_profile": seller_profile,
                        "comments_audit": [],
                        "url": video_url,
                        "image_urls": image_urls,
                        "extraction_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "raw_data": json.dumps(item)[:3000],
                        "platform_data": {
                            "username": author_name,
                            "video_id": video_id,
                            "video_views": item.get("playCount") or (item.get("stats") or {}).get("playCount"),
                            "likes": item.get("diggCount") or (item.get("stats") or {}).get("diggCount"),
                            "shares": item.get("shareCount") or (item.get("stats") or {}).get("shareCount"),
                            "comments_count": item.get("commentCount") or (item.get("stats") or {}).get("commentCount"),
                            "followers": author.get("fans") or author.get("followers"),
                            "hashtags": json.dumps([h.get("name", "") if isinstance(h, dict) else str(h) for h in item.get("hashtags", [])]) if item.get("hashtags") else None,
                            "description_full": str(item.get("text", ""))[:3000],
                            "image_urls": json.dumps(image_urls) if image_urls else None,
                            "source_engine": "Apify_Premium",
                        }
                    }
                    
                    results_count += 1
                    yield standardized_item
                    
                    if results_count >= settings.APIFY_MAX_ITEMS:
                        break
                except Exception as e:
                    cron_logger.log(f"[TT Apify] ⚠️ Item malformado ignorado: {e}")
                    continue
            
            cron_logger.log(f"[TT Apify] ✅ {results_count} items extraídos.")
            
        except Exception as e:
            cron_logger.log(f"[TT Apify] ❌ Error: {e}")
            raise e
