import re
import json
import asyncio
import httpx
from typing import AsyncGenerator, Dict, Any, List
from datetime import datetime, timezone

from config import settings
from services.cron_logger import cron_logger
from services.image_persistence import limpiar_url_canonica

class CertstreamScanner:
    """
    Escáner de Detección de Dominios Fraudulentos, Phishing y Tiendas Falsas.
    Combina logs de Transparencia de Certificados SSL (crt.sh) y Google Dorking para la Web Abierta,
    calculando similitud de marca y descartando dominios oficiales legítimos.
    """
    CRTSH_URL = "https://crt.sh/"

    OFFICIAL_TLDS_BLACKLIST = [
        "adidas.com", "adidas.com.ar", "adidas.cl", "adidas.com.br",
        "nike.com", "nike.com.ar", "puma.com", "puma.com.ar",
        "underarmour.com", "reebok.com", "newbalance.com",
        "mercadolibre.com", "mercadolibre.com.ar", "facebook.com", "instagram.com", "tiktok.com"
    ]

    def _is_official_domain(self, domain: str, brand_name: str) -> bool:
        d = domain.lower().strip()
        for off in self.OFFICIAL_TLDS_BLACKLIST:
            if d == off or d.endswith(f".{off}"):
                return True
        return False

    def _levenshtein(self, s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return self._levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    async def scan_brand_domains(
        self, brand_name: str, limit: int = 5
    ) -> AsyncGenerator[Dict[str, Any], None]:
        cron_logger.log(f"🛡️ [Certstream OSINT] Escaneando dominios fraudulentos y tiendas falsas para '{brand_name}'...")
        brand_clean = brand_name.lower().strip()
        seen_domains = set()
        count = 0

        # 1. Consulta a Certificate Transparency (crt.sh)
        try:
            params = {"q": f"%{brand_clean}%", "output": "json"}
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NetHolmes-BrandShield/1.0"}
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.CRTSH_URL, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for entry in data:
                        name_val = entry.get("name_value", "")
                        for raw_d in name_val.split("\n"):
                            d = raw_d.strip().lower().lstrip("*.")
                            if not d or d in seen_domains or self._is_official_domain(d, brand_clean):
                                continue

                            # Validar que contenga la marca o similitud
                            if brand_clean in d:
                                seen_domains.add(d)
                                url_target = f"https://{d}"
                                title = f"Tienda Falsa / Phishing Detectado: {d}"
                                desc = f"Certificado SSL emitido para dominio no oficial ({entry.get('issuer_name', 'CA')}). Posible tienda fraudulenta o réplicas."

                                yield {
                                    "plataforma": "web",
                                    "title": title[:200],
                                    "description": desc[:3000],
                                    "price": 0.0,
                                    "url": url_target,
                                    "image_urls": [],
                                    "seller_profile": {
                                        "name": d,
                                        "url": url_target,
                                    },
                                    "location": "Web / Argentina",
                                    "raw_data": json.dumps(entry)[:3000],
                                    "platform_data": {
                                        "seller_name": d,
                                        "seller_profile_url": url_target,
                                        "description_full": desc,
                                        "source_engine": "Certstream_SSL_Monitor",
                                    }
                                }
                                count += 1
                                if count >= limit:
                                    return
        except Exception as e:
            cron_logger.log(f" [Certstream] crt.sh no disponible temporalmente ({e}). Usando Dorking Web...")

        # 2. Dorking Web Abierta para Tiendas Falsas si faltan resultados
        if count < limit and settings.SERPER_API_KEY:
            try:
                dork_web = f'"{brand_name}" ("tienda online" OR "outlet" OR "zapatillas réplicas" OR "50% off") argentina -site:mercadolibre.com.ar -site:adidas.com* -site:nike.com* -site:facebook.com -site:instagram.com -site:tiktok.com'
                headers = {"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"}
                payload = {"q": dork_web, "gl": "ar", "hl": "es-419", "num": limit}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post("https://google.serper.dev/search", headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data.get("organic", []):
                            raw_link = item.get("link", "")
                            clean_link = limpiar_url_canonica(raw_link)
                            domain_match = re.search(r'https?://([^/]+)', clean_link)
                            if not domain_match:
                                continue
                            dom = domain_match.group(1).lower()
                            if dom in seen_domains or self._is_official_domain(dom, brand_clean):
                                continue

                            seen_domains.add(dom)
                            yield {
                                "plataforma": "web",
                                "title": item.get("title", f"Tienda no oficial: {dom}")[:200],
                                "description": item.get("snippet", "")[:3000],
                                "price": 0.0,
                                "url": clean_link,
                                "image_urls": [],
                                "seller_profile": {
                                    "name": dom,
                                    "url": clean_link,
                                },
                                "location": "Argentina",
                                "raw_data": json.dumps(item)[:3000],
                                "platform_data": {
                                    "seller_name": dom,
                                    "seller_profile_url": clean_link,
                                    "description_full": item.get("snippet", ""),
                                    "source_engine": "Web_Phishing_Dorking",
                                }
                            }
                            count += 1
                            if count >= limit:
                                return
            except Exception as ew:
                cron_logger.log(f" [Certstream Dorking] Error en búsqueda de tiendas web: {ew}")
