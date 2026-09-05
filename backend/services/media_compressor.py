import os
import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
import httpx
from PIL import Image, ExifTags

from config import settings
from services.cron_logger import cron_logger
from services.whatsapp_sender import get_active_whatsapp_credentials

STATIC_DIR = Path(__file__).resolve().parent.parent / 'static'
MEDIA_CHAT_DIR = STATIC_DIR / 'media' / 'chat'
MEDIA_CHAT_DIR.mkdir(parents=True, exist_ok=True)

def _has_ffmpeg() -> bool:
    return shutil.which('ffmpeg') is not None

def compress_image_bytes(data: bytes) -> tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(data))
        try:
            if hasattr(img, '_getexif') and img._getexif():
                exif = dict(img._getexif().items())
                orientation_tag = None
                for tag, value in ExifTags.TAGS.items():
                    if value == 'Orientation':
                        orientation_tag = tag
                        break
                if orientation_tag and orientation_tag in exif:
                    val = exif[orientation_tag]
                    if val == 3:
                        img = img.rotate(180, expand=True)
                    elif val == 6:
                        img = img.rotate(270, expand=True)
                    elif val == 8:
                        img = img.rotate(90, expand=True)
        except Exception:
            pass

        max_dim = 1440
        w, h = img.size
        if w > max_dim or h > max_dim:
            scale = min(max_dim / w, max_dim / h)
            new_size = (int(w * scale), int(h * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        out_io = io.BytesIO()
        img.save(out_io, format='WEBP', quality=60, method=6)
        compressed_bytes = out_io.getvalue()
        savings = max(0, int((1 - len(compressed_bytes) / max(1, len(data))) * 100))
        cron_logger.log(f'[Media Compressor] 🖼️ Imagen comprimida: {len(data)//1024}KB -> {len(compressed_bytes)//1024}KB ({savings}% ahorro)')
        return compressed_bytes, 'webp'
    except Exception as e:
        cron_logger.log(f'[Media Compressor] ⚠️ Error comprimiendo imagen ({e}). Guardando original.')
        return data, 'jpg'

def compress_audio_bytes(data: bytes, ext_hint: str = 'ogg') -> tuple[bytes, str]:
    if not _has_ffmpeg():
        return data, ext_hint
    try:
        with tempfile.NamedTemporaryFile(suffix=f'.{ext_hint}', delete=False) as in_file:
            in_file.write(data)
            in_path = in_file.name
        out_path = in_path + '_compressed.ogg'
        cmd = [
            'ffmpeg', '-y', '-i', in_path,
            '-vn', '-ac', '1', '-c:a', 'libopus',
            '-b:a', '24k', '-vbr', 'on',
            '-f', 'ogg', out_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            with open(out_path, 'rb') as f:
                compressed_bytes = f.read()
            savings = max(0, int((1 - len(compressed_bytes) / max(1, len(data))) * 100))
            cron_logger.log(f'[Media Compressor] 🎤 Audio comprimido con FFmpeg: {len(data)//1024}KB -> {len(compressed_bytes)//1024}KB ({savings}% ahorro)')
            ext = 'ogg'
        else:
            compressed_bytes = data
            ext = ext_hint
        for p in (in_path, out_path):
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
        return compressed_bytes, ext
    except Exception as e:
        cron_logger.log(f'[Media Compressor] ⚠️ Error en compresión de audio ({e}).')
        return data, ext_hint

def compress_video_bytes(data: bytes, ext_hint: str = 'mp4') -> tuple[bytes, str]:
    if not _has_ffmpeg():
        return data, ext_hint
    try:
        with tempfile.NamedTemporaryFile(suffix=f'.{ext_hint}', delete=False) as in_file:
            in_file.write(data)
            in_path = in_file.name
        out_path = in_path + '_compressed.mp4'
        cmd = [
            'ffmpeg', '-y', '-i', in_path,
            '-vcodec', 'libx264', '-crf', '30', '-preset', 'slow',
            '-vf', 'scale=min(720\,iw):-2',
            '-acodec', 'aac', '-b:a', '48k', '-ac', '1',
            out_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            with open(out_path, 'rb') as f:
                compressed_bytes = f.read()
            savings = max(0, int((1 - len(compressed_bytes) / max(1, len(data))) * 100))
            cron_logger.log(f'[Media Compressor] 🎥 Video comprimido con FFmpeg: {len(data)//1024}KB -> {len(compressed_bytes)//1024}KB ({savings}% ahorro)')
            ext = 'mp4'
        else:
            compressed_bytes = data
            ext = ext_hint
        for p in (in_path, out_path):
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
        return compressed_bytes, ext
    except Exception as e:
        cron_logger.log(f'[Media Compressor] ⚠️ Error en compresión de video ({e}).')
        return data, ext_hint

async def download_and_save_whatsapp_media(
    media_id: str,
    media_type: str,
    mime_type_hint: str = '',
    filename_hint: str = '',
    db=None
) -> tuple[str | None, str | None]:
    if not media_id:
        return None, None
    token, _ = get_active_whatsapp_credentials(db)
    if not token:
        cron_logger.log(f'[Media Downloader] ⚠️ Sin token de WhatsApp para descargar media {media_id}')
        return None, None
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': 'curl/7.64.1'}
    meta_url = f'https://graph.facebook.com/v21.0/{media_id}'
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            meta_resp = await client.get(meta_url, headers=headers)
            if meta_resp.status_code != 200:
                cron_logger.log(f'[Media Downloader] ❌ Error Meta ({meta_resp.status_code}) obteniendo media URL: {meta_resp.text}')
                return None, None
            meta_data = meta_resp.json()
            download_url = meta_data.get('url')
            mime_type = meta_data.get('mime_type') or mime_type_hint or 'application/octet-stream'
            if not download_url:
                cron_logger.log(f'[Media Downloader] ❌ Meta no devolvió URL de descarga para {media_id}')
                return None, None
            file_resp = await client.get(download_url, headers=headers)
            if file_resp.status_code != 200:
                cron_logger.log(f'[Media Downloader] ❌ Error ({file_resp.status_code}) descargando binario de {download_url}')
                return None, None
            raw_bytes = file_resp.content
            if not raw_bytes:
                return None, None
            year_month = datetime.now().strftime('%Y_%m')
            target_subfolder = MEDIA_CHAT_DIR / year_month
            target_subfolder.mkdir(parents=True, exist_ok=True)
            final_bytes = raw_bytes
            final_ext = 'bin'
            if media_type == 'image':
                final_bytes, final_ext = compress_image_bytes(raw_bytes)
            elif media_type in ('audio', 'voice'):
                hint_ext = 'ogg' if ('ogg' in mime_type or 'opus' in mime_type) else 'mp3'
                final_bytes, final_ext = compress_audio_bytes(raw_bytes, ext_hint=hint_ext)
            elif media_type == 'video':
                final_bytes, final_ext = compress_video_bytes(raw_bytes, ext_hint='mp4')
            elif media_type == 'document':
                if filename_hint and '.' in filename_hint:
                    final_ext = filename_hint.split('.')[-1].lower()
                elif 'pdf' in mime_type:
                    final_ext = 'pdf'
                else:
                    final_ext = 'doc'
                final_bytes = raw_bytes
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'{media_type}_{timestamp_str}_{media_id[:12]}.{final_ext}'
            file_path = target_subfolder / filename
            with open(file_path, 'wb') as f:
                f.write(final_bytes)
            relative_url = f'/static/media/chat/{year_month}/{filename}'
            cron_logger.log(f'[Media Downloader] 💾 Multimedia guardada: {relative_url} ({len(final_bytes)//1024} KB)')
            return relative_url, str(file_path)
    except Exception as e:
        cron_logger.log(f'[Media Downloader] ❌ Error descargando y comprimiendo media {media_id}: {e}')
        return None, None