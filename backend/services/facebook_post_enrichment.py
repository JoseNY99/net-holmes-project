"""Identificación trazable del autor de posts públicos de Facebook del dashboard."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from difflib import SequenceMatcher
from time import monotonic
import unicodedata
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from services.dashboard_log import dashboard_log
from services.dashboard_result_rules import canonical_url
from services.listing_fields import extract_facebook_author


UNKNOWN = {"", "desconocido", "usuario desconocido", "vendedor no identificado"}


@dataclass(frozen=True)
class SellerResolution:
    name: str | None
    source: str | None
    status: str
    verified_at: datetime
    reason: str | None = None


class FacebookPostEnricher:
    _cache: dict[str, tuple[float, SellerResolution]] = {}
    _cache_ttl = 6 * 60 * 60
    _network_slots = asyncio.Semaphore(2)
    _playwright_slots = asyncio.Semaphore(1)
    _browser_lock = asyncio.Lock()
    _playwright = None
    _browser = None

    def __init__(self, serper_key: str | None, country: str):
        self.serper_key = serper_key
        self.country = country

    async def enrich(self, client: httpx.AsyncClient, item: dict, fetch_html) -> SellerResolution:
        started = monotonic()
        url = canonical_url(item.get("url", ""))
        initial = str(item.get("seller") or "").strip()
        if initial.casefold() not in UNKNOWN and item.get("seller_author_verified"):
            result = self._result(initial, "serper", "identificado")
            self._log(url, item, result, started, original=False, structured=False, playwright=False)
            return result

        cached = self._cache.get(url)
        if cached and monotonic() - cached[0] < self._cache_ttl:
            result = cached[1]
            self._log(url, item, result, started, original=False, structured=False, playwright=False, cached=True)
            return result

        original_queried = structured = playwright_used = False
        failure = None
        html = ""
        try:
            original_queried = True
            html = item.pop("_facebook_public_html", "")
            if not html:
                async with self._network_slots:
                    html = await asyncio.wait_for(fetch_html(client, url), timeout=7)
            if html:
                name, source = self.extract_from_html(html, item)
                structured = source in {"json_ld", "metadata"}
                if name:
                    result = self._result(name, source, "identificado")
                    return self._finish(url, item, result, started, original_queried, structured, playwright_used)
                if self._requires_auth(html):
                    failure = "facebook solicita autenticación"
            else:
                failure = "publicación inaccesible o sin HTML público"
        except (asyncio.TimeoutError, httpx.HTTPError, OSError, ValueError) as exc:
            failure = f"consulta pública falló: {type(exc).__name__}"

        if failure != "facebook solicita autenticación":
            playwright_used = True
            rendered, rendered_text, render_reason = await self._render_public(url)
            if rendered:
                name, source = self.extract_from_html(rendered, item, rendered=True)
                if not name:
                    name = self.extract_near_title(rendered_text, item)
                    source = "facebook_playwright" if name else None
                if name:
                    result = self._result(name, source, "identificado")
                    return self._finish(url, item, result, started, original_queried, structured, playwright_used)
                failure = "playwright renderizó la publicación pero no validó un autor cercano al título"
            failure = render_reason or failure

        if self.serper_key:
            name = await self._complementary_serper(client, url)
            if name:
                result = self._result(name, "serper_complementario", "identificado")
                return self._finish(url, item, result, started, original_queried, structured, playwright_used)

        result = self._result(None, None, "pendiente", failure or "autor no disponible en fuentes públicas")
        return self._finish(url, item, result, started, original_queried, structured, playwright_used)

    @classmethod
    def extract_from_html(cls, raw_html: str, item: dict, rendered: bool = False) -> tuple[str | None, str | None]:
        soup = BeautifulSoup(raw_html, "html.parser")
        blocked = cls._blocked_names(item)

        for script in soup.select('script[type="application/ld+json"]'):
            try:
                values = cls._json_authors(json.loads(script.string or script.get_text()))
            except (ValueError, TypeError):
                continue
            name = next((value for value in values if cls._valid_name(value, blocked)), None)
            if name:
                return name, "json_ld"

        for selector in ('meta[name="author"]', 'meta[property="article:author"]'):
            tag = soup.select_one(selector)
            value = str(tag.get("content") or "").strip() if tag else ""
            if cls._valid_name(value, blocked):
                return value, "metadata"

        # Solo cabeceras del post. Se excluyen zonas de comentarios para no tomar comentaristas.
        for comments in soup.select('[aria-label*="coment" i], [data-testid*="comment" i], ul[role="list"]'):
            comments.decompose()
        selectors = (
            'article header a[href]', 'article h2 a[href]', 'article h3 a[href]',
            '[role="article"] h2 a[href]', '[role="article"] h3 a[href]',
            '[data-ad-preview="message"] ~ * a[href]',
        )
        for anchor in soup.select(", ".join(selectors)):
            name = " ".join(anchor.get_text(" ", strip=True).split())
            href = str(anchor.get("href") or "")
            if cls._profile_link(href) and cls._valid_name(name, blocked):
                return name, "facebook_playwright" if rendered else "cabecera_html"
        return None, None

    @classmethod
    def extract_near_title(cls, body_text: str, item: dict) -> str | None:
        """Fallback validado: cabecera autor/fecha inmediatamente previa al título."""
        title = cls._fold_title(item.get("title", ""))
        if not title or len(title) < 8:
            return None
        lines = [" ".join(line.split()) for line in str(body_text or "").splitlines() if line.strip()]
        blocked = cls._blocked_names(item)
        noise = re.compile(
            r"^(?:·|unirte(?: al grupo)?|seguir|compartir|me gusta|comentar|iniciar sesi[oó]n|"
            r"¿olvidaste la cuenta\?|\d+(?:[.,]\d+)?\s*(?:mil|k)?\s+miembros|"
            r"\d{1,2}\s+de\s+[a-záéíóúñ]+(?:\s+de\s+\d{4})?|ayer|hace\s+\d+.*)$",
            re.IGNORECASE,
        )
        date_line = re.compile(
            r"^(?:(?:hace\s+)?\d+\s+(?:minutos?|horas?|d[ií]as?|semanas?|meses?|a[nñ]os?)|"
            r"\d{1,2}\s+de\s+[a-záéíóúñ]+(?:\s+de\s+\d{4})?|ayer|hoy)$",
            re.I,
        )

        # Facebook puede mostrar el título indexado por Serper al final del post.
        # En grupos, la secuencia estable de la cabecera es:
        # nombre del grupo -> Unirte -> autor -> fecha -> contenido.
        for index, candidate in enumerate(lines):
            clean = " ".join(candidate.split()).strip(" ·")
            if not clean or noise.match(clean) or date_line.match(clean):
                continue
            before = [part.strip(" ·") for part in lines[max(0, index - 4):index]]
            after = [part.strip(" ·") for part in lines[index + 1:index + 5]]
            follows_group_join = any(re.fullmatch(r"unirte(?: al grupo)?", part, re.I) for part in before if part)
            precedes_date = any(date_line.match(part) for part in after if part)
            if follows_group_join and precedes_date and cls._valid_name(clean, blocked):
                return clean

        for index, line in enumerate(lines):
            folded_line = cls._fold_title(line)
            if not cls._same_title(title, folded_line):
                continue
            # Preferir la aparición del título como línea propia, no el og:title grupo | título.
            if folded_line != title and "|" in line:
                continue
            window_start = max(0, index - 8)
            previous = lines[window_start:index]
            for offset in range(len(previous) - 1, -1, -1):
                candidate = previous[offset]
                clean = " ".join(candidate.split()).strip(" ·")
                if not clean or noise.match(clean) or date_line.match(clean):
                    continue
                # El fallback solo es fiable cuando el candidato forma parte de una
                # cabecera autor/fecha. Así no toma texto del producto cercano.
                between = [part.strip(" ·") for part in previous[offset + 1:]]
                has_date = any(date_line.match(part) for part in between if part)
                if has_date and cls._valid_name(clean, blocked) and not cls._looks_commercial(clean):
                    return clean
        return None

    @staticmethod
    def _fold(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or ""))
        return " ".join(normalized.casefold().split())

    @classmethod
    def _fold_title(cls, value: str) -> str:
        folded = cls._fold(value).replace("…", " ").replace("...", " ")
        return " ".join(re.findall(r"[\wáéíóúñ]+", folded, re.UNICODE))

    @staticmethod
    def _same_title(expected: str, observed: str) -> bool:
        if not expected or not observed:
            return False
        if expected in observed or observed in expected:
            return min(len(expected), len(observed)) >= 12
        expected_words, observed_words = expected.split(), observed.split()
        common_prefix = 0
        for left, right in zip(expected_words, observed_words):
            if left != right:
                break
            common_prefix += 1
        return common_prefix >= 4 or SequenceMatcher(None, expected, observed).ratio() >= 0.68

    @staticmethod
    def _looks_commercial(value: str) -> bool:
        return bool(re.search(
            r"\b(?:zapatillas?|calzados?|ropa|puma|nike|adidas|g5|aaa|ua|réplica|replica|"
            r"calidad|premium|primera\s+l[ií]nea|1\s*:\s*1|stock|importad[oa]s?|precio|"
            r"talles?|modelos?|consultar|disponible|oferta|env[ií]os?|mayorista)\b",
            value, re.IGNORECASE,
        ))

    @staticmethod
    def _json_authors(value) -> list[str]:
        found = []
        if isinstance(value, list):
            for child in value:
                found.extend(FacebookPostEnricher._json_authors(child))
        elif isinstance(value, dict):
            for key in ("author", "creator", "accountablePerson"):
                child = value.get(key)
                child_type = str(child.get("@type") or "").casefold() if isinstance(child, dict) else ""
                if isinstance(child, dict) and child.get("name") and child_type not in {"organization", "group"}:
                    found.append(str(child["name"]))
                elif isinstance(child, str):
                    found.append(child)
            for child in value.values():
                if isinstance(child, (dict, list)):
                    found.extend(FacebookPostEnricher._json_authors(child))
        return found

    @staticmethod
    def _blocked_names(item: dict) -> set[str]:
        values = [item.get("title", "")]
        values.extend(item.get("facebook_group_names") or [])
        return {" ".join(str(value).split()).casefold() for value in values if value}

    @staticmethod
    def _valid_name(name: str, blocked: set[str]) -> bool:
        clean = " ".join(str(name or "").split()).strip()
        return bool(
            clean and clean.casefold() not in blocked and clean.casefold() not in UNKNOWN
            and 1 < len(clean.split()) <= 5 and len(clean) <= 100
            and not re.search(r"\b(?:grupo|compras?|ventas?|trueque|unirte|facebook|comentarios?)\b", clean, re.I)
            and not FacebookPostEnricher._looks_commercial(clean)
        )

    @staticmethod
    def _profile_link(href: str) -> bool:
        parsed = urlsplit(urljoin("https://facebook.com", href).replace("www.", ""))
        path = parsed.path.casefold()
        return "facebook.com" in (parsed.hostname or "") and not any(
            part in path for part in ("/groups/", "/posts/", "/comments/", "/share/", "/plugins/", "/login")
        )

    @staticmethod
    def _requires_auth(raw_html: str) -> bool:
        text = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True).casefold()
        return any(value in text for value in ("inicia sesión", "iniciar sesión", "log in to facebook", "debes iniciar sesión"))

    async def _render_public(self, url: str) -> tuple[str, str, str | None]:
        try:
            async with self._playwright_slots:
                return await asyncio.wait_for(self._render_async(url), timeout=20)
        except asyncio.TimeoutError:
            return "", "", "playwright agotó el tiempo"
        except Exception as exc:
            return "", "", f"playwright falló: {type(exc).__name__}"

    @classmethod
    async def _get_browser(cls):
        if cls._browser and cls._browser.is_connected():
            return cls._browser
        async with cls._browser_lock:
            if cls._browser and cls._browser.is_connected():
                return cls._browser
            from playwright.async_api import async_playwright
            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(headless=True)
            return cls._browser

    @classmethod
    async def _render_async(cls, url: str) -> tuple[str, str, str | None]:
        browser = await cls._get_browser()
        context = await browser.new_context(
            locale="es-AR",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2500)
            body_text = await page.locator("body").inner_text(timeout=5000)
            html = await page.content()
            if "login" in page.url.casefold() and not body_text:
                return "", "", "facebook solicita autenticación"
            return html, body_text, None
        finally:
            await context.close()

    @classmethod
    async def close(cls):
        async with cls._browser_lock:
            if cls._browser:
                await cls._browser.close()
                cls._browser = None
            if cls._playwright:
                await cls._playwright.stop()
                cls._playwright = None

    async def _complementary_serper(self, client: httpx.AsyncClient, url: str) -> str | None:
        post_id = next(reversed([part for part in urlsplit(url).path.split("/") if part]), "")
        query = f'"{post_id}" Facebook autor'
        try:
            async with self._network_slots:
                response = await asyncio.wait_for(client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": self.serper_key, "Content-Type": "application/json"},
                    json={"q": query, "num": 5, "gl": "ar", "hl": "es-419"},
                ), timeout=7)
            response.raise_for_status()
            for row in response.json().get("organic", [])[:5]:
                name = extract_facebook_author(row, str(row.get("title") or ""), str(row.get("snippet") or ""))
                if name and self._valid_name(name, set()):
                    return name
        except (asyncio.TimeoutError, httpx.HTTPError, ValueError, AttributeError):
            return None
        return None

    @staticmethod
    def _result(name, source, status, reason=None):
        return SellerResolution(name, source, status, datetime.now(timezone.utc), reason)

    def _finish(self, url, item, result, started, original, structured, playwright):
        self._cache[url] = (monotonic(), result)
        self._log(url, item, result, started, original, structured, playwright)
        return result

    @staticmethod
    def _log(url, item, result, started, original, structured, playwright, cached=False):
        dashboard_log(
            "[DASHBOARD][FACEBOOK-AUTOR] url=%s proveedor=%s serper_autor=%s original=%s estructurado=%s playwright=%s cache=%s nombre=%r fuente=%s estado=%s motivo=%s duracion_ms=%s",
            url, item.get("source"), bool(item.get("seller_author_verified")), original, structured,
            playwright, cached, result.name, result.source, result.status, result.reason,
            round((monotonic() - started) * 1000),
        )
