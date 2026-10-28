import re
import json
import asyncio
from typing import AsyncGenerator, Dict, Any, List
import httpx

from config import settings
from services.cron_logger import cron_logger
from services.image_persistence import limpiar_url_canonica

_SERPER_DISABLED = False


class SerperGoogleScraper:
    SERPER_ENDPOINT = "https://google.serper.dev/search"
    GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    def _build_dork(self, platform: str, keyword: str, city_name: str = None) -> str:
        kw = keyword.strip()
        loc = (city_name or "Argentina").strip()
        # Keep queries as plain words: Serper's free plan rejects advanced
        # operators such as site:, grouped ORs, and quoted phrase combinations.
        fake_terms = "replica G5 AAA clon calidad premium tailandesa importadas premium"
        common_terms = f"{kw} {loc} Argentina {fake_terms}"
        if platform == "facebook":
            return f"{common_terms} Facebook Marketplace"
        elif platform == "instagram":
            return f"{common_terms} Instagram publicación reel"
        elif platform == "tiktok":
            return f"{common_terms} TikTok video"
        return f"{kw} Argentina {loc}"

    async def scrape(self, platform: str, keyword: str, limit: int = 10, city_name: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        dork = self._build_dork(platform, keyword, city_name)
        cron_logger.log(f"🌐 [Google/Serper OSINT] Buscando para {platform} ({keyword}): {dork}")
        collected = 0

        global _SERPER_DISABLED

        from services.api_key_service import get_active_api_key
        serper_key = get_active_api_key("serper")
        if _SERPER_DISABLED:
            serper_key = None
        if serper_key:
            cron_logger.log("🔑 [Serper.dev] Ejecutando Google Dorking via Serper API...")
            try:
                headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
                payload = {"q": dork, "gl": "ar", "hl": "es-419", "num": min(max(limit * 2, 10), 50)}
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(self.SERPER_ENDPOINT, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        total_organic = len(data.get("organic", []))
                        cron_logger.log(f"✅ [Serper.dev] Respuesta OK - {total_organic} resultados encontrados")
                        for item in data.get("organic", []):
                            raw_link = item.get("link", "")
                            clean_link = limpiar_url_canonica(raw_link)
                            if not self._is_valid_direct_link(platform, clean_link):
                                continue
                            title = item.get("title", "Publicación detectada")
                            snippet = item.get("snippet", "")
                            thumbnail = item.get("imageUrl") or (item.get("thumbnail") if isinstance(item.get("thumbnail"), str) else None)
                            
                            # Enriquecer metadatos en vivo (username, likes, etc.)
                            meta_extra = self._enrich_metadata(platform, clean_link, title, snippet)
                            seller_name = meta_extra.get("username") or self._extract_seller_name(platform, clean_link, title, snippet)
                            price_val = self._extract_price(snippet)
                            followers_val = self._extract_followers(f"{title} {snippet}")
                            location_val = self._extract_location(f"{title} {snippet}", city_name)
                            phone_val = self._extract_phone(f"{title} {snippet}")
                            likes_val = meta_extra.get("likes")

                            img_urls = [thumbnail] if thumbnail and thumbnail.startswith("http") else []
                            yield {
                                "plataforma": platform,
                                "title": title[:200],
                                "description": snippet[:3000],
                                "price": price_val,
                                "url": clean_link,
                                "image_urls": img_urls,
                                "seller_profile": {"name": seller_name, "url": clean_link, "followers": followers_val},
                                "seguidores_infractor": followers_val,
                                "location": location_val,
                                "phone": phone_val,
                                "raw_data": json.dumps(item)[:3000],
                                "platform_data": {
                                    "username": seller_name if platform in ("instagram", "tiktok") else None,
                                    "seller_name": seller_name if platform == "facebook" else None,
                                    "followers": followers_val,
                                    "location": location_val,
                                    "phone": phone_val,
                                    "caption_full": snippet[:3000],
                                    "description_full": snippet[:3000],
                                    "image_urls": json.dumps(img_urls) if img_urls else None,
                                    "source_engine": "Google_Serper_OSINT",
                                }
                            }
                            collected += 1
                            if collected >= limit:
                                return
                    else:
                        response_text = resp.text
                        response_text_lower = response_text.lower()
                        if any(
                            marker in response_text_lower
                            for marker in (
                                "not enough credits",
                                "insufficient credits",
                                "query pattern not allowed",
                            )
                        ):
                            _SERPER_DISABLED = True
                            cron_logger.log(
                                "⚠️ [Serper.dev] La cuenta rechazó la consulta por créditos "
                                "insuficientes o restricción del plan; se deja de llamar "
                                "Serper en este proceso."
                            )
                        else:
                            cron_logger.log(
                                f"⚠️ [Serper.dev] Status {resp.status_code}: {response_text}"
                            )
            except Exception as e:
                cron_logger.log(f"⚠️ [Serper.dev] Error: {e}")

        elif settings.GOOGLE_CSE_API_KEY and settings.GOOGLE_CSE_CX:
            cron_logger.log("🔑 [Google CSE] Ejecutando consulta via Google Custom Search...")
            try:
                params = {"key": settings.GOOGLE_CSE_API_KEY, "cx": settings.GOOGLE_CSE_CX, "q": dork, "gl": "ar", "lr": "lang_es", "num": min(limit, 10)}
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(self.GOOGLE_CSE_ENDPOINT, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data.get("items", []):
                            raw_link = item.get("link", "")
                            clean_link = limpiar_url_canonica(raw_link)
                            if not self._is_valid_direct_link(platform, clean_link):
                                continue
                            title = item.get("title", "Publicación detectada")
                            snippet = item.get("snippet", "")
                            pagemap = item.get("pagemap", {})
                            cse_thumb = None
                            if pagemap.get("cse_thumbnail"):
                                cse_thumb = pagemap["cse_thumbnail"][0].get("src")
                            elif pagemap.get("cse_image"):
                                cse_thumb = pagemap["cse_image"][0].get("src")
                            seller_name = self._extract_seller_name(platform, clean_link, title, snippet)
                            price_val = self._extract_price(snippet)
                            followers_val = self._extract_followers(f"{title} {snippet}")
                            location_val = self._extract_location(f"{title} {snippet}", city_name)
                            phone_val = self._extract_phone(f"{title} {snippet}")
                            img_urls = [cse_thumb] if cse_thumb and cse_thumb.startswith("http") else []
                            yield {
                                "plataforma": platform,
                                "title": title[:200],
                                "description": snippet[:3000],
                                "price": price_val,
                                "url": clean_link,
                                "image_urls": img_urls,
                                "seller_profile": {"name": seller_name, "url": clean_link, "followers": followers_val},
                                "seguidores_infractor": followers_val,
                                "location": location_val,
                                "phone": phone_val,
                                "raw_data": json.dumps(item)[:3000],
                                "platform_data": {
                                    "username": seller_name if platform in ("instagram", "tiktok") else None,
                                    "seller_name": seller_name if platform == "facebook" else None,
                                    "followers": followers_val,
                                    "location": location_val,
                                    "phone": phone_val,
                                    "caption_full": snippet[:3000],
                                    "description_full": snippet[:3000],
                                    "image_urls": json.dumps(img_urls) if img_urls else None,
                                    "source_engine": "Google_CSE_OSINT",
                                }
                            }
                            collected += 1
                            if collected >= limit:
                                return
            except Exception as e:
                cron_logger.log(f"⚠️ [Google CSE] Error: {e}")

    def _is_valid_direct_link(self, platform: str, url: str) -> bool:
        if not url or not url.startswith("http"):
            return False
        u = url.lower()
        if platform == "facebook":
            return "/marketplace/item/" in u or "/posts/" in u
        elif platform == "instagram":
            return "/p/" in u or "/reel/" in u
        elif platform == "tiktok":
            # Rechazar URLs incompletas como "https://www.tiktok.com/@"
            if u.endswith("/@") or "/@/" in u:
                return False
            if "vt.tiktok.com/" in u:
                return True
            m = re.search(r'tiktok\.com/@([A-Za-z0-9_.-]+)/(?:video|photo)/\d+', u)
            if m:
                u_name = m.group(1).lower()
                if u_name in ("about", "legal", "nav", "us", "wiki", "explore", "tag", "channel", "discover", "live", "login", "signup", "foryou", "privacy", "community", "support"):
                    return False
                return True
            return False
        return True

    def _extract_seller_name(self, platform: str, url: str, title: str, snippet: str) -> str:
        if platform == "instagram":
            from services.listing_fields import extract_instagram_author
            author = extract_instagram_author(title, snippet)
            if author:
                return author
            # 1. Buscar en formato @username
            m = re.search(r'(@[A-Za-z0-9_.]+)', f"{title} {snippet}")
            if m:
                return m.group(1)
            # 2. Formato 'Name (@user) on Instagram'
            m_title = re.search(r'([A-Za-z0-9_.]+) on Instagram', title, re.IGNORECASE)
            if m_title:
                return f"@{m_title.group(1)}"
            # 3. Formato 'Foto de User en Instagram' o 'User (@user)'
            m_user = re.search(r'\((@[A-Za-z0-9_.]+)\)', title)
            if m_user:
                return m_user.group(1)
        elif platform == "tiktok":
            m = re.search(r'tiktok\.com/@([A-Za-z0-9_.-]+)', url)
            if m:
                u_name = m.group(1)
                if u_name.lower() not in ("about", "legal", "nav", "us", "wiki", "explore", "tag", "channel", "discover", "live", "login", "signup", "foryou", "privacy", "community", "support"):
                    return f"@{u_name}" if not u_name.startswith("@") else u_name
            m_tt = re.search(r'(@[A-Za-z0-9_.]{3,30})', f"{title} {snippet}")
            if m_tt:
                u_cand = m_tt.group(1)
                if u_cand.lower().replace("@", "") not in ("about", "legal", "nav", "us", "wiki", "explore", "tag", "channel", "discover", "live", "login", "signup", "foryou", "privacy", "community", "support"):
                    return u_cand
            return "@vendedor_tiktok"
        elif platform == "facebook":
            from services.listing_fields import extract_facebook_author
            author = extract_facebook_author({}, title, snippet)
            if author:
                return author
            # Marketplace listings often expose the seller in the indexed snippet.
            m_fb = re.search(
                r"(?:vendido por|publicado por|vendedor|seller|contacto)\s*:?\s*"
                r"([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúñÑ.'-]*"
                r"(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúñÑ.'-]*){0,3})",
                f"{title} {snippet}",
                re.IGNORECASE,
            )
            if m_fb:
                return m_fb.group(1).strip()
            profile_match = re.search(r"facebook\.com/([^/?#]+)", url, re.IGNORECASE)
            if profile_match and profile_match.group(1).lower() not in {
                "marketplace", "groups", "watch", "events", "share", "login",
            }:
                return f"@{profile_match.group(1)}"
            return "Vendedor No Identificado"
        return "Vendedor No Identificado"

    def _extract_followers(self, text: str) -> int | None:
        if not text:
            return None
        m = re.search(r'([\d.,]+)\s*([kKmM])?\s*(?:followers|seguidores)', text, re.IGNORECASE)
        if m:
            num_str = m.group(1).replace(",", ".")
            multiplier = m.group(2)
            try:
                val = float(num_str)
                if multiplier:
                    if multiplier.lower() == 'k':
                        val *= 1000
                    elif multiplier.lower() == 'm':
                        val *= 1000000
                return int(val)
            except Exception:
                return None
        return None

    def _extract_location(self, text: str, default_city: str = None) -> str:
        if not text:
            return default_city or "Argentina"
        locations = [
            'Flores', 'Once', 'Palermo', 'Avellaneda', 'Lomas de Zamora', 'San Justo',
            'Morón', 'Quilmes', 'Lanús', 'San Martín', 'Belgrano', 'Caballito', 'Villa Urquiza',
            'CABA', 'Buenos Aires', 'Córdoba', 'Cordoba', 'Rosario', 'Mendoza',
            'La Plata', 'Mar del Plata', 'Salta', 'Tucumán', 'Santa Fe', 'Neuquén',
            'Bahía Blanca', 'Corrientes', 'Posadas', 'Resistencia', 'San Juan', 'San Luis'
        ]
        for loc in locations:
            if re.search(r'\b' + re.escape(loc) + r'\b', text, re.IGNORECASE):
                return f"{loc}, Argentina" if loc != "Argentina" else loc
        return default_city or "Argentina"

    def _extract_phone(self, text: str) -> str | None:
        if not text:
            return None
        # Buscar patrones de WhatsApp / teléfono
        clean_text = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        m = re.search(r'(?:(?:00)?549?)?0?(11|[2368]\d)\d{8}', clean_text)
        if m:
            return m.group(0)
        return None

    def _extract_price(self, text: str) -> str:
        match = re.search(r'\$\s?([\d.,]+)', text)
        if match:
            raw = match.group(1).replace(".", "").replace(",", ".")
            try:
                float(raw)
                return raw
            except Exception:
                pass
        return "Consultar"

    def _enrich_metadata(self, platform: str, url: str, title: str, snippet: str) -> dict:
        """Enriquece metadatos en vivo (username @, likes, autor) consultando OpenGraph."""
        enriched = {}
        if platform == "instagram":
            try:
                from curl_cffi import requests
                from bs4 import BeautifulSoup
                res = requests.get(url, impersonate="chrome120", timeout=6)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    og_title = soup.find("meta", property="og:title")
                    og_desc = soup.find("meta", property="og:description")
                    t_text = og_title.get("content") if og_title else ""
                    d_text = og_desc.get("content") if og_desc else ""
                    
                    m_user = re.search(r'-\s+([A-Za-z0-9_.]+)\s+on\s+', d_text)
                    if m_user:
                        enriched["username"] = f"@{m_user.group(1)}"
                    elif " on Instagram" in t_text:
                        m_t = re.search(r'([A-Za-z0-9_.\s]+)\s+on Instagram', t_text)
                        if m_t:
                            enriched["username"] = f"@{m_t.group(1).strip()}"
                    
                    m_likes = re.search(r'([\d.,]+)\s+likes', d_text, re.IGNORECASE)
                    if m_likes:
                        enriched["likes"] = int(m_likes.group(1).replace(",", "").replace(".", ""))
            except Exception:
                pass
        elif platform == "tiktok":
            m_user = re.search(r'tiktok\.com/(@[A-Za-z0-9_.]+)', url)
            if m_user:
                enriched["username"] = m_user.group(1)
        return enriched
