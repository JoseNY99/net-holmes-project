"""
Servicio OSINT de Captura de Pantalla en Vivo con Playwright Stealth.
Permite generar capturas limpias de publicaciones de Facebook, Instagram, TikTok y Mercado Libre.
Usa sync_playwright dentro de asyncio.to_thread para compatibilidad 100% nativa con Windows y FastAPI.
"""

import os
import time
import asyncio
import random
from pathlib import Path
from playwright.sync_api import sync_playwright
from services.cron_logger import cron_logger

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_SCREENSHOTS_DIR = BASE_DIR / "static" / "screenshots"
STATIC_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['es-AR', 'es', 'en'] });
window.chrome = { runtime: {} };
"""

def _take_screenshot_sync(url: str, output_path: Path) -> bool:
    """Función sincrónica ejecutada en threadpool aislado."""
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        )
        try:
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                geolocation={"latitude": -34.6037, "longitude": -58.3816},
                permissions=["geolocation"],
                locale="es-AR",
                timezone_id="America/Argentina/Buenos_Aires",
                viewport={"width": 1280, "height": 900},
                extra_http_headers={
                    "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
                }
            )
            context.add_init_script(STEALTH_JS)
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=16000)
            except Exception:
                # Si domcontentloaded demora por scripts externos pesados, continuar con el contenido renderizado
                pass
            time.sleep(1.5)

            current_url = page.url.lower()
            redirected_to_login = any(
                part in current_url for part in ("/login", "/checkpoint", "/auth/")
            )

            try:
                password_fields = page.locator('input[type="password"]').count()
                body_text = page.locator("body").inner_text(timeout=3000).lower()
            except Exception:
                password_fields = 0
                body_text = ""

            login_wall = redirected_to_login or (
                password_fields > 0
                and any(
                    phrase in body_text
                    for phrase in ("iniciar sesión", "inicia sesión", "log in", "sign in")
                )
            )
            # Marketplace/post pages can show a login prompt while still rendering
            # the actual listing photo. Keep that visual evidence instead of rejecting it.
            visible_listing_image = page.evaluate("""
                () => Array.from(document.images).some((img) => {
                    const rect = img.getBoundingClientRect();
                    const style = window.getComputedStyle(img);
                    const description = `${img.alt || ''} ${img.src || ''}`.toLowerCase();
                    const looksLikeUi = /avatar|profile|logo|icon|emoji|sprite|rsrc\\.php/.test(description);
                    const visible = rect.width >= 140 && rect.height >= 120 &&
                        style.display !== 'none' && style.visibility !== 'hidden' &&
                        Number(style.opacity || 1) > 0 &&
                        rect.bottom > 0 && rect.right > 0 &&
                        rect.top < window.innerHeight && rect.left < window.innerWidth;
                    return visible && img.complete && img.naturalWidth >= 140 &&
                        img.naturalHeight >= 120 && !looksLikeUi;
                })
            """)
            if login_wall and not visible_listing_image:
                cron_logger.log(
                    f"[Screenshot OSINT] Se omite captura: se detectó un formulario de login ({url})."
                )
                return False
            if login_wall and visible_listing_image:
                cron_logger.log(
                    f"[Screenshot OSINT] Se conserva la captura: hay una imagen de publicación visible "
                    f"a pesar del formulario de login ({url})."
                )

            # Intentar limpiar modales obstructivos de login/cookies
            try:
                page.evaluate("""
                    () => {
                        const selectors = [
                            'div[role="dialog"]',
                            '#cookie-banner',
                            '.cookie-banner',
                            'div[aria-label="Cerrar"]',
                            'div[aria-label="Close"]',
                            'div[aria-label="Decline"]',
                            'button[aria-label="Cerrar"]',
                            'button:has-text("Aceptar")',
                            'button:has-text("Accept")',
                            'div[data-testid="cookie-policy-manage-dialog"]'
                        ];
                        selectors.forEach(sel => {
                            try {
                                document.querySelectorAll(sel).forEach(el => {
                                    if (el.innerText && (el.innerText.includes('Inicia') || el.innerText.includes('cookies') || el.innerText.includes('Log In'))) {
                                        el.style.display = 'none';
                                    }
                                });
                            } catch(e) {}
                        });
                    }
                """)
            except Exception:
                pass

            page.screenshot(
                path=str(output_path),
                type="jpeg",
                quality=85,
                full_page=False
            )
            return True
        finally:
            browser.close()

def take_screenshot_threaded(url: str, output_path: Path, timeout: float = 30.0) -> bool:
    """Ejecuta _take_screenshot_sync en un hilo del sistema operativo limpio sin bucle asyncio."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_take_screenshot_sync, url, output_path)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            cron_logger.log(f" [Screenshot Worker] Error capturando {url}: {e}")
            return False

async def capture_post_screenshot(url: str, reporte_id: int) -> str | None:
    """
    Navega a la URL con Playwright Stealth en threadpool aislado,
    neutraliza modales de login/cookies y captura un screenshot nítido en formato JPEG.
    Devuelve la URL relativa '/static/screenshots/reporte_{reporte_id}.jpg'.
    """
    if not url or not url.startswith("http"):
        return None

    filename = f"reporte_{reporte_id}.jpg"
    output_path = STATIC_SCREENSHOTS_DIR / filename

    cron_logger.log(f"[Screenshot OSINT] 📸 Capturando pantalla para Reporte #{reporte_id}: {url}")

    try:
        success = await asyncio.to_thread(take_screenshot_threaded, url, output_path)
        if success and output_path.exists():
            cron_logger.log(f" [Screenshot OSINT] Captura guardada con éxito en {output_path.name}")
            return f"/static/screenshots/{filename}"
        return None
    except Exception as e:
        cron_logger.log(f" [Screenshot OSINT] No se pudo tomar captura de {url}: {e}")
        return None
