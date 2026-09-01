"""
Middleware de autenticación.
Provee dependencias de FastAPI para proteger endpoints con JWT.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.user import User

# Esquema de seguridad Bearer
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Extrae y valida el token JWT del header Authorization."""
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: int | None = payload.get("sub")
        session_id: str | None = payload.get("session_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise credentials_exception

    # Validación de Sesión Única (Single Device Active Session)
    if user.session_token and session_id and user.session_token != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada: Se ha iniciado sesión desde otro dispositivo o navegador.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Verifica que el usuario autenticado tenga rol de admin o sup_admin."""
    if current_user.rol not in ("admin", "sup_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return current_user


def require_sup_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Verifica que el usuario autenticado tenga rol de sup_admin exclusivamente."""
    if current_user.rol != "sup_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de Super Administrador (SUP_ADMIN)",
        )
    return current_user
