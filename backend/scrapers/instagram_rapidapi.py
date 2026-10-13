import datetime
import json
import httpx
import re
import urllib.parse
from typing import Dict, Any, AsyncGenerator

from config import settings
from services.cron_logger import cron_logger

class InstagramRapidAPIScraper:
    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host = "instagram-scraper-api2.p.rapidapi.com"

    async def scrape(self, keyword: str, city_name: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        results_count = 0
        target_city = city_name or "Argentina"
        
        cron_logger.log(f"[IG RapidAPI] Iniciando búsqueda para hashtag '{keyword}' en {target_city} (Límite: {settings.APIFY_MAX_ITEMS} items)")
        
        from services.api_key_service import get_active_api_key
        api_key = get_active_api_key("rapidapi") or self.api_key

        if not api_key:
            cron_logger.log("[IG RapidAPI]  ERROR: Falta RAPIDAPI_KEY en DB o entorno.")
            return

        # Removing # if present in keyword
        clean_keyword = keyword.replace("#", "")
        encoded_query = urllib.parse.quote(clean_keyword)
        
        url = f"https://{self.host}/v1/hashtag?hashtag={encoded_query}"
        
        headers = {
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": self.host
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # Check different API structures for items
                items = data.get("data", {}).get("items", [])
                
                if not items and isinstance(data.get("items"), list):
                    items = data.get("items")
                elif not items and isinstance(data.get("data"), list):
                    items = data.get("data")
                
                if not items:
                    cron_logger.log(f"[IG RapidAPI]  No se encontraron resultados o formato inesperado.")
                    return
                
                for item in items:
                    try:
                        # Fallback structures for instagram posts
                        node = item.get("node") or item
                        
                        caption_node = node.get("edge_media_to_caption", {}).get("edges", [])
                        caption = ""
                        if caption_node and len(caption_node) > 0:
                            caption = caption_node[0].get("node", {}).get("text", "")
                        elif node.get("caption"):
                            if isinstance(node["caption"], dict):
                                caption = node["caption"].get("text", "")
                            else:
                                caption = str(node.get("caption", ""))
                                
                        shortcode = node.get("shortcode") or node.get("code") or "N/A"
                        
                        owner = node.get("owner") or node.get("user") or {}
                        username = owner.get("username", "desconocido")
                        follower_count = owner.get("edge_followed_by", {}).get("count") or owner.get("follower_count")
                        
                        # Extract price and hashtags
                        extracted_hashtags = re.findall(r'#\w+', caption)
                        
                        price_match = re.search(r'\$\s?([\d\.]+(?:,[\d]{2})?)', caption)
                        extracted_price = price_match.group(0) if price_match else None
                        
                        thumbnail_url = node.get("display_url") or node.get("thumbnail_src") or node.get("image_versions2", {}).get("candidates", [{}])[0].get("url")
                        
                        like_count = node.get("edge_media_preview_like", {}).get("count") or node.get("edge_liked_by", {}).get("count") or node.get("like_count")
                        comment_count = node.get("edge_media_to_comment", {}).get("count") or node.get("comment_count")
                        
                        is_video = node.get("is_video") or node.get("media_type") == 2
                        media_type = "video" if is_video else "image"
                        
                        standardized_item = {
                            "plataforma": "instagram",
                            "title": caption[:100] if caption else "",
                            "description": caption,
                            "price": extracted_price,
                            "url": f"https://www.instagram.com/p/{shortcode}/",
                            "image_urls": [thumbnail_url] if thumbnail_url else [],
                            "seller_profile": {
                                "name": f"@{username}",
                                "url": f"https://www.instagram.com/{username}/",
                                "followers": follower_count,
                            },
                            "location": target_city,
                            "platform_data": {
                                "username": username,
                                "followers": follower_count,
                                "bio_text": None,
                                "image_urls": json.dumps([thumbnail_url]) if thumbnail_url else None,
                                "likes_count": like_count,
                                "comments_count": comment_count,
                                "caption_full": caption,
                                "post_type": media_type,
                                "hashtags": json.dumps(extracted_hashtags),
                                "source_engine": "RapidAPI_Instagram",
                            },
                        }
                        
                        results_count += 1
                        yield standardized_item
                        
                        if results_count >= settings.APIFY_MAX_ITEMS:
                            break
                    except Exception as e:
                        cron_logger.log(f"[IG RapidAPI]  Item malformado ignorado: {e}")
                        continue
                        
                cron_logger.log(f"[IG RapidAPI]  Búsqueda completada. {results_count} items extraídos.")
                
        except httpx.HTTPError as e:
            cron_logger.log(f"[IG RapidAPI]  Error HTTP en ejecución: {e}")
        except Exception as e:
            cron_logger.log(f"[IG RapidAPI]  Error inesperado: {e}")
