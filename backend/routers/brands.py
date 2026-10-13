"""Router de marcas y productos."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.brand import BrandCreate, BrandUpdate, BrandResponse
from schemas.product import ProductCreate, ProductUpdate, ProductResponse
from services import brand_service
from middleware.auth_middleware import get_current_user, require_admin
from fastapi import HTTPException
from services.cron_service import get_cron_config

def check_cron_not_running(db: Session = Depends(get_db)):
    config = get_cron_config(db)
    if config and config.is_running:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El motor Cron está en ejecución. Modificaciones bloqueadas temporalmente.")

router = APIRouter(prefix="/api/brands", tags=["Marcas"])


# ==================== MARCAS ====================


@router.get("/", response_model=list[BrandResponse])
def list_brands(
    estado: str | None = Query(None, description="Filtrar por estado: activa o inactiva"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Lista todas las marcas con filtro opcional por estado."""
    brands = brand_service.get_brands(db, estado_filter=estado)
    print(f"DEBUG MARCAS DEVUELTAS: {brands} (Filtro: {estado})")
    return brands


@router.get("/{brand_id}", response_model=BrandResponse)
def get_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Obtiene una marca específica con sus productos."""
    return brand_service.get_brand(db, brand_id)


@router.post("/", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
def create_brand(
    brand_data: BrandCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _block: None = Depends(check_cron_not_running),
):
    """Crea una nueva marca (analistas, administradores y super administradores)."""
    return brand_service.create_brand(db, brand_data, current_user.id)


@router.put("/{brand_id}", response_model=BrandResponse)
def update_brand(
    brand_id: int,
    brand_data: BrandUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    _block: None = Depends(check_cron_not_running),
):
    """Actualiza una marca existente (solo administradores)."""
    return brand_service.update_brand(db, brand_id, brand_data)


@router.patch("/{brand_id}/toggle", response_model=BrandResponse)
def toggle_brand_status(
    brand_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    _block: None = Depends(check_cron_not_running),
):
    """Alterna el estado de una marca entre activa e inactiva (solo administradores)."""
    return brand_service.toggle_brand_status(db, brand_id)


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    _block: None = Depends(check_cron_not_running),
):
    """Elimina una marca y sus productos (solo administradores)."""
    brand_service.delete_brand(db, brand_id)


# ==================== PRODUCTOS ====================


@router.post(
    "/{brand_id}/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_product(
    brand_id: int,
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    _block: None = Depends(check_cron_not_running),
):
    """Agrega un producto a una marca (solo administradores)."""
    return brand_service.add_product(db, brand_id, product_data)


@router.put("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    _block: None = Depends(check_cron_not_running),
):
    """Actualiza un producto existente (solo administradores)."""
    return brand_service.update_product(db, product_id, product_data)


@router.patch("/products/{product_id}/toggle", response_model=ProductResponse)
def toggle_product_status(
    product_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    _block: None = Depends(check_cron_not_running),
):
    """Alterna el estado de un producto (solo administradores)."""
    return brand_service.toggle_product_status(db, product_id)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    _block: None = Depends(check_cron_not_running),
):
    """Elimina un producto (solo administradores)."""
    brand_service.delete_product(db, product_id)
