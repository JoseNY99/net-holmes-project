"""Router de usuarios."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.user import UserResponse, UserCreateAdmin, UserUpdate
from services import user_service
from middleware.auth_middleware import require_admin

router = APIRouter(prefix="/api/users", tags=["Usuarios"])

@router.get("/", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Lista todos los usuarios (solo administradores)."""
    return user_service.get_users(db)

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreateAdmin,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Crea un nuevo usuario respetando jerarquía de roles."""
    return user_service.create_user(db, user_data, _admin)

@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Actualiza datos básicos de un usuario respetando jerarquía."""
    return user_service.update_user(db, user_id, user_data, _admin)

@router.patch("/{user_id}/toggle", response_model=UserResponse)
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Alterna el estado activo de un usuario respetando jerarquía."""
    return user_service.toggle_user_status(db, user_id, _admin)

@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Elimina permanentemente a un usuario si la jerarquía lo permite."""
    return user_service.delete_user(db, user_id, _admin)
