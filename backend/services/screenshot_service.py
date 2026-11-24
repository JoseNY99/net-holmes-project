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

LOGIN_WORDS = (
    "iniciar sesión", "inicia sesión", "inicio de sesión", "log in", "login",
    "sign in", "registrarte", "regístrate", "create new account",
)


def _dismiss_obstructions(page) -> None:
    """Cierra avisos de acceso/cookies sin ocultar el contenido de la publicación."""
    # Facebook Marketplace usa este control para el cuadro "Ve más en Facebook".
    # Se intenta primero mediante Playwright para reproducir el clic real sobre la X.
    for selector in (
        '[role="dialog"] [aria-label="Cerrar"]',
        '[role="dialog"] [aria-label="Close"]',
        '[aria-modal="true"] [aria-label="Cerrar"]',
        '[aria-modal="true"] [aria-label="Close"]',
    ):
        try:
            close_button = page.locator(selector).first
            if close_button.is_visible(timeout=250):
                close_button.click(timeout=1200, force=True)
                time.sleep(0.4)
                break
        except Exception:
            continue

    # Buscar la X dentro del cuadro de acceso. No usar un selector global porque
    # podría cerrar el visor del producto que se necesita como evidencia.
    try:
        clicked = page.evaluate("""
            (loginWords) => {
                const dialogs = [...document.querySelectorAll('[role="dialog"], [aria-modal="true"]')];
                const dialog = dialogs.find((el) => {
                    const text = (el.innerText || '').toLowerCase();
                    return loginWords.some((word) => text.includes(word));
                });
                if (!dialog) return false;
                const controls = [...dialog.querySelectorAll('button, [role="button"], [aria-label], [title]')];
                const close = controls.find((el) => {
                    const label = `${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''}`.toLowerCase();
                    const text = (el.innerText || '').trim().toLowerCase();
                    return /cerrar|close|dismiss/.test(label) || /^(×|x|ahora no|not now)$/.test(text);
                });
                if (close) {
                    close.click();
                    return true;
                }
                // Último recurso para el modal de Marketplace: su X está en la
                // esquina superior derecha aunque Facebook quite el aria-label.
                const rect = dialog.getBoundingClientRect();
                const element = document.elementFromPoint(rect.right - 42, rect.top + 38);
                const clickable = element && element.closest('button, [role="button"], a, div');
                if (!clickable) return false;
                clickable.click();
                return true;
            }
        """, list(LOGIN_WORDS))
        if clicked:
            time.sleep(0.4)
    except Exception:
        pass

    # Consentimientos de cookies también pueden tapar la publicación.
    for selector in (
        'button:has-text("Permitir todas las cookies")',
        'button:has-text("Allow all cookies")',
        'button:has-text("Aceptar todas")',
        'button:has-text("Accept all")',
    ):
        try:
            candidate = page.locator(selector).first
            if candidate.is_visible(timeout=200):
                candidate.click(timeout=1000, force=True)
                time.sleep(0.25)
                break
        except Exception:
            continue

    # Algunos avisos no ofrecen un botón accesible. Ocultar únicamente diálogos cuyo
    # texto sea de acceso/registro; nunca se elimina el contenedor de la publicación.
    try:
        page.evaluate("""
            (loginWords) => {
                const visible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.display !== 'none' &&
                        s.visibility !== 'hidden';
                };
                document.querySelectorAll('[role="dialog"], [aria-modal="true"]').forEach((el) => {
                    const text = (el.innerText || '').toLowerCase();
                    if (visible(el) && loginWords.some((word) => text.includes(word))) {
                        el.remove();
                    }
                });
                document.querySelectorAll('#cookie-banner, .cookie-banner, [data-testid="cookie-policy-manage-dialog"]').forEach((el) => el.remove());
                document.querySelectorAll('body > div').forEach((el) => {
                    const style = getComputedStyle(el);
                    const text = (el.innerText || '').toLowerCase();
                    if ((style.position === 'fixed' || style.position === 'sticky') &&
                        loginWords.some((word) => text.includes(word)) &&
                        el.getBoundingClientRect().width >= innerWidth * 0.8) {
                        el.remove();
                    }
                });
                document.documentElement.style.overflow = 'auto';
                document.body.style.overflow = 'auto';
            }
        """, list(LOGIN_WORDS))
    except Exception:
        pass

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

            # El aviso puede aparecer unos segundos después de cargar Marketplace.
            # Reintentar el cierre, pero capturar siempre aunque Facebook lo cambie.
            for _attempt in range(3):
                _dismiss_obstructions(page)
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                time.sleep(0.6)

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
