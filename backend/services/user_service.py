"""Servicio CRUD para usuarios (Admin ABM)."""

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from models.user import User
from schemas.user import UserCreateAdmin, UserUpdate
from services.auth_service import hash_password

def get_users(db: Session) -> list[User]:
    """Obtiene todos los usuarios."""
    return db.query(User).order_by(User.created_at.desc()).all()

def get_user(db: Session, user_id: int) -> User:
    """Obtiene un usuario por ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    return user

def create_user(db: Session, user_data: UserCreateAdmin, current_user: User) -> User:
    """Crea un nuevo usuario desde el panel de admin respetando jerarquía."""
    from sqlalchemy import func
    # Solo SUP_ADMIN puede crear ADMIN o SUP_ADMIN
    if user_data.rol in ("admin", "sup_admin") and current_user.rol != "sup_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un Super Administrador puede crear usuarios con rol Administrador o Super Admin.",
        )
        
    clean_correo = (user_data.correo or "").strip().lower()
    existing = db.query(User).filter(func.lower(func.trim(User.correo)) == clean_correo).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con este correo electrónico",
        )
        
    clean_password = (user_data.password or "").strip()
    user = User(
        nombre=user_data.nombre.strip(),
        apellido=user_data.apellido.strip(),
        celular=user_data.celular,
        ci=user_data.ci,
        correo=clean_correo,
        password_hash=hash_password(clean_password),
        rol=user_data.rol,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def update_user(db: Session, user_id: int, user_data: UserUpdate, current_user: User) -> User:
    """Actualiza datos de un usuario respetando la jerarquía de roles."""
    target_user = get_user(db, user_id)
    
    # 1. Nadie (ni siquiera otro sup_admin) puede degradar o editar a un SUP_ADMIN si no es el mismo
    if target_user.rol == "sup_admin" and current_user.id != target_user.id and current_user.rol != "sup_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pueden realizar modificaciones sobre una cuenta Super Administrador.",
        )

    # 2. ADMIN no puede editar a otros ADMIN
    if target_user.rol == "admin" and current_user.rol == "admin" and current_user.id != target_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un Administrador no puede editar a otros Administradores.",
        )

    # 3. ADMIN no puede asignar rol admin o sup_admin
    if user_data.rol and user_data.rol in ("admin", "sup_admin") and current_user.rol != "sup_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un Super Administrador puede otorgar roles de Administrador o Super Admin.",
        )
    
    update_data = user_data.model_dump(exclude_unset=True)
    if "correo" in update_data and update_data["correo"]:
        update_data["correo"] = update_data["correo"].strip().lower()
        
    if "password" in update_data and update_data["password"]:
        clean_new_pass = str(update_data.pop("password")).strip()
        if clean_new_pass:
            target_user.password_hash = hash_password(clean_new_pass)
        
    for key, value in update_data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(target_user, key, value)
        
    db.commit()
    db.refresh(target_user)
    return target_user

def toggle_user_status(db: Session, user_id: int, current_user: User) -> User:
    """Alterna is_active (baja lógica) respetando la jerarquía de roles."""
    target_user = get_user(db, user_id)
    
    # 1. SUP_ADMIN nunca puede ser desactivado
    if target_user.rol == "sup_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Las cuentas Super Administrador (SUP_ADMIN) están blindadas y no pueden ser desactivadas.",
        )
        
    # 2. No se puede desactivar a uno mismo
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta activa.",
        )
        
    # 3. ADMIN no puede desactivar a otros ADMIN ni a SUP_ADMIN
    if target_user.rol in ("admin", "sup_admin") and current_user.rol != "sup_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un Super Administrador puede suspender a usuarios con rol Administrador.",
        )
        
    target_user.is_active = not target_user.is_active
    db.commit()
    db.refresh(target_user)
    return target_user

def delete_user(db: Session, user_id: int, current_user: User) -> dict:
    """Elimina permanentemente a un usuario. Exclusivo para SUP_ADMIN."""
    # 0. Exclusivo para SUP_ADMIN
    if current_user.rol != "sup_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: Únicamente el Super Administrador (SUP_ADMIN) tiene autorización para eliminar cuentas de usuario.",
        )

    target_user = get_user(db, user_id)
    
    # 1. SUP_ADMIN nunca puede ser borrado
    if target_user.rol == "sup_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Las cuentas Super Administrador (SUP_ADMIN) están blindadas y no pueden ser eliminadas.",
        )
        
    # 2. No se puede borrar a uno mismo
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta en sesión.",
        )
        
    db.delete(target_user)
    db.commit()
    return {"status": "ok", "message": f"Usuario {target_user.correo} eliminado con éxito."}
