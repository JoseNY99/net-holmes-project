"""Router para Logs de Administrador y Memoria RAG."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from models.rag_memory import RagMemory
from middleware.auth_middleware import get_current_user, require_admin
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin/logs", tags=["Admin Logs RAG"])

class FlagRequest(BaseModel):
    reason: str

@router.post("/suspects/{suspect_id}/flag")
def flag_suspect(suspect_id: int, req: FlagRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """(Analistas) Marca un sospechoso como posible Falso Positivo."""
    # Desactivado en la Fase 2 actual
    return {"status": "ok", "message": "Funcionalidad heredada desactivada. Use el estado Descartado en su lugar."}

@router.get("/flags")
def get_flagged_suspects(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    """(Admin) Obtiene los sospechosos marcados como FP."""
    return []

@router.post("/flags/{suspect_id}/approve")
def approve_flag(suspect_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """(Admin) Aprueba un FP, entrena la RAG y descarta el sospechoso."""
    return {"status": "ok", "message": "Operación desactivada en Fase 2."}

@router.post("/flags/{suspect_id}/reject")
def reject_flag(suspect_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    """(Admin) Rechaza la bandera y quita la marca."""
    return {"status": "ok", "message": "Operación desactivada en Fase 2."}
