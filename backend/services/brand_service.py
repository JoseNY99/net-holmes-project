"""Servicio CRUD para marcas y productos."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from models.brand import Brand
from models.product import Product
from models.marca_cuenta_oficial import MarcaCuentaOficial
from schemas.brand import BrandCreate, BrandUpdate
from schemas.product import ProductCreate, ProductUpdate


# ==================== MARCAS ====================


def get_brands(db: Session, estado_filter: str | None = None) -> list[Brand]:
    """Obtiene todas las marcas, con filtro opcional por estado."""
    query = db.query(Brand).options(joinedload(Brand.products), joinedload(Brand.cuentas_oficiales))
    if estado_filter and estado_filter.strip():
        query = query.filter(Brand.estado.ilike(f"%{estado_filter.strip()}%"))
    return query.order_by(Brand.created_at.desc()).all()


def get_brand(db: Session, brand_id: int) -> Brand:
    """Obtiene una marca por su ID, incluyendo sus productos."""
    brand = (
        db.query(Brand)
        .options(joinedload(Brand.products), joinedload(Brand.cuentas_oficiales))
        .filter(Brand.id == brand_id)
        .first()
    )
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marca no encontrada",
        )
    return brand


def create_brand(db: Session, brand_data: BrandCreate, user_id: int) -> Brand:
    """Crea una nueva marca asociada al usuario indicado."""
    brand = Brand(
        nombre=brand_data.nombre,
        descripcion=brand_data.descripcion,
        created_by=user_id,
    )
    
    # Agregar cuentas oficiales
    if hasattr(brand_data, "cuentas_oficiales") and brand_data.cuentas_oficiales:
        for cuenta in brand_data.cuentas_oficiales:
            brand.cuentas_oficiales.append(
                MarcaCuentaOficial(
                    plataforma=cuenta.plataforma,
                    handle_oficial=cuenta.handle_oficial
                )
            )

    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def update_brand(db: Session, brand_id: int, brand_data: BrandUpdate) -> Brand:
    """Actualiza los campos de una marca existente."""
    brand = get_brand(db, brand_id)
    update_fields = brand_data.model_dump(exclude_unset=True)
    
    if "cuentas_oficiales" in update_fields:
        # Reemplazar cuentas oficiales
        # Primero eliminar las actuales
        db.query(MarcaCuentaOficial).filter(MarcaCuentaOficial.marca_id == brand.id).delete()
        
        # Añadir las nuevas
        for cuenta in update_fields["cuentas_oficiales"]:
            db.add(
                MarcaCuentaOficial(
                    marca_id=brand.id,
                    plataforma=cuenta["plataforma"],
                    handle_oficial=cuenta["handle_oficial"]
                )
            )
        
        del update_fields["cuentas_oficiales"]

    for field, value in update_fields.items():
        setattr(brand, field, value)
    brand.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(brand)
    return brand


def toggle_brand_status(db: Session, brand_id: int) -> Brand:
    """Alterna el estado de una marca entre 'activa' e 'inactiva'."""
    brand = get_brand(db, brand_id)
    brand.estado = "inactiva" if brand.estado == "activa" else "activa"
    brand.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(brand)
    return brand


def delete_brand(db: Session, brand_id: int) -> None:
    """Elimina una marca y todos sus productos asociados."""
    brand = get_brand(db, brand_id)
    db.delete(brand)
    db.commit()


# ==================== PRODUCTOS ====================


def add_product(db: Session, brand_id: int, product_data: ProductCreate) -> Product:
    """Agrega un producto a una marca existente."""
    # Verificar que la marca existe
    get_brand(db, brand_id)
    product = Product(
        brand_id=brand_id,
        nombre=product_data.nombre,
        descripcion=product_data.descripcion,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(
    db: Session, product_id: int, product_data: ProductUpdate
) -> Product:
    """Actualiza los campos de un producto existente."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    update_fields = product_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product

def toggle_product_status(db: Session, product_id: int) -> Product:
    """Alterna el estado de un producto entre 'activa' e 'inactiva'."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    product.estado = "inactiva" if product.estado == "activa" else "activa"
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: int) -> None:
    """Elimina un producto por su ID."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    db.delete(product)
    db.commit()
