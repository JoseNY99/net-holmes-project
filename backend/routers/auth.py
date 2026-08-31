"""Router de autenticación: registro, login y perfil del usuario."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse
from services.auth_service import hash_password, verify_password, create_access_token
from middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Registra un nuevo usuario. El primer usuario registrado obtiene rol 'admin'."""
    from sqlalchemy import func
    clean_correo = (user_data.correo or "").strip().lower()
    existing = db.query(User).filter(func.lower(func.trim(User.correo)) == clean_correo).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con este correo",
        )

    # El primer usuario del sistema recibe rol de administrador
    user_count = db.query(User).count()
    rol = "admin" if user_count == 0 else "analista"

    clean_password = (user_data.password or "").strip()
    user = User(
        nombre=user_data.nombre.strip(),
        apellido=user_data.apellido.strip(),
        celular=user_data.celular,
        ci=user_data.ci,
        correo=clean_correo,
        password_hash=hash_password(clean_password),
        rol=rol,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Inicia sesión con correo y contraseña, devuelve un token JWT."""
    from sqlalchemy import func
    clean_correo = (credentials.correo or "").strip().lower()
    clean_pass = credentials.password or ""
    
    user = db.query(User).filter(func.lower(func.trim(User.correo)) == clean_correo).first()
    if not user or not (verify_password(clean_pass, user.password_hash) or verify_password(clean_pass.strip(), user.password_hash)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada",
        )

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """Devuelve los datos del usuario autenticado."""
    return current_user
