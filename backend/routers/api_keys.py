"""Router FastAPI para gestión de API Keys en Base de Datos."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from database import get_db
from middleware.auth_middleware import require_admin
from services import api_key_service

router = APIRouter(prefix="/api/api-keys", tags=["API Keys Management"])

class ApiKeyUpsertRequest(BaseModel):
    service_name: str
    api_key: Optional[str] = ""
    description: Optional[str] = None
    is_active: Optional[bool] = True
    extra_config: Optional[Dict[str, Any]] = None

class ApiKeyTestRequest(BaseModel):
    api_key: Optional[str] = None

@router.get("")
def get_all_keys(db: Session = Depends(get_db), admin=Depends(require_admin)):
    """Retorna la lista de todos los servicios y sus API Keys (enmascaradas)."""
    return api_key_service.list_all_keys(db)

@router.post("")
def save_api_key(req: ApiKeyUpsertRequest, db: Session = Depends(get_db), admin=Depends(require_admin)):
    """Crea o actualiza una API key para un servicio."""
    try:
        updated = api_key_service.upsert_api_key(
            db, 
            service_name=req.service_name, 
            api_key=req.api_key, 
            description=req.description, 
            is_active=req.is_active, 
            extra_config=req.extra_config
        )
        return {
            "success": True,
            "message": f"API Key para '{req.service_name}' guardada correctamente en la Base de Datos.",
            "service_name": updated.service_name,
            "is_active": updated.is_active
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando API key: {str(e)}")

@router.delete("/{service_name}")
def remove_api_key(service_name: str, db: Session = Depends(get_db), admin=Depends(require_admin)):
    """Elimina la API key de la base de datos para ese servicio."""
    success = api_key_service.delete_api_key(db, service_name)
    if not success:
        raise HTTPException(status_code=404, detail="No se encontró configuración en DB para este servicio.")
    return {"success": True, "message": f"Configuración en DB eliminada para '{service_name}'."}

@router.post("/test/{service_name}")
async def test_key(service_name: str, req: Optional[ApiKeyTestRequest] = None, db: Session = Depends(get_db), admin=Depends(require_admin)):
    """Realiza un test de conectividad en vivo con el proveedor."""
    key_override = req.api_key if req else None
    result = await api_key_service.test_service_connection(service_name, key_override=key_override, db=db)
    return result