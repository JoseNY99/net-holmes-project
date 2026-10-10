import os
import re
import shutil
import urllib.parse
from pathlib import Path
from curl_cffi import requests
from services.cron_logger import cron_logger

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_EVIDENCIAS_DIR = BASE_DIR / 'static' / 'evidencias'
STATIC_EVIDENCIAS_DIR.mkdir(parents=True, exist_ok=True)

def limpiar_url_canonica(raw_url: str) -> str:
    if not raw_url:
        return 'N/A'
    url = str(raw_url).strip()
    
    if 'duckduckgo.com/l/' in url or 'uddg=' in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if 'uddg' in qs:
            url = qs['uddg'][0]
            
    if 'google.com/url' in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if 'q' in qs:
            url = qs['q'][0]
            
    if 'instagram.com/p/' in url or 'instagram.com/reel/' in url:
        m = re.search(r'instagram\.com/(p|reel)/([A-Za-z0-9_-]+)', url)
        if m:
            return f'https://www.instagram.com/{m.group(1)}/{m.group(2)}/'
            
    if 'facebook.com/marketplace/item/' in url:
        m = re.search(r'facebook\.com/marketplace/item/(\d+)', url)
        if m:
            return f'https://www.facebook.com/marketplace/item/{m.group(1)}/'
            
    if 'tiktok.com' in url and '/video/' in url:
        m_user = re.search(r'tiktok\.com/(@[^/]+/video/\d+)', url)
        if m_user:
            return f'https://www.tiktok.com/{m_user.group(1)}'
        m_vid = re.search(r'tiktok\.com/video/(\d+)', url)
        if m_vid:
            return f'https://www.tiktok.com/@_/video/{m_vid.group(1)}'
            
    if 'mercadolibre.com' in url or 'articulo.mercadolibre.com.ar' in url:
        m_mla = re.search(r'(MLA-?\d+)', url, re.IGNORECASE)
        if m_mla:
            mla_clean = m_mla.group(1).replace('-', '').upper()
            return f'https://articulo.mercadolibre.com.ar/{mla_clean}'
            
    return url

def persistir_imagen_local(img_source: str | list, reporte_id: int, post_url: str = None) -> str | None:
    filename = f'reporte_{reporte_id}.jpg'
    target_path = STATIC_EVIDENCIAS_DIR / filename
    
    actual_source = None
    if isinstance(img_source, list) and len(img_source) > 0:
        actual_source = img_source[0]
    elif isinstance(img_source, str):
        if img_source.startswith('['):
            import json
            try:
                parsed = json.loads(img_source)
                if isinstance(parsed, list) and len(parsed) > 0:
                    actual_source = parsed[0]
            except Exception:
                actual_source = img_source
        else:
            actual_source = img_source
            
    if actual_source and isinstance(actual_source, str) and actual_source.startswith('/static/'):
        local_rel = actual_source.lstrip('/')
        local_full = BASE_DIR / local_rel
        if local_full.exists():
            shutil.copy2(local_full, target_path)
            cron_logger.log(f'💾 [Evidencia Local] Imagen copiada a {target_path.name}')
            return f'/static/evidencias/{filename}'
            
    if actual_source and isinstance(actual_source, str) and actual_source.startswith('http'):
        try:
            res = requests.get(actual_source, impersonate='chrome120', timeout=15)
            if res.status_code == 200 and len(res.content) > 1000:
                with open(target_path, 'wb') as f:
                    f.write(res.content)
                cron_logger.log(f'💾 [Evidencia Local] Foto remota descargada a {target_path.name}')
                return f'/static/evidencias/{filename}'
        except Exception as e:
            cron_logger.log(f'⚠️ [Evidencia Local] Error descargando foto remota: {e}')
            
    clean_post_url = limpiar_url_canonica(post_url) if post_url else None
    if clean_post_url and clean_post_url.startswith('http') and 'n/a' not in clean_post_url.lower():
        # 3. Intentar descarga rápida de foto de producto vía OpenGraph (og:image)
        try:
            from bs4 import BeautifulSoup
            res_meta = requests.get(clean_post_url, impersonate='chrome120', timeout=8)
            if res_meta.status_code == 200:
                soup = BeautifulSoup(res_meta.text, 'html.parser')
                og_img = soup.find('meta', property='og:image')
                if og_img and og_img.get('content') and og_img.get('content').startswith('http'):
                    direct_img_url = og_img.get('content')
                    res_img = requests.get(direct_img_url, impersonate='chrome120', timeout=12)
                    if res_img.status_code == 200 and len(res_img.content) > 1000:
                        with open(target_path, 'wb') as f:
                            f.write(res_img.content)
                        cron_logger.log(f'💾 [Evidencia Local] Foto HD original guardada en {target_path.name} ({len(res_img.content) // 1024} KB)')
                        return f'/static/evidencias/{filename}'
        except Exception as e_og:
            pass

        # 4. Fallback: Captura en vivo de pantalla con Playwright Stealth
        try:
            from services.screenshot_service import take_screenshot_threaded
            cron_logger.log(f'📸 [Evidencia Local] Captura en vivo de {clean_post_url} para #{reporte_id}')
            ok = take_screenshot_threaded(clean_post_url, target_path, timeout=35.0)
            if ok and target_path.exists():
                cron_logger.log(f'✅ [Evidencia Local] Captura guardada en {target_path.name}')
                return f'/static/evidencias/{filename}'
        except Exception as se:
            cron_logger.log(f'⚠️ [Evidencia Local] Fallo captura: {se}')
            
    return None
