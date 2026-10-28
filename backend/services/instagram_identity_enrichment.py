"""Identidad pública de perfiles, posts y reels de Instagram del dashboard."""

import asyncio
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from services.dashboard_log import dashboard_log
from services.facebook_post_enrichment import FacebookPostEnricher
from services.listing_fields import extract_instagram_author, instagram_url_identity


@dataclass(frozen=True)
class InstagramIdentity:
    username: str | None
    display_name: str | None
    result_type: str | None
    source: str | None


class InstagramIdentityEnricher:
    _cache = {}
    _ttl = 6 * 60 * 60

    async def enrich(self, item: dict) -> InstagramIdentity:
        started = monotonic()
        result_type, profile_username = instagram_url_identity(item.get("url", ""))
        current = str(item.get("account") or item.get("seller") or "")
        if profile_username:
            return self._finish(item, InstagramIdentity(profile_username, None, result_type, "instagram_url"), started)
        if current.startswith("@") and item.get("seller_author_verified"):
            return self._finish(item, InstagramIdentity(current, None, result_type, item.get("seller_source") or "serper"), started)

        cached = self._cache.get(item.get("url"))
        if cached and monotonic() - cached[0] < self._ttl:
            return cached[1]

        identity = await self._playwright(item, result_type)
        return self._finish(item, identity, started)

    async def _playwright(self, item: dict, result_type: str | None) -> InstagramIdentity:
        try:
            async with FacebookPostEnricher._playwright_slots:
                return await asyncio.wait_for(self._render(item, result_type), timeout=18)
        except (asyncio.TimeoutError, OSError):
            return InstagramIdentity(None, None, result_type, None)

    @staticmethod
    async def _render(item: dict, result_type: str | None) -> InstagramIdentity:
        browser = await FacebookPostEnricher._get_browser()
        context = await browser.new_context(
            locale="es-AR",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        )
        page = await context.new_page()
        try:
            await page.goto(item["url"], wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1800)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            metadata = [str(tag.get("content") or "") for tag in soup.select(
                'meta[property="og:title"], meta[property="og:description"], meta[name="description"]'
            )]
            username = extract_instagram_author(*metadata)
            display_name = None
            if not username:
                for anchor in soup.select('header a[href], article header a[href], main a[href]'):
                    kind, candidate = instagram_url_identity(urljoin("https://instagram.com", str(anchor.get("href") or "")))
                    if kind == "profile" and candidate:
                        username = candidate
                        visible = " ".join(anchor.get_text(" ", strip=True).split())
                        display_name = visible if visible and visible.casefold() != candidate.lstrip("@").casefold() else None
                        break
            return InstagramIdentity(username, display_name, result_type, "instagram_playwright" if username else None)
        finally:
            await context.close()

    def _finish(self, item, identity, started):
        self._cache[item.get("url")] = (monotonic(), identity)
        dashboard_log(
            "[DASHBOARD][INSTAGRAM-AUTOR] url=%s tipo=%s username=%r nombre_visible=%r fuente=%s duracion_ms=%s",
            item.get("url"), identity.result_type, identity.username, identity.display_name,
            identity.source, round((monotonic() - started) * 1000),
        )
        return identity
