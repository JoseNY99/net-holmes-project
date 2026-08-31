from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, model_validator
from decimal import Decimal

from schemas.perfil_investigacion import PerfilResponse
from schemas.platform_data import PlatformDataPayload

class ReporteBase(BaseModel):
    pais: str
    referencia_interna: Optional[str] = None
    producto_catalogo: str
    marca_afectada: str
    plataforma: str
    titular_cuenta: str
    url_evidencia: str
    descripcion_post: Optional[str] = None
    precio_publico: Optional[Decimal] = None
    direccion_publica: Optional[str] = None
    telefono_publico: Optional[str] = None
    seguidores_infractor: Optional[int] = None
    estado: Optional[str] = "Pendiente"

class ReporteCreate(ReporteBase):
    platform_data: Optional[PlatformDataPayload] = None

class ReporteUpdate(BaseModel):
    estado: Optional[str] = None

class ReporteResponse(ReporteBase):
    id: int
    fecha_captura: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class ReporteDetail(ReporteResponse):
    perfil: Optional[PerfilResponse] = None
    platform_data: Optional[PlatformDataPayload] = None

    @model_validator(mode="wrap")
    @classmethod
    def _load_platform_data(cls, data, handler):
        # Si viene de un ORM object con _platform_data_obj, lo inyectamos
        pd_obj = None
        if hasattr(data, "_platform_data_obj"):
            pd_obj = data._platform_data_obj
        
        result = handler(data)
        
        if pd_obj and result.platform_data is None:
            try:
                result.platform_data = PlatformDataPayload.model_validate(pd_obj, from_attributes=True)
            except Exception:
                pass
        return result

class PaginatedReportes(BaseModel):
    items: List[ReporteResponse]
    total: int
