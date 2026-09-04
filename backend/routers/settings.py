import json
import os
import dotenv
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from middleware.auth_middleware import require_admin
from models.user import User
from models.api_key_setting import ApiKeySetting
from services.cron_logger import cron_logger

router = APIRouter(prefix="/api/settings", tags=["Settings"])

class WhatsAppSettingsUpdate(BaseModel):
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_business_account_id: Optional[str] = None
    whatsapp_verify_token: Optional[str] = None

@router.get("/whatsapp")
def get_whatsapp_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Obtiene la configuración de WhatsApp, priorizando la Base de Datos."""
    setting = db.query(ApiKeySetting).filter(ApiKeySetting.service_name == "meta_whatsapp").first()
    
    access_token = None
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    business_account_id = settings.WHATSAPP_BUSINESS_ACCOUNT_ID
    verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", None) or "operativa_123"
    
    if setting:
        if setting.api_key:
            access_token = setting.api_key
        if setting.extra_config:
            try:
                cfg = json.loads(setting.extra_config)
                phone_number_id = cfg.get("whatsapp_phone_number_id") or phone_number_id
                business_account_id = cfg.get("whatsapp_business_account_id") or business_account_id
                verify_token = cfg.get("whatsapp_verify_token") or verify_token
            except Exception:
                pass
    elif settings.WHATSAPP_ACCESS_TOKEN:
        access_token = settings.WHATSAPP_ACCESS_TOKEN

    # Enmascarar el access token por seguridad
    masked_token = None
    if access_token and len(access_token) > 8:
        masked_token = f"{access_token[:4]}...{access_token[-4:]}"
    elif access_token:
        masked_token = "***"
        
    return {
        "whatsapp_access_token": masked_token,
        "whatsapp_phone_number_id": phone_number_id or "",
        "whatsapp_business_account_id": business_account_id or "",
        "whatsapp_verify_token": verify_token or "operativa_123"
    }

@router.post("/whatsapp")
def update_whatsapp_settings(
    data: WhatsAppSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Guarda toda la configuración de WhatsApp directamente en la Base de Datos (PostgreSQL)."""
    setting = db.query(ApiKeySetting).filter(ApiKeySetting.service_name == "meta_whatsapp").first()
    if not setting:
        setting = ApiKeySetting(
            service_name="meta_whatsapp",
            description="Credenciales WhatsApp Cloud API",
            is_active=True,
            extra_config="{}"
        )
        db.add(setting)

    extra = {}
    if setting.extra_config:
        try:
            extra = json.loads(setting.extra_config)
        except Exception:
            extra = {}

    # Actualizar token si no viene enmascarado
    if data.whatsapp_access_token and "..." not in data.whatsapp_access_token and "***" not in data.whatsapp_access_token:
        clean_token = data.whatsapp_access_token.strip()
        if clean_token:
            setting.api_key = clean_token
            settings.WHATSAPP_ACCESS_TOKEN = clean_token

    if data.whatsapp_phone_number_id is not None:
        clean_phone = data.whatsapp_phone_number_id.strip()
        extra["whatsapp_phone_number_id"] = clean_phone
        settings.WHATSAPP_PHONE_NUMBER_ID = clean_phone

    if data.whatsapp_business_account_id is not None:
        clean_biz = data.whatsapp_business_account_id.strip()
        extra["whatsapp_business_account_id"] = clean_biz
        settings.WHATSAPP_BUSINESS_ACCOUNT_ID = clean_biz

    if data.whatsapp_verify_token is not None:
        clean_verify = data.whatsapp_verify_token.strip()
        extra["whatsapp_verify_token"] = clean_verify
        settings.WHATSAPP_VERIFY_TOKEN = clean_verify

    setting.extra_config = json.dumps(extra)
    setting.is_active = True
    db.commit()
    db.refresh(setting)

    cron_logger.log(f"[Settings] ✅ Configuración de WhatsApp guardada en Base de Datos por {current_user.correo}.")

    # Sincronización secundaria opcional con .env sin romper si no hay permisos de archivo
    try:
        env_file = ".env"
        if os.path.exists(env_file):
            if setting.api_key:
                dotenv.set_key(env_file, "WHATSAPP_ACCESS_TOKEN", setting.api_key)
            if "whatsapp_phone_number_id" in extra:
                dotenv.set_key(env_file, "WHATSAPP_PHONE_NUMBER_ID", extra["whatsapp_phone_number_id"])
            if "whatsapp_business_account_id" in extra:
                dotenv.set_key(env_file, "WHATSAPP_BUSINESS_ACCOUNT_ID", extra["whatsapp_business_account_id"])
            if "whatsapp_verify_token" in extra:
                dotenv.set_key(env_file, "WHATSAPP_VERIFY_TOKEN", extra["whatsapp_verify_token"])
    except Exception as e:
        cron_logger.log(f"[Settings] ⚠️ Aviso: No se pudo escribir en .env (ignorable, datos en DB): {e}")

    return {"status": "ok", "message": "Configuración de WhatsApp guardada correctamente en la Base de Datos"}


class WhatsAppTestRequest(BaseModel):
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None

@router.post("/whatsapp/test")
async def test_whatsapp_connection_endpoint(
    data: WhatsAppTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Prueba en tiempo real la validez del token y el Phone Number ID con Meta Graph API."""
    from services.api_key_service import test_service_connection
    token = data.whatsapp_access_token
    # Si viene enmascarado o vacío, buscar el real en DB
    if not token or "..." in token or "***" in token or "••••" in token:
        setting = db.query(ApiKeySetting).filter(ApiKeySetting.service_name == "meta_whatsapp").first()
        if setting and setting.api_key:
            token = setting.api_key
        elif settings.WHATSAPP_ACCESS_TOKEN:
            token = settings.WHATSAPP_ACCESS_TOKEN

    if not token:
        return {"success": False, "message": "No hay un WhatsApp Access Token configurado para probar.", "latency_ms": 0}

    phone_id = data.whatsapp_phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
    res = await test_service_connection("meta_whatsapp", token, {"whatsapp_phone_number_id": phone_id})
    return res

