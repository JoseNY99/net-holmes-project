from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from config import settings
from middleware.auth_middleware import get_current_user
from models.user import User
import dotenv
import os

router = APIRouter(prefix="/api/settings", tags=["Settings"])

class WhatsAppSettingsUpdate(BaseModel):
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_business_account_id: Optional[str] = None
    whatsapp_verify_token: Optional[str] = None

@router.get("/whatsapp")
def get_whatsapp_settings(current_user: User = Depends(get_current_user)):
    if current_user.rol != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
        
    # Enmascarar el access token por seguridad (e.g. EAAG...xyz)
    masked_token = None
    if settings.WHATSAPP_ACCESS_TOKEN and len(settings.WHATSAPP_ACCESS_TOKEN) > 8:
        masked_token = f"{settings.WHATSAPP_ACCESS_TOKEN[:4]}...{settings.WHATSAPP_ACCESS_TOKEN[-4:]}"
    elif settings.WHATSAPP_ACCESS_TOKEN:
        masked_token = "***"
        
    return {
        "whatsapp_access_token": masked_token,
        "whatsapp_phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID,
        "whatsapp_business_account_id": settings.WHATSAPP_BUSINESS_ACCOUNT_ID,
        "whatsapp_verify_token": settings.WHATSAPP_VERIFY_TOKEN
    }

@router.post("/whatsapp")
def update_whatsapp_settings(data: WhatsAppSettingsUpdate, current_user: User = Depends(get_current_user)):
    if current_user.rol != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
        
    env_file = ".env"
    
    # Asegurarnos que el archivo existe
    if not os.path.exists(env_file):
        open(env_file, 'a').close()
        
    if data.whatsapp_access_token:
        # Solo guardar si no viene enmascarado (para evitar que se sobreescriba con "EAAG...x9Z")
        if "..." not in data.whatsapp_access_token:
            dotenv.set_key(env_file, "WHATSAPP_ACCESS_TOKEN", data.whatsapp_access_token)
            settings.WHATSAPP_ACCESS_TOKEN = data.whatsapp_access_token
            
    if data.whatsapp_phone_number_id is not None:
        dotenv.set_key(env_file, "WHATSAPP_PHONE_NUMBER_ID", data.whatsapp_phone_number_id)
        settings.WHATSAPP_PHONE_NUMBER_ID = data.whatsapp_phone_number_id
        
    if data.whatsapp_business_account_id is not None:
        dotenv.set_key(env_file, "WHATSAPP_BUSINESS_ACCOUNT_ID", data.whatsapp_business_account_id)
        settings.WHATSAPP_BUSINESS_ACCOUNT_ID = data.whatsapp_business_account_id
        
    if data.whatsapp_verify_token is not None:
        dotenv.set_key(env_file, "WHATSAPP_VERIFY_TOKEN", data.whatsapp_verify_token)
        settings.WHATSAPP_VERIFY_TOKEN = data.whatsapp_verify_token
        
    return {"status": "ok", "message": "Configuración de WhatsApp actualizada correctamente"}
