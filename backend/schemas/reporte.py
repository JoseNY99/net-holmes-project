from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, model_validator
from decimal import Decimal

from schemas.perfil_investigacion import PerfilResponse
from schemas.platform_data import PlatformDataPayload

class ReporteBase(BaseModel):
    pais: Optional[str] = "Argentina"
    referencia_interna: Optional[str] = None
    codigo_interno: Optional[str] = None
    tipo_informe: Optional[str] = "INTELIGENCIA"
    numero_caso_cliente: Optional[str] = None
    codigo_marca: Optional[str] = None
    producto_catalogo: Optional[str] = None
    marca_afectada: Optional[str] = None
    plataforma: Optional[str] = None
    titular_cuenta: Optional[str] = None
    url_evidencia: Optional[str] = None
    descripcion_post: Optional[str] = None
    precio_publico: Optional[Decimal] = None
    moneda: Optional[str] = "ARS"
    direccion_publica: Optional[str] = None
    telefono_publico: Optional[str] = None
    seguidores_infractor: Optional[int] = None
    estado: Optional[str] = "Pendiente"

class ReporteCreate(ReporteBase):
    platform_data: Optional[PlatformDataPayload] = None

class ReporteUpdate(BaseModel):
    estado: Optional[str] = None

class ReporteQuickEdit(BaseModel):
    precio_publico: Optional[float] = None
    moneda: Optional[str] = None
    telefono_publico: Optional[str] = None
    direccion_publica: Optional[str] = None
    descripcion_post: Optional[str] = None
    titular_cuenta: Optional[str] = None
    estado: Optional[str] = None
    tipo_informe: Optional[str] = None
    numero_caso_cliente: Optional[str] = None

class ReporteResponse(ReporteBase):
    id: int
    relevamiento_completitud: int = 0
    fecha_captura: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class ReporteDetail(ReporteResponse):
    perfil: Optional[PerfilResponse] = None
    platform_data: Optional[PlatformDataPayload] = None
    evidence_image_url: Optional[str] = None

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
