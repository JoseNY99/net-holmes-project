import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import httpx
from typing import Dict, Any

from scrapers.playwright_fallback import _run_isolated_playwright, _run_playwright_async
from services.cron_logger import cron_logger

async def scrape_generic_url(url: str) -> Dict[str, Any]:
    cron_logger.log(f"[Generic Scraper] Iniciando escaneo manual de: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    html = ""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
            cron_logger.log("[Generic Scraper] HTTPX fetch exitoso.")
    except Exception as e:
        cron_logger.log(f" [Generic Scraper] HTTPX falló ({e}). Intentando Playwright...")
        # Lógica de fallback con Playwright para SPA / Cloudflare
        # Reutilizamos lógica de aislamiento (aislando en otro hilo si es necesario, pero acá ya estamos async)
        # Importamos de playwright_fallback o implementamos simple:
        from playwright.async_api import async_playwright
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(user_agent=headers["User-Agent"])
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                html = await page.content()
                await browser.close()
                cron_logger.log("[Generic Scraper] Playwright fetch exitoso.")
        except Exception as pe:
            cron_logger.log(f" [Generic Scraper] Playwright también falló: {pe}")
            return {"error": str(pe)}

    # Parsear HTML
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Título
    title = soup.title.string if soup.title else ""
    if not title:
        h1 = soup.find('h1')
        title = h1.text if h1 else "Sin título"
        
    title = title.strip()
    
    # 2. Descripción (Meta o texto)
    desc_meta = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', property='og:description')
    description = desc_meta['content'] if desc_meta and desc_meta.has_attr('content') else ""
    if not description:
        # Fallback a body text
        if soup.body:
            description = soup.body.get_text(separator=' ', strip=True)[:1000]
            
    # 3. Imágenes (Meta OG o imágenes grandes)
    images = []
    img_meta = soup.find('meta', property='og:image')
    if img_meta and img_meta.has_attr('content'):
        images.append(img_meta['content'])
    for img in soup.find_all('img'):
        src = img.get('src')
        if src and src.startswith('http'):
            images.append(src)
    
    # 4. Precio (Heurística)
    price = ""
    text_content = (title + " " + description).replace('.', '').replace(',', '.')
    price_match = re.search(r'\$\s*(\d+[\d\.]*)', text_content)
    if price_match:
        price = price_match.group(1)
        
    # 5. Teléfonos (Regex AR)
    phones = re.findall(r'(?:(?:\+?54\s*9\s*)?11\s*[3-6]\d{3}-?\d{4})|(?:(?:\+?54\s*9\s*)?[1-3]\d{2}\s*\d{3}-?\d{4})', text_content)
    phones = list(set([p.strip() for p in phones]))
    
    # 6. Emails
    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text_content)
    emails = list(set([e.strip() for e in emails]))
    
    # 7. Autor/Username
    author = "Desconocido"
    author_meta = soup.find('meta', attrs={'name': 'author'})
    if author_meta and author_meta.has_attr('content'):
        author = author_meta['content']
    elif "mercadolibre" in url:
        # Extraer Vendedor ML si es posible
        seller_el = soup.find('span', class_='ui-pdp-color--BLUE')
        if seller_el: author = seller_el.text.strip()
        
    cron_logger.log(f" [Generic Scraper] Extracción exitosa. Teléfonos: {len(phones)}, Emails: {len(emails)}")

    return {
        "plataforma": "generico",
        "title": title,
        "description": description[:3000],
        "price": price,
        "url": url,
        "imagen_urls": str(images[:3]),
        "seller_profile": {
            "name": author,
            "url": url
        },
        "location": "N/A",
        "raw_data": {
            "phones": phones,
            "emails": emails
        },
        "platform_data": {
            "source_engine": "Manual Generic Scraper",
            "extracted_phones": phones,
            "extracted_emails": emails
        }
    }
