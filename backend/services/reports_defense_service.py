from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import List

from models.reporte import ReporteBrandDefense
from schemas.reporte import ReporteCreate
from services.perfil_service import get_or_create_perfil
from services.correlation_engine import CorrelationEngine
from models.facebook_data import ReporteFacebookData
from models.instagram_data import ReporteInstagramData
from models.tiktok_data import ReporteTiktokData
from models.mercadolibre_data import ReporteMercadoLibreData

def get_reportes(db: Session, estado: str = None, plataforma: str = None, skip: int = 0, limit: int = 20, marca_id: str = None):
    try:
        query = db.query(ReporteBrandDefense)
        if estado and estado.strip():
            from sqlalchemy import cast, String, or_
            estados = [value.strip() for value in estado.split("|") if value.strip()]
            query = query.filter(
                or_(*[
                    cast(ReporteBrandDefense.estado, String).ilike(f"%{value}%")
                    for value in estados
                ])
            )
        if plataforma and plataforma.strip():
            query = query.filter(ReporteBrandDefense.plataforma.ilike(f"%{plataforma.strip()}%"))
        if marca_id and str(marca_id).strip():
            try:
                from models.brand import Brand
                brand = db.query(Brand).filter(Brand.id == int(marca_id)).first()
                if brand:
                    query = query.filter(ReporteBrandDefense.marca_afectada.ilike(f"%{brand.nombre}%"))
            except Exception:
                query = query.filter(ReporteBrandDefense.marca_afectada.ilike(f"%{marca_id}%"))
                
        total = query.count()
        items = query.order_by(ReporteBrandDefense.fecha_captura.desc().nullslast(), ReporteBrandDefense.id.desc()).offset(skip).limit(limit).all()
        
        return {"items": items or [], "total": total or 0}
    except Exception as e:
        print(f"Error in get_reportes: {e}")
        return {"items": [], "total": 0}

def get_reporte_detail(db: Session, reporte_id: int):
    reporte = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.id == reporte_id).first()
    if not reporte:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")
    
    # Construir platform_data desde las relaciones backref para la API response
    plat = (reporte.plataforma or "").lower()
    pd_obj = None
    if plat == "facebook" and hasattr(reporte, "facebook_data") and reporte.facebook_data:
        pd_obj = {"facebook": reporte.facebook_data}
    elif plat == "instagram" and hasattr(reporte, "instagram_data") and reporte.instagram_data:
        pd_obj = {"instagram": reporte.instagram_data}
    elif plat == "tiktok" and hasattr(reporte, "tiktok_data") and reporte.tiktok_data:
        pd_obj = {"tiktok": reporte.tiktok_data}
    elif plat == "mercadolibre" and hasattr(reporte, "mercadolibre_data") and reporte.mercadolibre_data:
        pd_obj = {"mercadolibre": reporte.mercadolibre_data}
    
    # Adjuntar como atributo temporal para que Pydantic lo serialice
    reporte._platform_data_obj = pd_obj

    # Comprobar si existe un archivo físico de evidencia o captura en disco
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent
    evid_path = base_dir / "static" / "evidencias" / f"reporte_{reporte.id}.jpg"
    screen_path = base_dir / "static" / "screenshots" / f"reporte_{reporte.id}.jpg"

    if evid_path.exists() and evid_path.stat().st_size > 100:
        reporte.evidence_image_url = f"/static/evidencias/reporte_{reporte.id}.jpg"
    elif screen_path.exists() and screen_path.stat().st_size > 100:
        reporte.evidence_image_url = f"/static/screenshots/reporte_{reporte.id}.jpg"
    else:
        reporte.evidence_image_url = None

    return reporte

def update_reporte_status(db: Session, reporte_id: int, estado: str):
    reporte = get_reporte_detail(db, reporte_id)
    if estado:
        reporte.estado = estado
        
        # Trigger de Transición a Fase 2 (ABM)
        if estado in ["Sospechoso", "Investigando"]:
            get_or_create_perfil(db, reporte_id)
            
        db.commit()
        db.refresh(reporte)
    return reporte

def quick_update_reporte(db: Session, reporte_id: int, data: dict):
    reporte = get_reporte_detail(db, reporte_id)
    if "precio_publico" in data and data["precio_publico"] is not None:
        reporte.precio_publico = data["precio_publico"]
    if "moneda" in data and data["moneda"] is not None:
        reporte.moneda = data["moneda"]
    if "telefono_publico" in data and data["telefono_publico"] is not None:
        reporte.telefono_publico = data["telefono_publico"]
    if "direccion_publica" in data and data["direccion_publica"] is not None:
        reporte.direccion_publica = data["direccion_publica"]
    if "descripcion_post" in data and data["descripcion_post"] is not None:
        reporte.descripcion_post = data["descripcion_post"]
    if "titular_cuenta" in data and data["titular_cuenta"] is not None:
        reporte.titular_cuenta = data["titular_cuenta"]
    if "estado" in data and data["estado"] is not None:
        reporte.estado = data["estado"]
        if reporte.estado in ["Sospechoso", "Investigando"]:
            get_or_create_perfil(db, reporte_id)
            
    db.commit()
    db.refresh(reporte)
    return reporte

def ingest_reportes(db: Session, reportes_data: List[ReporteCreate]):
    nuevos_reportes = []
    for data in reportes_data:
        # Extraer platform_data del payload
        dump = data.model_dump()
        platform_data = dump.pop("platform_data", None)
        
        nuevo = ReporteBrandDefense(**dump)
        db.add(nuevo)
        db.flush() # Para obtener el ID

        from services.phase_transition import start_phase_two_automatically
        start_phase_two_automatically(db, nuevo)
        
        # Procesar datos específicos de plataforma
        if platform_data and nuevo.plataforma:
            plat = nuevo.plataforma.lower()
            if plat == "facebook" and platform_data.get("facebook"):
                fb_data = ReporteFacebookData(reporte_id=nuevo.id, **platform_data["facebook"])
                db.add(fb_data)
            elif plat == "instagram" and platform_data.get("instagram"):
                ig_data = ReporteInstagramData(reporte_id=nuevo.id, **platform_data["instagram"])
                db.add(ig_data)
            elif plat == "tiktok" and platform_data.get("tiktok"):
                tt_data = ReporteTiktokData(reporte_id=nuevo.id, **platform_data["tiktok"])
                db.add(tt_data)
            elif plat == "mercadolibre" and platform_data.get("mercadolibre"):
                ml_data = ReporteMercadoLibreData(reporte_id=nuevo.id, **platform_data["mercadolibre"])
                db.add(ml_data)

        nuevos_reportes.append(nuevo)
        
    db.commit()
    for n in nuevos_reportes:
        db.refresh(n)
        
    # Trigger correlación automática ligera (Identificadores y Contenido)
    if nuevos_reportes:
        try:
            CorrelationEngine.analyze_new_reports(db, [n.id for n in nuevos_reportes])
        except Exception as e:
            print(f"Error en motor de correlación automático: {e}")
        
    return nuevos_reportes
