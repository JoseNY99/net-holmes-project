import json
import urllib.parse
import httpx
from typing import AsyncGenerator, Dict, Any, List
from datetime import datetime, timezone

from config import settings
from services.cron_logger import cron_logger
from services.image_persistence import limpiar_url_canonica

class MercadoLibreDevScraper:
    """
    Scraper oficial de Mercado Libre Argentina para desarrolladores (developers.mercadolibre.com.ar).
    Utiliza autenticación OAuth / Client Credentials para acceder a la API de búsqueda sin bloqueos 403.
    """
    API_SEARCH_URL = "https://api.mercadolibre.com/sites/MLA/search"
    OAUTH_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

    def __init__(self):
        self._cached_token: str | None = None

    async def _get_access_token(self) -> str | None:
        if settings.MERCADOLIBRE_ACCESS_TOKEN:
            return settings.MERCADOLIBRE_ACCESS_TOKEN
        
        if self._cached_token:
            return self._cached_token

        if settings.MERCADOLIBRE_APP_ID and settings.MERCADOLIBRE_CLIENT_SECRET:
            cron_logger.log("🔑 [MeLi Developers] Solicitando token OAuth con Client Credentials...")
            try:
                payload = {
                    "grant_type": "client_credentials",
                    "client_id": settings.MERCADOLIBRE_APP_ID,
                    "client_secret": settings.MERCADOLIBRE_CLIENT_SECRET,
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(self.OAUTH_TOKEN_URL, data=payload)
                    if resp.status_code == 200:
                        token_data = resp.json()
                        self._cached_token = token_data.get("access_token")
                        cron_logger.log("✅ [MeLi Developers] Token OAuth obtenido exitosamente.")
                        return self._cached_token
                    else:
                        cron_logger.log(f"⚠️ [MeLi Developers] Error OAuth ({resp.status_code}): {resp.text}")
            except Exception as e:
                cron_logger.log(f"⚠️ [MeLi Developers] Error obteniendo token: {e}")

        return None

    async def scrape(
        self, keyword: str, limit: int = 10, city_name: str | None = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        cron_logger.log(f"📦 [MeLi Developers API] Buscando publicaciones para '{keyword}' (Límite: {limit})")
        token = await self._get_access_token()
        collected_count = 0

        if token:
            try:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "NetHolmes-BrandDefense/1.0",
                }
                params = {
                    "q": keyword,
                    "limit": min(max(limit * 2, 10), 50),
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(self.API_SEARCH_URL, headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])
                        cron_logger.log(f"✅ [MeLi Developers] {len(results)} publicaciones encontradas en API Oficial.")

                        for item in results:
                            raw_permalink = item.get("permalink", "")
                            clean_url = limpiar_url_canonica(raw_permalink)
                            title = item.get("title", "Publicación Mercado Libre")
                            price = float(item.get("price", 0.0))

                            seller = item.get("seller", {})
                            seller_id = str(seller.get("id", "Desconocido"))
                            seller_nickname = seller.get("nickname") or f"Vendedor {seller_id}"

                            # Extraer imagen en alta resolución
                            thumb_id = item.get("thumbnail_id")
                            if thumb_id:
                                high_res_img = f"https://http2.mlstatic.com/D_NQ_NP_{thumb_id}-O.webp"
                            else:
                                high_res_img = item.get("thumbnail", "")

                            img_urls = [high_res_img] if high_res_img and high_res_img.startswith("http") else []

                            yield {
                                "plataforma": "mercadolibre",
                                "title": title[:200],
                                "description": f"{title} — Stock: {item.get('available_quantity', 1)} — Condición: {item.get('condition', 'N/A')}",
                                "price": price,
                                "url": clean_url,
                                "image_urls": img_urls,
                                "seller_profile": {
                                    "name": seller_nickname,
                                    "url": f"https://www.mercadolibre.com.ar/perfil/{seller_nickname}" if seller_nickname != f"Vendedor {seller_id}" else clean_url,
                                },
                                "location": city_name or "Argentina",
                                "raw_data": json.dumps(item)[:3000],
                                "platform_data": {
                                    "seller_id": seller_id,
                                    "seller_nickname": seller_nickname,
                                    "item_id": item.get("id"),
                                    "category_id": item.get("category_id"),
                                    "category_name": item.get("category_id", "Desconocida"),
                                    "item_condition": item.get("condition"),
                                    "available_stock": item.get("available_quantity"),
                                    "sold_quantity": item.get("sold_quantity"),
                                    "image_urls": json.dumps(img_urls) if img_urls else None,
                                    "source_engine": "MercadoLibre_Developers_API",
                                }
                            }
                            collected_count += 1
                            if collected_count >= limit:
                                return
                    else:
                        cron_logger.log(f"⚠️ [MeLi Developers] Status {resp.status_code}: {resp.text}")
            except Exception as e:
                cron_logger.log(f"⚠️ [MeLi Developers] Error consultando API: {e}")

        # Fallback a DuckDuckGo OSINT si no hay token o falló la API
        if collected_count == 0:
            cron_logger.log("🔄 [MeLi Developers] Sin credenciales de developer o 0 resultados. Usando motor Local OSINT...")
            from scrapers.index_scraper import ejecutar_motor_indexado
            async for item in ejecutar_motor_indexado("mercadolibre", keyword, limit, city_name):
                yield item
