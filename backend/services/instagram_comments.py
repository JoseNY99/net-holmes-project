"""Enriquecimiento de posts de Instagram: comentarios públicos y ubicación del post."""

import asyncio
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from services.cron_logger import cron_logger

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_TIME_RE = re.compile(r"^\d+\s*(s|min|h|d|sem|sema|a|w|m)\b", re.IGNORECASE)
_UI_NOISE = {"me gusta", "responder", "ver traducción", "ver respuestas", "editado"}
MAX_COMMENTS = 50


def parse_comments_from_spans(spans: List[str]) -> List[str]:
    """
    Sin login, cada comentario llega como la secuencia:
    usuario, usuario, '2 sem', texto, 'N Me gusta', 'Responder'.
    """
    comments: List[str] = []
    for i, token in enumerate(spans):
        if token.strip().lower() != "responder" or i < 4:
            continue
        likes_idx, text_idx, time_idx = i - 1, i - 2, i - 3
        if not _TIME_RE.match(spans[time_idx].strip()):
            # Comentario sin la fila de "me gusta": el texto está justo antes de 'Responder'
            text_idx, time_idx = i - 1, i - 2
            if not _TIME_RE.match(spans[time_idx].strip()):
                continue
        text = spans[text_idx].strip()
        if text and text.lower() not in _UI_NOISE and not re.search(r"\bme gusta$", text.lower()):
            comments.append(text)
        if len(comments) >= MAX_COMMENTS:
            break
    return comments


async def fetch_instagram_details(page, url: str) -> Dict[str, Any]:
    """Abre el post en una página de Playwright y devuelve comentarios y ubicación."""
    details: Dict[str, Any] = {"comments": [], "location": None}
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        spans = await page.eval_on_selector_all("span[dir=auto]", "els => els.map(e => e.innerText)")
        details["comments"] = parse_comments_from_spans(spans)
        loc = await page.query_selector('a[href*="/explore/locations/"]')
        if loc:
            details["location"] = (await loc.inner_text() or "").strip() or None
        if not details["location"]:
            body = await page.evaluate("document.body.innerText")
            m = re.search(r"Seguir\s*\n+\s*([^\n]{3,80})\n+\s*[^\n]+\n", body)
            if m and "(" in m.group(1):
                details["location"] = m.group(1).strip()
    except Exception as e:
        cron_logger.log(f"⚠️ [IG Comentarios] No se pudieron leer comentarios de {url}: {e}")
    return details


async def enrich_instagram_items(items: AsyncGenerator[Dict[str, Any], None]) -> AsyncGenerator[Dict[str, Any], None]:
    """Envuelve el generador de scrapers: agrega comentarios a cada post de Instagram."""
    browser = None
    pw = None
    page = None
    try:
        async for item in items:
            url = str(item.get("url") or "")
            if "instagram.com/" in url and ("/p/" in url or "/reel/" in url):
                try:
                    if page is None:
                        from playwright.async_api import async_playwright
                        pw = await async_playwright().start()
                        browser = await pw.chromium.launch(args=["--no-sandbox"])
                        ctx = await browser.new_context(locale="es-AR", user_agent=_UA)
                        page = await ctx.new_page()
                    details = await fetch_instagram_details(page, url)
                    existing = [c for c in (item.get("comments_audit") or []) if isinstance(c, str)]
                    item["comments_audit"] = existing + [c for c in details["comments"] if c not in existing]
                    if details["location"]:
                        item["ig_location_tag"] = details["location"]
                    cron_logger.log(
                        f"💬 [IG Comentarios] {len(item['comments_audit'])} comentarios leídos en {url}"
                    )
                except Exception as e:
                    cron_logger.log(f"⚠️ [IG Comentarios] Error enriqueciendo {url}: {e}")
            yield item
    finally:
        try:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
        except Exception:
            pass
