"""
Orquestador de Scraping Híbrido en Cascada de 3 Niveles.

Flujo:
  Nivel 1 → DuckDuckGo OSINT (index_scraper.py)     — Gratuito
  Nivel 2 → Playwright Headless Stealth (playwright_fallback.py) — Gratuito
  Nivel 3 → Apify Cloud API (facebook_apify, tiktok_apify, etc.) — Pago, oculto por defecto

Reglas:
  - Si Nivel 1 retorna ≥ min_threshold resultados → FIN (no se baja al Nivel 2)
  - Si Nivel 1 retorna 0 → Nivel 2 automáticamente
  - Si Nivel 2 falla o 0 resultados y USE_APIFY=True → Nivel 3
  - Volumen controlado: 5 a 50 registros por plataforma
"""

import os
from typing import AsyncGenerator, Dict, Any
from urllib.parse import urlsplit, urlunsplit

from config import settings
from services.cron_logger import cron_logger

# Nivel 1: OSINT Index Scraper
from scrapers.index_scraper import ejecutar_motor_indexado

# Nivel 2: Playwright Stealth Fallback
from scrapers.playwright_fallback import run_playwright_fallback

# Nivel 3: Apify Cloud (oculto por defecto)
from scrapers.facebook_apify import FacebookApifyScraper
from scrapers.instagram_scraper import InstagramApifyScraper
from scrapers.tiktok_apify import TikTokApifyScraper
from scrapers.mercadolibre import MercadoLibreScraper

# Suite OSINT Enterprise: Google Serper + MeLi Developers + Certstream
from scrapers.serper_google_scraper import SerperGoogleScraper
from scrapers.mercadolibre_dev_scraper import MercadoLibreDevScraper
from scrapers.certstream_scanner import CertstreamScanner


# Umbral mínimo de resultados para considerar un nivel exitoso
MIN_THRESHOLD = 20


class ScraperEngine:
    """Motor de scraping con arquitectura de cascada de 3 niveles y suite OSINT."""

    def __init__(self):
        # Instancias de Apify (Nivel 3) — se mantienen cableadas pero apagadas
        self.fb_apify = FacebookApifyScraper()
        self.ig_apify = InstagramApifyScraper()
        self.tt_apify = TikTokApifyScraper()
        self.ml_scraper = MercadoLibreScraper()
        
        # Instancias Suite OSINT Enterprise
        self.serper_scraper = SerperGoogleScraper()
        self.meli_dev = MercadoLibreDevScraper()
        self.certstream = CertstreamScanner()

    # ─── Nivel 3: Apify Cloud (Backup Invisible) ─────────────────────────────

    async def _run_apify_premium(
        self, platform: str, keyword: str, city_name: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecuta el escáner Premium de Apify directamente usando el motor Apify."""
        if not settings.APIFY_API_TOKEN:
            cron_logger.log(
                f" [Apify Cloud] Error: Falta APIFY_API_TOKEN en .env. "
                f"No se puede ejecutar Apify para {platform}."
            )
            return

        cron_logger.log(
            f"💎 [Apify Cloud] Ejecutando escáner Apify para {platform} ('{keyword}')."
        )

        from scrapers.apify_motor import ApifyMotorFase2
        motor = ApifyMotorFase2()
        
        limit = settings.APIFY_MAX_ITEMS
        locs = [city_name] if city_name else []
        async for item in motor.execute(keyword, [platform], locs, limit):
            yield item

    async def _run_rapidapi(
        self, platform: str, keyword: str, city_name: str | None, limit: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Motor RapidAPI — usa scrapers de terceros vía RapidAPI key."""
        if not settings.RAPIDAPI_KEY:
            cron_logger.log(
                f" [RapidAPI] Error: Falta RAPIDAPI_KEY en .env. "
                f"No se puede ejecutar RapidAPI para {platform}."
            )
            return

        cron_logger.log(f"🔑 [RapidAPI] Ejecutando Motor RapidAPI para {platform} ('{keyword}').")
        
        try:
            count = 0
            if platform == "facebook":
                from scrapers.facebook_rapidapi import FacebookRapidAPIScraper
                scraper = FacebookRapidAPIScraper()
                async for item in scraper.scrape(keyword, city_name=city_name):
                    yield item
                    count += 1
                    if count >= limit:
                        break
            elif platform == "instagram":
                from scrapers.instagram_rapidapi import InstagramRapidAPIScraper
                scraper = InstagramRapidAPIScraper()
                async for item in scraper.scrape(keyword, city_name=city_name):
                    yield item
                    count += 1
                    if count >= limit:
                        break
            elif platform == "tiktok":
                from scrapers.tiktok_rapidapi import TikTokRapidAPIScraper
                scraper = TikTokRapidAPIScraper()
                async for item in scraper.scrape(keyword, city_name=city_name):
                    yield item
                    count += 1
                    if count >= limit:
                        break
            elif platform == "mercadolibre":
                async for item in self._scrape_mercadolibre_api(keyword, limit, city_name):
                    yield item
                    count += 1
                    if count >= limit:
                        break
            
            cron_logger.log(f" [RapidAPI] {platform}: {count} resultados obtenidos.")
        except Exception as e:
            cron_logger.log(f" [RapidAPI] Error en {platform}: {e}.")

    async def _scrape_mercadolibre_api(
        self, keyword: str, limit: int, city_name: str | None = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Consulta directa y rápida a la API Oficial Pública de Mercado Libre Argentina (MLA)."""
        import httpx
        import urllib.parse
        try:
            api_url = f"https://api.mercadolibre.com/sites/MLA/search?q={urllib.parse.quote(keyword)}&limit={limit}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(api_url)
                response.raise_for_status()
                data = response.json()
                items = data.get("results", [])
                cron_logger.log(f"[API ML Oficial] Se encontraron {len(items)} items para '{keyword}'.")

                for api_item in items:
                    seller = api_item.get("seller", {})
                    seller_id = str(seller.get("id", "Desconocido"))
                    precio = float(api_item.get("price", 0.0))
                    title = api_item.get("title", "Desconocido")
                    url_pub = api_item.get("permalink", "")

                    yield {
                        "plataforma": "mercadolibre",
                        "title": title,
                        "description": title,
                        "price": precio,
                        "url": url_pub.split("#")[0] if url_pub else "",
                        "imagen_urls": f'["{api_item.get("thumbnail", "")}"]',
                        "seller_profile": {
                            "name": f"Seller ID: {seller_id}",
                            "url": url_pub,
                        },
                        "location": city_name or "Argentina",
                        "raw_data": api_item,
                        "platform_data": {
                            "seller_id": seller_id,
                            "item_id": api_item.get("id"),
                            "category_name": api_item.get("category_id", "Desconocida"),
                            "available_stock": api_item.get("available_quantity"),
                            "sold_quantity": api_item.get("sold_quantity"),
                            "item_condition": api_item.get("condition"),
                            "image_urls": f'["{api_item.get("thumbnail", "")}"]',
                            "snippet": f"API ML — Precio: ${precio}",
                            "search_query": keyword,
                            "source_engine": "MercadoLibre API Pública",
                        },
                    }
        except Exception as e:
            cron_logger.log(f" [API ML Oficial] Error consultando API de MercadoLibre: {e}")

    # ─── Cascada Genérica (Modo Gratuito/Local) ──────────────────────────────

    async def _cascade(
        self,
        platform: str,
        keyword: str,
        limit: int,
        city_name: str | None,
        exclude_urls: set[str] | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Ejecuta el modo Local/Gratuito (DuckDuckGo OSINT + Playwright).
        NO invoca Apify ni RapidAPI.
        """
        collected = []
        seen_urls = set(exclude_urls or ())

        if platform == "instagram":
            indexed_items = []
            async for item in ejecutar_motor_indexado(platform, keyword, limit * 3, city_name):
                url_key = self._item_url_key(item)
                if url_key and url_key in seen_urls:
                    continue
                if url_key:
                    seen_urls.add(url_key)
                indexed_items.append(item)

            candidate_urls = [
                str(item.get("url"))
                for item in indexed_items
                if item.get("url")
            ]
            cron_logger.log(
                f"[Local/Instagram] Extrayendo publicaciones desde {len(candidate_urls)} URLs indexadas."
            )
            async for item in run_playwright_fallback(
                "instagram",
                keyword,
                limit,
                city_name,
                candidate_urls=candidate_urls,
            ):
                url_key = self._item_url_key(item)
                if url_key:
                    seen_urls.add(url_key)
                collected.append(item)
                yield item
                if len(collected) >= limit:
                    return

            remaining = limit - len(collected)
            if remaining:
                async for item in run_playwright_fallback(
                    "instagram", keyword, remaining, city_name
                ):
                    url_key = self._item_url_key(item)
                    if url_key and url_key in seen_urls:
                        continue
                    if url_key:
                        seen_urls.add(url_key)
                    collected.append(item)
                    yield item
                    if len(collected) >= limit:
                        break
            return

        # ── NIVEL 1: DuckDuckGo OSINT ──
        cron_logger.log(f" [Local/DDG] Nivel 1: DuckDuckGo OSINT para {platform} ")
        async for item in ejecutar_motor_indexado(platform, keyword, limit, city_name):
            url_key = self._item_url_key(item)
            if url_key and url_key in seen_urls:
                continue
            if url_key:
                seen_urls.add(url_key)
            collected.append(item)
            yield item
            if len(collected) >= limit:
                break

        if len(collected) >= limit:
            cron_logger.log(
                f" [Local/DDG] Nivel 1 completado: {len(collected)} resultados."
            )
            return

        # ── NIVEL 2: Playwright Stealth ──
        cron_logger.log(f" [Local/Playwright] Nivel 2: Playwright Stealth para {platform} ")
        remaining = limit - len(collected)
        async for item in run_playwright_fallback(platform, keyword, remaining, city_name):
            url_key = self._item_url_key(item)
            if url_key and url_key in seen_urls:
                continue
            if url_key:
                seen_urls.add(url_key)
            collected.append(item)
            yield item
            if len(collected) >= limit:
                break

    @staticmethod
    def _item_url_key(item: Dict[str, Any]) -> str:
        url = str(item.get("url") or "").strip()
        if not url:
            return ""
        parsed = urlsplit(url)
        hostname = parsed.netloc.lower()
        for prefix in ("www.", "m.", "l."):
            if hostname.startswith(prefix):
                hostname = hostname[len(prefix):]
        return urlunsplit(
            (parsed.scheme.lower(), hostname, parsed.path.rstrip("/"), "", "")
        )

    async def _scrape_social_with_fallback(
        self,
        platform: str,
        keyword: str,
        city_name: str | None,
        limit: int,
        exclude_urls: set[str] | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Usa Serper primero y completa desde motores gratuitos, omitiendo URLs conocidas."""
        collected = 0
        seen_urls = set(exclude_urls or ())

        if platform == "instagram":
            candidate_items = []
            try:
                async for item in self.serper_scraper.scrape(
                    platform, keyword, limit * 3, city_name
                ):
                    url_key = self._item_url_key(item)
                    if url_key and url_key in seen_urls:
                        continue
                    if url_key:
                        seen_urls.add(url_key)
                    candidate_items.append(item)
            except Exception as exc:
                cron_logger.log(
                    f"[Instagram] Serper no disponible para '{keyword}': {exc}. "
                    "Se buscarán URLs con DDG gratuito."
                )

            candidate_urls = [
                str(item.get("url"))
                for item in candidate_items
                if item.get("url")
            ]
            if candidate_urls:
                cron_logger.log(
                    f"[Instagram] Abriendo {len(candidate_urls)} URLs de Serper/DDG "
                    "para extraer caption, comentarios e idioma."
                )
                async for item in run_playwright_fallback(
                    "instagram",
                    keyword,
                    limit,
                    city_name,
                    candidate_urls=candidate_urls,
                ):
                    url_key = self._item_url_key(item)
                    if url_key:
                        if url_key in (exclude_urls or set()):
                            continue
                        seen_urls.add(url_key)
                    yield item
                    collected += 1
                    if collected >= limit:
                        return

            remaining = limit - collected
            if remaining:
                cron_logger.log(
                    f"[Instagram] Fallback gratuito local; faltan {remaining} de {limit}."
                )
                async for item in self._cascade(
                    "instagram",
                    keyword,
                    remaining,
                    city_name,
                    exclude_urls=seen_urls,
                ):
                    url_key = self._item_url_key(item)
                    if url_key and url_key in seen_urls:
                        continue
                    if url_key:
                        seen_urls.add(url_key)
                    yield item
                    collected += 1
                    if collected >= limit:
                        break
            cron_logger.log(f"[Instagram] Resultados extraídos: {collected}/{limit}.")
            return

        instagram_kind_counts = {"p": 0, "reel": 0}

        try:
            async for item in self.serper_scraper.scrape(platform, keyword, limit * 3, city_name):
                url_key = self._item_url_key(item)
                if url_key and url_key in seen_urls:
                    continue
                if url_key:
                    seen_urls.add(url_key)
                yield item
                collected += 1
                if collected >= limit:
                    cron_logger.log(
                        f"[{platform}] Límite alcanzado con Serper/DDG: {collected}/{limit}."
                    )
                    return
        except Exception as exc:
            cron_logger.log(
                f"[{platform}] Serper no disponible para '{keyword}': {exc}. "
                "Continuando con DDG/Playwright gratuitos."
            )

        remaining = limit - collected
        if remaining <= 0:
            return

        cron_logger.log(
            f"[{platform}] Completando resultados con motores gratuitos: "
            f"faltan {remaining} de {limit}."
        )
        try:
            async for item in self._cascade(
                platform, keyword, remaining, city_name, exclude_urls=seen_urls
            ):
                url_key = self._item_url_key(item)
                if url_key and url_key in seen_urls:
                    continue
                if url_key:
                    seen_urls.add(url_key)
                yield item
                collected += 1
                if collected >= limit:
                    break
        except Exception as exc:
            cron_logger.log(
                f"[{platform}] Falló también el fallback gratuito para '{keyword}': {exc}"
            )

        cron_logger.log(f"[{platform}] Resultados reunidos: {collected}/{limit}.")

    # ─── Métodos Públicos por Plataforma ─────────────────────────────────────

    async def scrape_facebook(
        self,
        keyword: str,
        city_name: str = None,
        proveedor: str = "playwright",
        exclude_urls: set[str] | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        limit = settings.APIFY_MAX_ITEMS
        seen_urls = set(exclude_urls or ())
        source = None
        if proveedor == "apify":
            source = self._run_apify_premium("facebook", keyword, city_name)
        elif proveedor == "rapidapi":
            source = self._run_rapidapi("facebook", keyword, city_name, limit)
        elif proveedor == "google_meli_osint":
            async for item in self._scrape_social_with_fallback(
                "facebook", keyword, city_name, limit, seen_urls
            ):
                yield item
            return
        else:
            source = self._cascade(
                "facebook", keyword, limit, city_name, exclude_urls=seen_urls
            )

        collected = 0
        async for item in source:
            key = self._item_url_key(item)
            if key and key in seen_urls:
                continue
            if key:
                seen_urls.add(key)
            yield item
            collected += 1

        if proveedor != "google_meli_osint" and collected < limit:
            remaining = limit - collected
            cron_logger.log(
                f"[Facebook] Proveedor entregó {collected}/{limit}; "
                f"completando {remaining} desde búsqueda gratuita."
            )
            async for item in self._cascade(
                "facebook", keyword, remaining, city_name, exclude_urls=seen_urls
            ):
                key = self._item_url_key(item)
                if key and key in seen_urls:
                    continue
                if key:
                    seen_urls.add(key)
                yield item

    async def scrape_instagram(
        self,
        keyword: str,
        city_name: str = None,
        proveedor: str = "playwright",
        exclude_urls: set[str] | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        limit = settings.APIFY_MAX_ITEMS
        collected_count = 0
        seen_urls = set(exclude_urls or ())

        # Intentar con el proveedor configurado
        if proveedor == "apify":
            try:
                async for item in self._run_apify_premium("instagram", keyword, city_name):
                    key = self._item_url_key(item)
                    if key and key in seen_urls:
                        continue
                    if key:
                        seen_urls.add(key)
                    collected_count += 1
                    yield item
            except Exception as exc:
                cron_logger.log(f"[Instagram Apify] Falló: {exc}. Activando motor gratuito.")
        elif proveedor == "rapidapi":
            try:
                async for item in self._run_rapidapi("instagram", keyword, city_name, limit):
                    key = self._item_url_key(item)
                    if key and key in seen_urls:
                        continue
                    if key:
                        seen_urls.add(key)
                    collected_count += 1
                    yield item
            except Exception as exc:
                cron_logger.log(f"[Instagram RapidAPI] Falló: {exc}. Activando motor gratuito.")
        elif proveedor == "google_meli_osint":
            async for item in self._scrape_social_with_fallback(
                "instagram", keyword, city_name, limit, seen_urls
            ):
                yield item
            return

        if collected_count < limit:
            remaining = limit - collected_count
            cron_logger.log(
                f"[Instagram] Proveedor entregó {collected_count}/{limit}; "
                f"completando {remaining} desde DDG/Playwright."
            )
            async for item in self._cascade(
                "instagram", keyword, remaining, city_name, exclude_urls=seen_urls
            ):
                yield item

    async def scrape_tiktok(
        self,
        keyword: str,
        city_name: str = None,
        proveedor: str = "playwright",
        exclude_urls: set[str] | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        limit = settings.APIFY_MAX_ITEMS
        collected_count = 0
        seen_urls = set(exclude_urls or ())

        # Intentar con el proveedor configurado
        if proveedor == "apify":
            try:
                async for item in self._run_apify_premium("tiktok", keyword, city_name):
                    key = self._item_url_key(item)
                    if key and key in seen_urls:
                        continue
                    if key:
                        seen_urls.add(key)
                    collected_count += 1
                    yield item
            except Exception as exc:
                cron_logger.log(f"[TikTok Apify] Falló: {exc}. Activando motor gratuito.")
        elif proveedor == "rapidapi":
            try:
                async for item in self._run_rapidapi("tiktok", keyword, city_name, limit):
                    key = self._item_url_key(item)
                    if key and key in seen_urls:
                        continue
                    if key:
                        seen_urls.add(key)
                    collected_count += 1
                    yield item
            except Exception as exc:
                cron_logger.log(f"[TikTok RapidAPI] Falló: {exc}. Activando motor gratuito.")
        elif proveedor == "google_meli_osint":
            async for item in self._scrape_social_with_fallback(
                "tiktok", keyword, city_name, limit, seen_urls
            ):
                yield item
            return

        if collected_count < limit:
            remaining = limit - collected_count
            cron_logger.log(
                f"[TikTok] Proveedor entregó {collected_count}/{limit}; "
                f"completando {remaining} desde DDG/Playwright."
            )
            async for item in self._cascade(
                "tiktok", keyword, remaining, city_name, exclude_urls=seen_urls
            ):
                yield item

    async def scrape_mercadolibre(
        self, keyword: str, city_name: str = None, proveedor: str = "playwright"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Para MercadoLibre (Argentina):
        - google_meli_osint: Consulta la API oficial de Desarrolladores de MeLi (con fallback a DDG).
        - apify/rapidapi: Intenta con el proveedor, cae a local
        - playwright / local: Utiliza el motor de indexación DuckDuckGo OSINT y Playwright como fallback.
        """
        limit = settings.APIFY_MAX_ITEMS
        collected = []
        
        # Intentar con proveedor configurado
        if proveedor == "apify":
            try:
                cron_logger.log(f" [MercadoLibre Apify] Buscando '{keyword}'...")
                async for item in self._run_apify_premium("mercadolibre", keyword, city_name):
                    collected.append(item)
                    yield item
            except Exception as e:
                cron_logger.log(f"  [MercadoLibre Apify] Fallo: {e}")
        elif proveedor == "rapidapi":
            try:
                cron_logger.log(f" [MercadoLibre RapidAPI] Buscando '{keyword}'...")
                async for item in self._run_rapidapi("mercadolibre", keyword, city_name, limit):
                    collected.append(item)
                    yield item
            except Exception as e:
                cron_logger.log(f"  [MercadoLibre RapidAPI] Fallo: {e}")
        elif proveedor == "google_meli_osint":
            try:
                cron_logger.log(f" [MercadoLibre Developers API] Buscando '{keyword}'...")
                async for item in self.meli_dev.scrape(keyword, limit, city_name):
                    collected.append(item)
                    yield item
            except Exception as e:
                cron_logger.log(f"  [MercadoLibre API] Fallo: {e}")
        
        # Si se obtuvieron pocos resultados, complementar con DuckDuckGo + Playwright
        if len(collected) < limit:
            cron_logger.log(f" [MercadoLibre OSINT] Complementando con DuckDuckGo + Playwright (obtenidos: {len(collected)}, falta: {limit - len(collected)})...")
            async for item in ejecutar_motor_indexado("mercadolibre", keyword, limit, city_name):
                collected.append(item)
                yield item
                if len(collected) >= limit:
                    break

            # Si aún faltan items, usar Playwright Stealth
            if len(collected) < limit:
                cron_logger.log(" [MercadoLibre] Playwright Stealth Fallback ")
                async for item in run_playwright_fallback("mercadolibre", keyword, limit, city_name):
                    collected.append(item)
                    yield item
                    if len(collected) >= limit:
                        break
        
        cron_logger.log(f" [MercadoLibre] {len(collected)} publicaciones encontradas.")

    async def scan_certstream_domains(
        self, brand_name: str, limit: int = 5
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Escanea dominios SSL de phishing y tiendas falsas para la marca."""
        async for item in self.certstream.scan_brand_domains(brand_name, limit):
            yield item
