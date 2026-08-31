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

def get_reportes(db: Session, estado: str = None, plataforma: str = None, skip: int = 0, limit: int = 20):
    query = db.query(ReporteBrandDefense)
    if estado:
        query = query.filter(ReporteBrandDefense.estado == estado)
    if plataforma:
        query = query.filter(ReporteBrandDefense.plataforma == plataforma)
        
    total = query.count()
    items = query.order_by(ReporteBrandDefense.fecha_captura.desc()).offset(skip).limit(limit).all()
    
    return {"items": items, "total": total}

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

def ingest_reportes(db: Session, reportes_data: List[ReporteCreate]):
    nuevos_reportes = []
    for data in reportes_data:
        # Extraer platform_data del payload
        dump = data.model_dump()
        platform_data = dump.pop("platform_data", None)
        
        nuevo = ReporteBrandDefense(**dump)
        db.add(nuevo)
        db.flush() # Para obtener el ID
        
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
