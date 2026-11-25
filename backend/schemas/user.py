"""Esquemas Pydantic para usuarios y autenticación."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, ConfigDict


# ---------- Entrada ----------

class UserCreate(BaseModel):
    nombre: str
    apellido: str
    celular: str | None = None
    ci: str | None = None
    correo: EmailStr
    password: str


class UserLogin(BaseModel):
    correo: EmailStr
    password: str

class UserCreateAdmin(UserCreate):
    rol: Literal["sup_admin", "admin", "analista", "cliente"] = "analista"


class UserUpdate(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
    celular: str | None = None
    ci: str | None = None
    correo: EmailStr | None = None
    rol: Literal["sup_admin", "admin", "analista", "cliente"] | None = None
    password: str | None = None


# ---------- Salida ----------

class UserResponse(BaseModel):
    id: int
    nombre: str
    apellido: str
    celular: str | None = None
    ci: str | None = None
    correo: str
    rol: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
