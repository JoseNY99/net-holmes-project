from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class PerfilUpdate(BaseModel):
    pais: Optional[str] = None
    dni_cedula: Optional[str] = None
    cuit_cuil_ruc: Optional[str] = None
    banco: Optional[str] = None
    alias_bancario: Optional[str] = None
    cvu_cbu: Optional[str] = None
    email: Optional[str] = None
    direccion_exacta: Optional[str] = None
    telefono_confirmado: Optional[str] = None
    precio_final: Optional[str] = None

class PerfilResponse(PerfilUpdate):
    id: int
    reporte_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
