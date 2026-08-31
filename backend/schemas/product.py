"""Esquemas Pydantic para productos."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ---------- Entrada ----------

class ProductCreate(BaseModel):
    nombre: str
    descripcion: str | None = None
    estado: str = "activa"


class ProductUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    estado: str | None = None


# ---------- Salida ----------

class ProductResponse(BaseModel):
    id: int
    brand_id: int
    nombre: str
    descripcion: str | None = None
    estado: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
