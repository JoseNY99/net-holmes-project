from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class PerfilUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dni_cedula: Optional[str] = None
    cuit_cuil_ruc: Optional[str] = None
    banco: Optional[str] = None
    alias_bancario: Optional[str] = None
    cvu_cbu: Optional[str] = None
    email: Optional[str] = None
    direccion_exacta: Optional[str] = None
    telefono_privado: Optional[str] = None
    precio_final_cotizado: Optional[str] = None
    
    # Aliases
    telefono_confirmado: Optional[str] = None
    precio_final: Optional[str] = None
    pais: Optional[str] = None

class PerfilResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: int
    reporte_id: int
    dni_cedula: Optional[str] = None
    cuit_cuil_ruc: Optional[str] = None
    banco: Optional[str] = None
    alias_bancario: Optional[str] = None
    cvu_cbu: Optional[str] = None
    email: Optional[str] = None
    direccion_exacta: Optional[str] = None
    telefono_privado: Optional[str] = None
    precio_final_cotizado: Optional[str] = None
    created_at: datetime
    updated_at: datetime
