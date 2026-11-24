"""Enriquecimiento conservador de publicaciones mediante OCR y el LLM configurado.

La imagen nunca se envía al modelo de texto: Tesseract extrae el texto visible y
DeepSeek/Cerebras recibe ese OCR junto con los metadatos públicos. Los valores se
incorporan sólo cuando el campo original está vacío.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
import ipaddress
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, ImageEnhance, ImageOps
import pytesseract

from services.cron_logger import cron_logger
from services.llm_client import call_llm_chat_completion
from services.listing_fields import extract_price
from services.public_contacts import extract_labelled_phone, extract_phone


BASE_DIR = Path(__file__).resolve().parent.parent
UNKNOWN_VALUES = {
    "", "n/a", "na", "null", "none", "desconocido", "desconocida",
    "no informado", "no informada", "no detectado", "no detectada",
    "vendedor no identificado", "usuario desconocido",
}
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _clean(value, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    if not text or text.casefold() in UNKNOWN_VALUES:
        return None
    return text[:limit]


def _walk_image_values(value) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                return _walk_image_values(json.loads(text))
            except (ValueError, TypeError):
                pass
        return [text] if text.startswith(("http://", "https://", "/static/")) else []
    if isinstance(value, (list, tuple, set)):
        return [url for child in value for url in _walk_image_values(child)]
    return []


def image_sources(item: dict) -> list[str]:
    platform_data = item.get("platform_data")
    platform_data = platform_data if isinstance(platform_data, dict) else {}
    raw_data = item.get("raw_data")
    raw_data = raw_data if isinstance(raw_data, dict) else {}
    sources: list[str] = []
    for value in (
        item.get("image"), item.get("image_urls"), item.get("imagen_urls"), item.get("images"),
        platform_data.get("image_urls"), platform_data.get("images"), platform_data.get("display_url"),
        raw_data.get("imageUrl"), raw_data.get("thumbnail"), raw_data.get("images"),
    ):
        sources.extend(_walk_image_values(value))
    return list(dict.fromkeys(sources))[:MAX_IMAGES]


async def _download_image(client: httpx.AsyncClient, source: str) -> bytes | None:
    if source.startswith("/static/"):
        path = (BASE_DIR / source.lstrip("/")).resolve()
        static_dir = (BASE_DIR / "static").resolve()
        if static_dir not in path.parents or not path.is_file():
            return None
        data = await asyncio.to_thread(path.read_bytes)
        return data if len(data) <= MAX_IMAGE_BYTES else None

    current = source
    for _ in range(3):
        parsed = urlsplit(current)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        try:
            addresses = await asyncio.get_running_loop().getaddrinfo(
                parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
            if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
                return None
            async with client.stream("GET", current, follow_redirects=False, timeout=12) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    return None
                content_type = response.headers.get("content-type", "").casefold()
                if not content_type.startswith("image/"):
                    return None
                declared = int(response.headers.get("content-length") or 0)
                if declared > MAX_IMAGE_BYTES:
                    return None
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks)
        except (httpx.HTTPError, ValueError, OSError):
            return None
    return None


def _ocr_image(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            if max(image.size) < 1800:
                ratio = min(2.5, 1800 / max(image.size))
                image = image.resize((int(image.width * ratio), int(image.height * ratio)))
            gray = ImageOps.grayscale(image)
            gray = ImageEnhance.Contrast(gray).enhance(1.7)
            text = pytesseract.image_to_string(gray, lang="spa+eng", config="--psm 6")
            return "\n".join(line.strip() for line in text.splitlines() if line.strip())[:8000]
    except Exception as exc:
        cron_logger.log(f"[OCR publicación] No se pudo leer una imagen: {exc}")
        return ""


async def add_image_ocr(item: dict, client: httpx.AsyncClient, country: str = "Argentina") -> dict:
    """Añade texto visible de las imágenes sin llamar todavía al LLM."""
    texts = []
    for source in image_sources(item):
        data = await _download_image(client, source)
        if data:
            text = await asyncio.to_thread(_ocr_image, data)
            if text:
                texts.append(text)
    if not texts:
        return item
    ocr_text = "\n--- IMAGEN ---\n".join(dict.fromkeys(texts))[:16000]
    item["image_ocr_text"] = ocr_text
    item["observed_text"] = " ".join(filter(None, (item.get("observed_text"), ocr_text)))
    # Datos de formato inequívoco no dependen del proveedor de IA.
    if not item.get("phone"):
        item["phone"] = extract_phone(ocr_text, country) or extract_labelled_phone(ocr_text)
    if not item.get("email"):
        email = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", ocr_text, re.I)
        item["email"] = email.group(0)[:255] if email else None
    if not item.get("extracted_price"):
        item["extracted_price"] = extract_price(ocr_text)
    return item


def _context(item: dict) -> str:
    platform_data = item.get("platform_data")
    platform_data = platform_data if isinstance(platform_data, dict) else {}
    comments = item.get("comments_audit") or item.get("comments") or platform_data.get("comments_text") or ""
    if isinstance(comments, (list, tuple)):
        comments = "\n".join(str(value) for value in comments if value)
    return "\n".join((
        f"PLATAFORMA: {item.get('plataforma') or 'no informada'}",
        f"URL: {item.get('url') or ''}",
        f"TÍTULO: {item.get('title') or ''}",
        f"DESCRIPCIÓN Y METADATOS: {item.get('description') or ''}",
        f"COMENTARIOS PÚBLICOS: {comments}",
        f"TEXTO OCR DE LAS IMÁGENES: {item.get('image_ocr_text') or 'sin texto legible'}",
    ))[:24000]


SYSTEM_PROMPT = """Sos un extractor de datos públicos para protección de marcas.
Copiá únicamente datos explícitos de la publicación, sus metadatos, comentarios o texto OCR.
No deduzcas identidades, domicilios, teléfonos, marcas, productos ni precios. No completes datos
por conocimiento general. Un nombre mencionado como comprador o comentarista no es el vendedor.
Un número de 7 a 15 dígitos identificado como WhatsApp, wasap, wsp, teléfono, celular o contacto
sí es un teléfono público válido aunque no tenga prefijo internacional o no coincida con el país.
Devolvé JSON válido, sin markdown, con estas claves exactas y null cuando no haya evidencia:
seller_name, account, phone, email, address, location_city, location_province, price, currency,
product, brand, category, condition, delivery_method, followers. price y followers deben ser números o null.
"""


def _json_object(content: str) -> dict:
    clean = content.strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I)
    try:
        value = json.loads(clean)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        match = re.search(r"\{.*\}", clean, re.S)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}


def _fold(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.sub(r"[^a-z0-9@.+]+", " ", text.encode("ascii", "ignore").decode().casefold()).split())


def _evidence_only(extracted: dict, evidence: str) -> dict:
    """Rechaza valores del LLM que no puedan localizarse en la fuente pública."""
    folded_evidence = _fold(evidence)
    evidence_digits = re.sub(r"\D", "", evidence)
    accepted = {}
    for key, value in extracted.items():
        if value is None or value == "":
            continue
        if key in {"price", "followers"}:
            digits = re.sub(r"\D", "", str(value))
            if digits and digits in evidence_digits:
                accepted[key] = value
            continue
        if key == "phone":
            digits = re.sub(r"\D", "", str(value))
            # Se admite el prefijo internacional normalizado si los diez
            # dígitos publicados coinciden exactamente con la evidencia.
            if 7 <= len(digits) <= 15 and digits in evidence_digits:
                accepted[key] = value
            continue
        clean = _fold(value)
        if clean and clean in folded_evidence:
            accepted[key] = value
    return accepted


def _merge_extraction(item: dict, extracted: dict, country: str = "Argentina") -> dict:
    seller = _clean(extracted.get("seller_name"), 255)
    account = _clean(extracted.get("account"), 255)
    phone = _clean(extracted.get("phone"), 100)
    email = _clean(extracted.get("email"), 255)
    address = _clean(extracted.get("address"), 255)
    city = _clean(extracted.get("location_city"), 120)
    province = _clean(extracted.get("location_province"), 120)

    if not item.get("phone") and phone:
        item["phone"] = phone
    if not item.get("email") and email and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        item["email"] = email
    if not item.get("address"):
        item["address"] = address or ", ".join(filter(None, (city, province))) or None
    current_seller = _clean(item.get("seller"))
    if (not current_seller or current_seller.casefold() in UNKNOWN_VALUES) and (account or seller):
        item["seller"] = account or seller
        item["account"] = account
        item["seller_source"] = "ai_public_evidence"
        item["seller_author_verified"] = False
    seller_profile = item.get("seller_profile")
    seller_profile = seller_profile if isinstance(seller_profile, dict) else {}
    profile_name = _clean(seller_profile.get("name"))
    if (not profile_name or profile_name.casefold() in UNKNOWN_VALUES) and (account or seller):
        item["seller_profile"] = {**seller_profile, "name": account or seller}

    price = extracted.get("price")
    if isinstance(price, str):
        price = extract_price(price)
    if isinstance(price, (int, float)) and price > 0 and not item.get("extracted_price"):
        item["extracted_price"] = float(price)
        if not item.get("price"):
            item["price"] = float(price)
    followers = extracted.get("followers")
    if isinstance(followers, str):
        followers = int(re.sub(r"\D", "", followers) or 0)
    if isinstance(followers, (int, float)) and followers >= 0 and item.get("followers") is None:
        item["followers"] = int(followers)
    for target, source in (
        ("product", "product"), ("detected_brand", "brand"), ("category", "category"),
        ("condition", "condition"), ("delivery_method", "delivery_method"),
        ("detected_currency", "currency"),
    ):
        if not item.get(target):
            item[target] = _clean(extracted.get(source), 255)
    platform_data = item.get("platform_data")
    platform_data = platform_data if isinstance(platform_data, dict) else {}
    for target, value in (
        ("marketplace_category", item.get("category")),
        ("item_condition", item.get("condition")),
        ("delivery_method", item.get("delivery_method")),
        ("seller_location_city", city),
        ("seller_location_province", province),
    ):
        if value and not platform_data.get(target):
            platform_data[target] = value
    item["platform_data"] = platform_data
    item["ai_enrichment"] = {key: value for key, value in extracted.items() if _clean(value)}
    return item


async def enrich_publication_with_ai(item: dict, country: str = "Argentina") -> dict:
    """Extrae datos faltantes. Un error del proveedor nunca bloquea el reporte."""
    evidence = _context(item)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": evidence},
    ]
    content, error = await call_llm_chat_completion(messages, temperature=0.0, max_tokens=700)
    if not content:
        if error:
            cron_logger.log(f"[IA publicación] Enriquecimiento omitido: {error}")
        if not item.get("phone"):
            item["phone"] = extract_labelled_phone(evidence)
        return item
    extracted = _evidence_only(_json_object(content), evidence)
    if not extracted:
        cron_logger.log("[IA publicación] El proveedor no devolvió JSON utilizable.")
        # La extracción etiquetada sigue funcionando si el proveedor responde
        # con un formato inválido o deja el campo en null.
        if not item.get("phone"):
            item["phone"] = extract_labelled_phone(evidence)
        return item
    item = _merge_extraction(item, extracted, country)
    if not item.get("phone"):
        item["phone"] = extract_labelled_phone(evidence)
    return item


async def enrich_publication(item: dict, country: str = "Argentina") -> dict:
    """Entrada simple para procesos que no mantienen un cliente HTTP compartido."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NetHolmes/1.0)"}
    async with httpx.AsyncClient(headers=headers) as client:
        await add_image_ocr(item, client, country)
    return await enrich_publication_with_ai(item, country)

