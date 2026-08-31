import datetime
import json
import asyncio
from typing import Dict, Any, List
from apify_client import ApifyClientAsync
from config import settings
from services.cron_logger import cron_logger

class FacebookApifyScraper:
    def __init__(self):
        self.client = ApifyClientAsync(token=settings.APIFY_API_TOKEN)
        self.actor_id = settings.APIFY_ACTOR_FB

    async def scrape(self, keyword: str, city_name: str = None):
        results_count = 0
        target_city = city_name or settings.DEFAULT_CITY
        from config import PROVINCIAS_AR
        
        # Mapear nombre de ciudad a slug oficial de FB Marketplace (ej: 'buenosaires', 'cordoba', 'rosario')
        city_slug = "buenosaires"
        c_lower = (target_city or "").lower().strip()
        for p in PROVINCIAS_AR:
            if p["name"].lower() in c_lower or c_lower in p["name"].lower():
                city_slug = p.get("marketplace_slug", "buenosaires")
                break
        
        cron_logger.log(f"[FB Apify] Iniciando búsqueda para '{keyword}' en Marketplace /{city_slug} (Límite: {settings.APIFY_MAX_ITEMS} items)")
        
        if not settings.APIFY_API_TOKEN:
            cron_logger.log("[FB Apify] ❌ ERROR: Falta APIFY_API_TOKEN.")
            return

        import urllib.parse
        encoded_kw = urllib.parse.quote(keyword)
        marketplace_url = f"https://www.facebook.com/marketplace/{city_slug}/search?daysSince=30&query={encoded_kw}"
        fetch_limit = max(settings.APIFY_MAX_ITEMS * 2, 5)
        run_input = {
            "searchQuery": keyword,
            "location": city_slug,
            "startUrls": [{"url": marketplace_url}],
            "maxItems": fetch_limit,
            "resultsLimit": fetch_limit,
            "shouldDownloadVideos": False,
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": settings.DEFAULT_PROXY_COUNTRY
            }
        }
        
        timeout_val = 45.0 if settings.APIFY_MAX_ITEMS <= 5 else (30.0 + (settings.APIFY_MAX_ITEMS * 3.0))
        
        try:
            run = await asyncio.wait_for(
                self.client.actor(self.actor_id).call(run_input=run_input),
                timeout=timeout_val
            )
            
            async for item in self.client.dataset(run.default_dataset_id).iterate_items():
                try:
                    # Extraer ID y URL real del anuncio
                    item_id = str(item.get("id") or item.get("listingId") or item.get("itemId") or "").strip()
                    item_url = (
                        item.get("listingUrl") or 
                        item.get("url") or 
                        item.get("link") or 
                        item.get("marketplaceUrl") or 
                        (f"https://www.facebook.com/marketplace/item/{item_id}/" if item_id else "N/A")
                    )

                    # Extraer imagen real del producto
                    raw_img = (
                        item.get("imageUrl") or 
                        item.get("image") or 
                        item.get("primaryImage") or 
                        item.get("thumbnail") or
                        item.get("photo") or
                        item.get("coverImage")
                    )
                    if not raw_img:
                        imgs = item.get("images") or item.get("photos") or []
                        if isinstance(imgs, list) and len(imgs) > 0:
                            first_img = imgs[0]
                            raw_img = first_img if isinstance(first_img, str) else (first_img.get("url") or first_img.get("src") or first_img.get("image"))

                    image_urls = [raw_img] if raw_img and isinstance(raw_img, str) and raw_img.startswith("http") else []

                    # Titular y vendedor
                    seller_raw = item.get("seller") or item.get("sellerProfile") or {}
                    seller_name = (
                        item.get("sellerName") or 
                        (seller_raw.get("name") if isinstance(seller_raw, dict) else str(seller_raw)) or 
                        "Desconocido"
                    )
                    seller_url = (
                        item.get("sellerUrl") or 
                        (seller_raw.get("url") if isinstance(seller_raw, dict) else "") or 
                        ""
                    )

                    seller_profile = {
                        "id": item_id or "N/A",
                        "name": seller_name,
                        "url": seller_url
                    }

                    title_val = item.get("title") or item.get("listingTitle") or item.get("name") or "Publicación Marketplace"
                    price_val = item.get("price") or item.get("listingPrice") or item.get("formattedPrice") or "Consultar"
                    desc_val = item.get("description") or title_val
                    
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
                        "raw_data": json.dumps(item)[:3000],
                        "platform_data": {
                            "seller_name": seller_name,
                            "seller_profile_url": seller_url,
                            "seller_location_city": item.get("location", {}).get("city") if isinstance(item.get("location"), dict) else (item.get("location") if isinstance(item.get("location"), str) else None),
                            "seller_location_province": item.get("location", {}).get("state") if isinstance(item.get("location"), dict) else None,
                            "listing_id": item_id,
                            "marketplace_category": item.get("category", None),
                            "item_condition": item.get("condition", None),
                            "image_urls": json.dumps(image_urls) if image_urls else None,
                            "source_engine": "Apify_Premium",
                        }
                    }
                    
                    results_count += 1
                    yield standardized_item
                    
                    if results_count >= settings.APIFY_MAX_ITEMS:
                        break
                except Exception as e:
                    cron_logger.log(f"[FB Apify] ⚠️ Item malformado ignorado: {e}")
                    continue
            
            cron_logger.log(f"[FB Apify] ✅ {results_count} items extraídos.")
            
        except Exception as e:
            cron_logger.log(f"[FB Apify] ❌ Error: {e}")
            raise e
