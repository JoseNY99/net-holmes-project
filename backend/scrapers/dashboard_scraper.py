"""Serper → búsqueda gratuita, únicamente para el dashboard."""

import asyncio
import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from scrapers.serper_google_scraper import SerperGoogleScraper
from services.dashboard_result_rules import canonical_url, direct_link, seller_handle
from services.dashboard_scope import COUNTRIES
from services.public_contacts import extract_phone
from services.dashboard_log import dashboard_log
from services.listing_fields import (
    extract_facebook_author,
    extract_instagram_author,
    instagram_url_identity,
)

class DashboardScraper(SerperGoogleScraper):
    """Reutiliza los parsers existentes sin alterar el scraper usado por el cron."""

    def __init__(self, key: str | None, country: str):
        self.key = key
        self.country = country
        self.provider = "Serper" if key else "Gratuito"
        self.warning = None
        self.successful_queries = 0
        self.failed_queries = 0

    def query(self, platform: str, keyword: str, province: str | None, variant: int) -> str:
        cfg = COUNTRIES[self.country]
        site = {"facebook": "Facebook", "instagram": "Instagram", "tiktok": "TikTok", "mercadolibre": cfg["market"]}[platform]
        terms = {
            "Argentina": (
                "G5 réplica trucho ropa calzado", "calidad 1:1 simil original indumentaria zapatillas",
                "primera línea AAA ropa calzado", "PK top quality ropa zapatillas", "imitación vestimenta",
            ),
            "Brasil": (
                "réplica falsificado roupas calçados", "primeira linha premium roupas tênis",
                "linha premium espelhado roupas calçados", "qualidade 1:1 UA roupas tênis", "inspirado importado vestuário",
            ),
            "México": (
                "clon pirata réplica ropa calzado", "calidad espejo clon 1:1 ropa tenis",
                "G5 triple A ropa calzado", "super clon UA ropa tenis", "imitación vestimenta",
            ),
        }[self.country]
        # Una consulta breve por variante evita exigir todas las jergas a la vez.
        return " ".join(filter(None, (keyword, terms[variant % len(terms)], province, self.country, site)))

    async def search(self, client: httpx.AsyncClient, platform: str, keyword: str, province: str | None, variant: int = 0) -> list[dict]:
        cfg = COUNTRIES[self.country]
        query = self.query(platform, keyword, province, variant)
        page = variant // 5 + 1
        dashboard_log(
            "[DASHBOARD][BUSQUEDA] proveedor=%s pais=%s region=%s plataforma=%s pagina=%s consulta=%r",
            self.provider, self.country, province or "todas", platform, page, query,
        )
        rows = []
        source = "Google_Serper_OSINT"
        if self.key:
            try:
                response = await client.post(self.SERPER_ENDPOINT, headers={"X-API-KEY": self.key}, json={"q": query, "gl": cfg["gl"], "hl": cfg["hl"], "num": 20, "page": page})
                response.raise_for_status()
                rows = response.json().get("organic", [])
                self.successful_queries += 1
                self.provider = "Serper"
            except (httpx.HTTPError, ValueError, AttributeError) as exc:
                # Solo se desactiva durante esta ejecución; la siguiente reintenta Serper.
                self.key = None
                self.warning = "Serper no está disponible. Se utiliza la búsqueda gratuita."
                dashboard_log("[DASHBOARD][SERPER] no disponible (%s); se usa búsqueda gratuita", type(exc).__name__)
        items = [self.parse(row, platform, source, province) for row in rows if isinstance(row, dict)]
        items = [item for item in items if direct_link(item["url"], platform, self.country)]
        dashboard_log("[DASHBOARD][SERPER] recibidos=%s enlaces_directos=%s", len(rows), len(items))
        if items:
            return items
        self.provider = "Gratuito"
        source = "DuckDuckGo_OSINT"
        try:
            rows = await asyncio.to_thread(self._free_search, query, cfg["region"])
            self.successful_queries += 1
        except Exception as exc:
            self.failed_queries += 1
            self.warning = "La búsqueda gratuita no respondió en algunas consultas."
            dashboard_log("[DASHBOARD][GRATUITO] no disponible (%s)", type(exc).__name__)
            return []
        items = [item for row in rows if isinstance(row, dict) and direct_link((item := self.parse(row, platform, source, province))["url"], platform, self.country)]
        dashboard_log("[DASHBOARD][GRATUITO] recibidos=%s enlaces_directos=%s", len(rows), len(items))
        return items

    @staticmethod
    def _free_search(query: str, region: str) -> list[dict]:
        from ddgs import DDGS
        # Sin datasets de demostración ni apertura a otros países.
        with DDGS(timeout=8) as search:
            return list(search.text(query, region=region, safesearch="off", max_results=20, backend="duckduckgo"))

    def parse(self, row: dict, platform: str, source: str, searched_region: str | None = None) -> dict:
        title = str(row.get("title") or "")[:200]
        description = str(row.get("snippet") or row.get("body") or "")[:4000]
        url = canonical_url(str(row.get("link") or row.get("href") or ""))
        text = f"{title} {description}"
        handle = seller_handle(url, text)
        explicit_author = None
        if platform == "facebook":
            explicit_author = extract_facebook_author(row, title, description)
        elif platform == "instagram":
            result_type, profile_username = instagram_url_identity(url)
            explicit_author = profile_username or extract_instagram_author(title, description)
        else:
            result_type = None
        name = explicit_author or self._extract_seller_name(platform, url, title, description)
        if name == "@vendedor_tiktok":
            name = "Vendedor No Identificado"
        thumbnail = row.get("imageUrl") or row.get("thumbnail")
        return {
            "url": url, "title": title, "description": description, "plataforma": platform,
            "seller": explicit_author or handle or name,
            "account": (explicit_author if explicit_author and explicit_author.startswith("@") else handle),
            "phone": extract_phone(text, self.country),
            "followers": self._extract_followers(text), "image": thumbnail if isinstance(thumbnail, str) and thumbnail.startswith("https://") else None,
            "source": source, "address": None, "email": None, "contact_sources": [],
            "seller_initial": explicit_author or handle or name,
            "author_sources": [title, description],
            "seller_author_verified": bool(explicit_author),
            "result_type": result_type if platform == "instagram" else None,
            "seller_source": "instagram_url" if platform == "instagram" and profile_username else ("serper" if explicit_author else None),
            "searched_country": self.country, "searched_region": searched_region,
        }

    async def enrich(self, client: httpx.AsyncClient, item: dict) -> dict:
        """Máximo dos páginas públicas por resultado, después de filtrar y deduplicar."""
        pending = [item["url"]]
        visited = set()
        for _ in range(2):
            if not pending:
                break
            url = pending.pop(0)
            if url in visited:
                break
            visited.add(url)
            try:
                html = await self._public_html(client, url)
                if not html:
                    continue
                if item["plataforma"] == "facebook" and url == item["url"]:
                    # Se reutiliza en el enriquecedor de autor; nunca se persiste.
                    item["_facebook_public_html"] = html
                soup = BeautifulSoup(html, "html.parser")
                metadata_parts = [
                    str(tag.get("content") or "").strip()
                    for tag in soup.select('meta[property="og:description"], meta[name="description"], meta[property="og:title"]')
                    if str(tag.get("content") or "").strip()
                ]
                metadata = "\n".join(metadata_parts)
                item["author_sources"] = list(dict.fromkeys(
                    [*(item.get("author_sources") or []), *metadata_parts]
                ))
                links = [str(a.get("href") or "") for a in soup.select("a[href]")]
                structured = []
                for script in soup.select('script[type="application/ld+json"]'):
                    try:
                        structured.extend(self._structured_contacts(json.loads(script.string or script.get_text())))
                    except (ValueError, TypeError):
                        continue
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                # No tomar menciones de usuarios, sugerencias ni comentarios como autor.
                text = " ".join((metadata, soup.get_text(" ", strip=True)[:40000], " ".join(links), " ".join(structured)))
                item["phone"] = item["phone"] or extract_phone(text, self.country)
                email = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
                item["email"] = item["email"] or (email[0][:255] if email else None)
                for entry in structured:
                    if entry.startswith("Dirección: "):
                        item["address"] = entry[len("Dirección: "):][:255]
                if metadata:
                    item["description"] += "\n" + metadata[:4000]
                item["observed_text"] = item.get("observed_text", "") + " " + " ".join((metadata, " ".join(structured)))
                if item["plataforma"] == "facebook":
                    author = next(
                        (extract_facebook_author({}, description=part) for part in metadata_parts
                         if extract_facebook_author({}, description=part)),
                        None,
                    )
                    if author:
                        item["seller"] = author
                        item["seller_author_verified"] = True
                elif item["plataforma"] == "instagram":
                    author = extract_instagram_author(*metadata_parts)
                    if author:
                        item["account"] = author
                        item["seller"] = author
                        item["seller_author_verified"] = True
                        item["seller_source"] = "instagram_metadata"
                if not item["account"]:
                    item["account"] = seller_handle(item["url"], metadata)
                    if item["account"]:
                        item["seller"] = item["account"]
                image = soup.select_one('meta[property="og:image"]')
                if image and str(image.get("content") or "").startswith("https://"):
                    item["image"] = image["content"]
                item["contact_sources"].append(url)
                if not item["phone"]:
                    # Seguir contacto de la misma web, o el perfil del autor ya identificado.
                    contact = next((urljoin(url, link) for link in links if re.search(r"/(?:contacto|contato|contact)(?:/|$|\?)", link, re.I) and urlsplit(urljoin(url, link)).hostname == urlsplit(url).hostname), None)
                    if contact:
                        pending.append(contact)
                    elif item["account"] and item["plataforma"] in ("instagram", "tiktok"):
                        handle = item["account"].lstrip("@")
                        prefix = "@" if item["plataforma"] == "tiktok" else ""
                        pending.append(f"https://www.{item['plataforma']}.com/{prefix}{handle}/")
            except (httpx.HTTPError, ValueError, OSError, asyncio.TimeoutError):
                continue
        return item

    @classmethod
    def _structured_contacts(cls, value) -> list[str]:
        if isinstance(value, list):
            return [text for child in value for text in cls._structured_contacts(child)]
        if not isinstance(value, dict):
            return []
        result = []
        for key, child in value.items():
            if key in ("telephone", "email") and isinstance(child, str):
                result.append(("Teléfono: " if key == "telephone" else "Email: ") + child)
            elif key == "address" and isinstance(child, dict):
                address = ", ".join(str(child[k]) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry") if child.get(k))
                if address:
                    result.append("Dirección: " + address)
            elif isinstance(child, (dict, list)):
                result.extend(cls._structured_contacts(child))
        return result

    @staticmethod
    async def _public_html(client: httpx.AsyncClient, url: str) -> str:
        # Revalidar cada redirect; no permitir redes privadas o puertos de servicios internos.
        for _ in range(3):
            parsed = urlsplit(url)
            if parsed.scheme not in ("https", "http") or parsed.port not in (None, 80, 443) or parsed.username or parsed.password or not parsed.hostname:
                return ""
            addresses = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
                return ""
            async with client.stream("GET", url, timeout=5, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200 or "text/html" not in response.headers.get("content-type", ""):
                    return ""
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 512_000:
                        return ""
                return data.decode(response.encoding or "utf-8", errors="replace")
        return ""
