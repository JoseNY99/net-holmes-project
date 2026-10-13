"""Esquemas Pydantic para marcas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from schemas.product import ProductResponse


# ---------- Entrada ----------

class CuentaOficialBase(BaseModel):
    plataforma: str
    handle_oficial: str

class BrandCreate(BaseModel):
    nombre: str
    descripcion: str | None = None
    cuentas_oficiales: list[CuentaOficialBase] = []


class BrandUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    cuentas_oficiales: list[CuentaOficialBase] | None = None


# ---------- Salida ----------

class CuentaOficialResponse(CuentaOficialBase):
    id: int
    marca_id: int
    model_config = ConfigDict(from_attributes=True)

class BrandResponse(BaseModel):
    id: int
    nombre: str
    descripcion: str | None = None
    estado: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    products: list[ProductResponse] = []
    cuentas_oficiales: list[CuentaOficialResponse] = []

    model_config = ConfigDict(from_attributes=True)
