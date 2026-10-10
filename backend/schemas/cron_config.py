from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class CronConfigBase(BaseModel):
    is_active: bool = False
    hora: int = Field(ge=0, le=23, default=2)
    minuto: int = Field(ge=0, le=59, default=0)
    plataformas_activas: str = '["mercadolibre", "facebook", "instagram", "tiktok"]'
    marcas_seleccionadas: str = '[]'
    provincias_seleccionadas: str = '["Buenos Aires"]'
    limite_extraccion: int = Field(ge=1, le=100, default=10) # Deprecated
    limite_extraccion_fb: int = Field(ge=1, le=100, default=10)
    limite_extraccion_ig: int = Field(ge=1, le=100, default=10)
    limite_extraccion_tt: int = Field(ge=1, le=100, default=10)
    limite_extraccion_ml: int = Field(ge=1, le=100, default=10)
    proveedor: str = Field(default="apify")
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None

class CronConfigUpdate(CronConfigBase):
    pass

class CronConfigResponse(CronConfigBase):
    id: int
    is_running: bool
    last_run: Optional[datetime]
    last_run_status: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
