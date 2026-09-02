"""Servicio para consulta y gestión dinámica de API Keys desde la base de datos."""

import json
import time
import httpx
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import SessionLocal
from models.api_key_setting import ApiKeySetting
from config import settings
from services.cron_logger import cron_logger

SUPPORTED_SERVICES = {
    "serper": {
        "name": "Serper.dev (Google Dorking OSINT)",
        "env_fallback": "SERPER_API_KEY",
        "doc_url": "https://serper.dev",
        "description": "Búsqueda en Google de publicaciones de Facebook, Instagram y TikTok."
    },
    "apify": {
        "name": "Apify Motor",
        "env_fallback": "APIFY_API_TOKEN",
        "doc_url": "https://apify.com",
        "description": "Scraping avanzado de perfiles y redes sociales vía Actors de Apify."
    },
    "rapidapi": {
        "name": "RapidAPI (Instagram Scraper)",
        "env_fallback": "RAPIDAPI_KEY",
        "doc_url": "https://rapidapi.com",
        "description": "Extracción de perfiles y publicaciones de Instagram vía RapidAPI."
    },
    "cerebras": {
        "name": "Cerebras Cloud (LLM NLP)",
        "env_fallback": "CEREBRAS_API_KEY",
        "doc_url": "https://cerebras.ai",
        "description": "Inferencia ultra-rápida (Llama 3.3 70B) para extracción de entidades y chat honeypot."
    },
    "deepseek": {
        "name": "DeepSeek API (LLM Fallback)",
        "env_fallback": "DEEPSEEK_API_KEY",
        "doc_url": "https://deepseek.com",
        "description": "Modelo de lenguaje alternativo de respaldo para análisis profundo."
    },
    "meta_whatsapp": {
        "name": "WhatsApp Cloud API (Meta)",
        "env_fallback": "WHATSAPP_ACCESS_TOKEN",
        "doc_url": "https://developers.facebook.com",
        "description": "Token de acceso a WhatsApp Cloud API para el actor honeypot."
    }
}

def mask_api_key(key: str | None) -> str:
    """Enmascara una API Key para visualización segura (ej: sk-1234...5678)."""
    if not key or len(key.strip()) == 0:
        return ""
    k = key.strip()
    if len(k) <= 8:
        return "****"
    return f"{k[:4]}...{k[-4:]}"

def get_active_api_key(service_name: str, db: Session = None) -> str | None:
    """
    Obtiene la API Key activa para el servicio dado.
    Prioridad: 
    1. Base de Datos (si está activa y no vacía)
    2. Variable de Entorno (.env / settings)
    """
    srv = service_name.lower().strip()
    close_db = False
    
    if db is None:
        db = SessionLocal()
        close_db = True
        
    try:
        db_key = db.query(ApiKeySetting).filter(
            ApiKeySetting.service_name == srv,
            ApiKeySetting.is_active == True
        ).first()
        
        if db_key and db_key.api_key and len(db_key.api_key.strip()) > 0:
            return db_key.api_key.strip()
            
    except Exception as e:
        cron_logger.log(f"⚠️ [API Key Service] Error consultando BD para {srv}: {e}")
    finally:
        if close_db:
            db.close()

    # Fallback a settings / .env
    fallback_attr = SUPPORTED_SERVICES.get(srv, {}).get("env_fallback")
    if fallback_attr:
        env_val = getattr(settings, fallback_attr, None)
        if env_val and len(str(env_val).strip()) > 0:
            return str(env_val).strip()
            
    return None

def list_all_keys(db: Session) -> list[dict]:
    """Retorna la lista de todos los servicios soportados con su estado y llave enmascarada."""
    db_keys = {k.service_name: k for k in db.query(ApiKeySetting).all()}
    results = []

    for srv_id, srv_meta in SUPPORTED_SERVICES.items():
        db_entry = db_keys.get(srv_id)
        effective_key = get_active_api_key(srv_id, db=db)
        
        is_from_db = bool(db_entry and db_entry.api_key)
        is_configured = bool(effective_key)
        
        extra_cfg = {}
        if db_entry and db_entry.extra_config:
            try:
                extra_cfg = json.loads(db_entry.extra_config)
            except:
                pass

        results.append({
            "service_name": srv_id,
            "display_name": srv_meta["name"],
            "description": db_entry.description if (db_entry and db_entry.description) else srv_meta["description"],
            "doc_url": srv_meta["doc_url"],
            "is_active": db_entry.is_active if db_entry else True,
            "is_configured": is_configured,
            "is_from_db": is_from_db,
            "masked_key": mask_api_key(effective_key),
            "extra_config": extra_cfg,
            "updated_at": db_entry.updated_at.isoformat() if (db_entry and db_entry.updated_at) else None
        })

    return results

def upsert_api_key(db: Session, service_name: str, api_key: str, description: str = None, is_active: bool = True, extra_config: dict = None) -> ApiKeySetting:
    """Inserta o actualiza una API key en la base de datos."""
    srv = service_name.lower().strip()
    db_entry = db.query(ApiKeySetting).filter(ApiKeySetting.service_name == srv).first()

    extra_str = json.dumps(extra_config) if extra_config is not None else None

    if db_entry:
        if api_key is not None and len(api_key.strip()) > 0:
            db_entry.api_key = api_key.strip()
        db_entry.description = description or db_entry.description
        db_entry.is_active = is_active
        if extra_str is not None:
            db_entry.extra_config = extra_str
        db_entry.updated_at = datetime.now(timezone.utc)
    else:
        db_entry = ApiKeySetting(
            service_name=srv,
            api_key=api_key.strip() if api_key else "",
            description=description or SUPPORTED_SERVICES.get(srv, {}).get("description", ""),
            is_active=is_active,
            extra_config=extra_str
        )
        db.add(db_entry)

    db.commit()
    db.refresh(db_entry)
    return db_entry

def delete_api_key(db: Session, service_name: str) -> bool:
    """Elimina la llave almacenada en base de datos para ese servicio."""
    srv = service_name.lower().strip()
    db_entry = db.query(ApiKeySetting).filter(ApiKeySetting.service_name == srv).first()
    if db_entry:
        db.delete(db_entry)
        db.commit()
        return True
    return False

async def test_service_connection(service_name: str, key_override: str = None, db: Session = None) -> dict:
    """Ejecuta un test de conectividad en vivo con el proveedor para validar la API Key."""
    srv = service_name.lower().strip()
    key = key_override or get_active_api_key(srv, db=db)

    if not key:
        return {"success": False, "message": "No hay ninguna API Key configurada para este servicio.", "latency_ms": 0}

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if srv == "serper":
                resp = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": key, "Content-Type": "application/json"},
                    json={"q": "test", "num": 1}
                )
                latency = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    data = resp.json()
                    credits = data.get("credits", "N/A")
                    return {"success": True, "message": f"Conexión exitosa a Serper.dev ({latency}ms). Créditos usados/disponibles: {credits}", "latency_ms": latency}
                else:
                    return {"success": False, "message": f"Error Serper ({resp.status_code}): {resp.text}", "latency_ms": latency}

            elif srv == "apify":
                resp = await client.get(
                    f"https://api.apify.com/v2/users/me?token={key}"
                )
                latency = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    username = data.get("username", "Desconocido")
                    return {"success": True, "message": f"Conexión exitosa a Apify ({latency}ms). Usuario: @{username}", "latency_ms": latency}
                else:
                    return {"success": False, "message": f"Error Apify ({resp.status_code}): {resp.text}", "latency_ms": latency}

            elif srv == "rapidapi":
                resp = await client.get(
                    "https://instagram-scraper-api2.p.rapidapi.com/v1/info?username_or_id_or_url=instagram",
                    headers={
                        "x-rapidapi-key": key,
                        "x-rapidapi-host": "instagram-scraper-api2.p.rapidapi.com"
                    }
                )
                latency = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    return {"success": True, "message": f"Conexión exitosa a RapidAPI Instagram ({latency}ms).", "latency_ms": latency}
                else:
                    return {"success": False, "message": f"Error RapidAPI ({resp.status_code}): {resp.text}", "latency_ms": latency}

            elif srv == "cerebras":
                resp = await client.get(
                    "https://api.cerebras.ai/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                latency = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    return {"success": True, "message": f"Conexión exitosa a Cerebras Cloud ({latency}ms). Modelos disponibles.", "latency_ms": latency}
                else:
                    return {"success": False, "message": f"Error Cerebras ({resp.status_code}): {resp.text}", "latency_ms": latency}

            elif srv == "deepseek":
                resp = await client.get(
                    "https://api.deepseek.com/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                latency = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    return {"success": True, "message": f"Conexión exitosa a DeepSeek API ({latency}ms).", "latency_ms": latency}
                else:
                    return {"success": False, "message": f"Error DeepSeek ({resp.status_code}): {resp.text}", "latency_ms": latency}

            elif srv == "meta_whatsapp":
                resp = await client.get(
                    "https://graph.facebook.com/v21.0/me",
                    headers={"Authorization": f"Bearer {key}"}
                )
                latency = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    data = resp.json()
                    name = data.get("name", "Meta App")
                    return {"success": True, "message": f"Conexión exitosa a Meta Cloud ({latency}ms). App: {name}", "latency_ms": latency}
                else:
                    return {"success": False, "message": f"Error Meta API ({resp.status_code}): {resp.text}", "latency_ms": latency}

            else:
                return {"success": True, "message": f"Servicio '{srv}' registrado.", "latency_ms": 0}

    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return {"success": False, "message": f"Error de conexión / Timeout: {str(e)}", "latency_ms": latency}