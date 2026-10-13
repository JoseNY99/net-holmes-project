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
        "whatsapp_verify_token": verify_token or "operativa_123",
        "is_configured": bool(access_token and phone_number_id)
    }

@router.post("/whatsapp")
def update_whatsapp_settings(
    data: WhatsAppSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Guarda toda la configuración de WhatsApp directamente en la Base de Datos (PostgreSQL), validando que no esté vacía."""
    setting = db.query(ApiKeySetting).filter(ApiKeySetting.service_name == "meta_whatsapp").first()
    
    # Extraer candidatos
    token_candidate = (data.whatsapp_access_token or "").strip()
    phone_candidate = (data.whatsapp_phone_number_id or "").strip()

    # Validar que no se guarden registros vacíos
    is_masked = ("..." in token_candidate or "***" in token_candidate or "••••" in token_candidate)
    has_existing_token = bool(setting and setting.api_key) or bool(settings.WHATSAPP_ACCESS_TOKEN)

    if not is_masked and not token_candidate and not has_existing_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pueden guardar campos vacíos. Debe ingresar al menos el WhatsApp Access Token y el Phone Number ID. Si desea eliminar las credenciales, use 'Borrar Datos'."
        )

    if not phone_candidate and not (setting and setting.extra_config and "whatsapp_phone_number_id" in setting.extra_config):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El Phone Number ID es obligatorio para operar el bot de WhatsApp. Ingrese el ID numérico proporcionado por Meta."
        )

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
    if token_candidate and not is_masked:
        setting.api_key = token_candidate
        settings.WHATSAPP_ACCESS_TOKEN = token_candidate

    if data.whatsapp_phone_number_id is not None and phone_candidate:
        extra["whatsapp_phone_number_id"] = phone_candidate
        settings.WHATSAPP_PHONE_NUMBER_ID = phone_candidate

    if data.whatsapp_business_account_id is not None:
        clean_biz = data.whatsapp_business_account_id.strip()
        extra["whatsapp_business_account_id"] = clean_biz
        settings.WHATSAPP_BUSINESS_ACCOUNT_ID = clean_biz

    if data.whatsapp_verify_token is not None:
        clean_verify = data.whatsapp_verify_token.strip()
        if clean_verify:
            extra["whatsapp_verify_token"] = clean_verify
            settings.WHATSAPP_VERIFY_TOKEN = clean_verify

    setting.extra_config = json.dumps(extra)
    setting.is_active = True
    db.commit()
    db.refresh(setting)

    cron_logger.log(f"[Settings]  Configuración de WhatsApp guardada en Base de Datos por {current_user.correo}.")

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
        cron_logger.log(f"[Settings]  Aviso: No se pudo escribir en .env (ignorable, datos en DB): {e}")

    return {"status": "ok", "message": "Configuración de WhatsApp guardada correctamente en la Base de Datos"}


@router.delete("/whatsapp")
def delete_whatsapp_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Elimina las credenciales de WhatsApp de la base de datos y resetea la configuración."""
    setting = db.query(ApiKeySetting).filter(ApiKeySetting.service_name == "meta_whatsapp").first()
    if setting:
        db.delete(setting)
        db.commit()

    # Limpiar configuración en memoria
    settings.WHATSAPP_ACCESS_TOKEN = None
    settings.WHATSAPP_PHONE_NUMBER_ID = None
    settings.WHATSAPP_BUSINESS_ACCOUNT_ID = None

    cron_logger.log(f"[Settings] 🗑️ Credenciales de WhatsApp eliminadas de la BD por {current_user.correo}.")

    return {
        "status": "ok",
        "message": "Credenciales de WhatsApp eliminadas correctamente de la base de datos."
    }


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

    phone_id = data.whatsapp_phone_number_id
    if (not phone_id or "..." in phone_id) and setting and setting.extra_config:
        try:
            cfg = json.loads(setting.extra_config)
            phone_id = cfg.get("whatsapp_phone_number_id") or cfg.get("phone_number_id")
        except Exception:
            pass

    if not phone_id:
        phone_id = settings.WHATSAPP_PHONE_NUMBER_ID

    res = await test_service_connection(
        service_name="meta_whatsapp",
        key_override=token,
        extra_config={"whatsapp_phone_number_id": phone_id},
        db=db
    )
    return res

