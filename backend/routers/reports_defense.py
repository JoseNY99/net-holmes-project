from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from database import get_db
from models.user import User
from schemas.reporte import ReporteResponse, ReporteCreate, ReporteUpdate, ReporteDetail, PaginatedReportes
from schemas.perfil_investigacion import PerfilUpdate, PerfilResponse
from schemas.audit_log import AuditLogResponse

from services import reports_defense_service, perfil_service
from middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/api/reports_defense", tags=["Reportes Defense"])

@router.get("/general")
def get_general_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    from models.reporte import ReporteBrandDefense
    
    # Fake categories since "tipo" (manual/automatico) doesn't exist directly on ReporteBrandDefense 
    # but we can just split all stats and pretend they are automatic for now.
    stats = db.query(
        ReporteBrandDefense.estado, 
        func.count(ReporteBrandDefense.id)
    ).group_by(ReporteBrandDefense.estado).all()
    
    data = {"confirmados": 0, "pendientes": 0, "investigando": 0, "descartados": 0, "total": 0}
    for row in stats:
        estado = (row[0] or "").lower()
        count = row[1]
        data["total"] += count
        if "confirmado" in estado:
            data["confirmados"] += count
        elif "sospechoso" in estado or "investigando" in estado:
            data["investigando"] += count
        elif "pendiente" in estado:
            data["pendientes"] += count
        elif "descartado" in estado:
            data["descartados"] += count
            
    return {
        "stats_automatico": data,
        "stats_manual": {"confirmados": 0, "pendientes": 0, "investigando": 0, "descartados": 0, "total": 0}
    }

@router.get("/", response_model=PaginatedReportes)
def get_reportes(
    estado: str | None = Query(None),
    plataforma: str | None = Query(None),
    tipo: str | None = Query(None),
    page: int | None = Query(None),
    brand_id: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user)
):
    if page and page > 0 and skip == 0:
        skip = (page - 1) * limit
    return reports_defense_service.get_reportes(db, estado, plataforma, skip, limit, marca_id=brand_id)

@router.get("/{reporte_id}", response_model=ReporteDetail)
def get_reporte(reporte_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return reports_defense_service.get_reporte_detail(db, reporte_id)

@router.patch("/{reporte_id}", response_model=ReporteResponse)
def update_reporte_status(reporte_id: int, data: ReporteUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    result = reports_defense_service.update_reporte_status(db, reporte_id, data.estado)
    
    # Cuando pasa a Sospechoso → Fase 2: disparar correlación profunda multicuenta
    if data.estado == "Sospechoso":
        try:
            from services.correlation_engine import CorrelationEngine
            CorrelationEngine.deep_analysis(
                db, reporte_id,
                dimensiones=["identificador", "contenido", "temporal", "linguistico", "social"]
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error en correlación profunda al promover a Sospechoso: {e}")
    
    return result

class ManualScanRequest(BaseModel):
    url: str
    plataforma: str
    brand_id: int | str

@router.post("/scan/manual")
async def scan_manual_url(req: ManualScanRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Analiza una URL arbitraria usando el Generic Scraper y lo guarda como un reporte manual."""
    try:
        scraped_data = await scrape_generic_url(req.url)
        if "error" in scraped_data:
            raise HTTPException(status_code=400, detail=f"Error al analizar la URL: {scraped_data['error']}")
            
        # Determinar brand_id si es nueva marca (asumimos que brand_id ya existe en db si viene como int)
        brand_id_int = int(req.brand_id) if str(req.brand_id).isdigit() else None
        
        # Procesar y guardar
        reporte = process_and_save_single_result(db, scraped_data, brand_id_int)
        
        return {
            "msg": "URL analizada y guardada exitosamente.",
            "data": {
                "id": reporte.id,
                "titulo_publicacion": reporte.titulo_publicacion,
                "vendedor_nombre": reporte.titular_cuenta,
                "vendedor_ubicacion": reporte.ubicacion_infractor,
                "vendedor_telefono": reporte.telefono_publico,
                "precio": reporte.precio,
                "correlaciones_nlp": reporte.correlaciones_nlp,
                "estado": reporte.estado,
                "platform_data": reporte.platform_data,
                "imagen_urls": reporte.imagen_urls
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fallo al procesar el escaneo manual: {str(e)}")

@router.post("/ingest", response_model=List[ReporteResponse])
def ingest_reportes(reportes: List[ReporteCreate], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Protegido con el token de analista/admin
    return reports_defense_service.ingest_reportes(db, reportes)

# ABM (Fase 2) Endpoints
@router.get("/{reporte_id}/perfil", response_model=PerfilResponse)
def get_perfil(reporte_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return perfil_service.get_or_create_perfil(db, reporte_id)

@router.patch("/{reporte_id}/perfil", response_model=PerfilResponse)
def update_perfil(reporte_id: int, data: PerfilUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return perfil_service.update_perfil(db, reporte_id, current_user.id, data)

@router.get("/{reporte_id}/audit", response_model=list[AuditLogResponse])
def get_audit_logs(reporte_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return perfil_service.get_audit_logs(db, reporte_id)

from fastapi.responses import StreamingResponse
from services.export_service import generate_investigation_pdf, generate_investigation_docx, generate_cbn_investigation_pdf
from services.cbn_pdf import generate_fase1_preview_pdf

@router.get("/{reporte_id}/export/fase1-preview-pdf")
def export_fase1_preview_pdf(reporte_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    reporte = reports_defense_service.get_reporte_detail(db, reporte_id)
    if str(reporte.estado).lower() not in ["pendiente", "descartado"]:
        raise HTTPException(
            status_code=400, 
            detail="La Vista Previa (Fase 1) solo está disponible para reportes en estado Pendiente o Descartado. Para reportes relevados utilice el Reporte Oficial CBN."
        )
    
    pdf_buffer = generate_fase1_preview_pdf(db, reporte)
    
    import uuid
    random_id = uuid.uuid4().hex[:6]
    platform_name = str(reporte.plataforma).lower()
    filename = f"vista_previa_fase1_{platform_name}_{random_id}.pdf"
    
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers=headers)

@router.get("/{reporte_id}/export/pdf")
def export_pdf(reporte_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    reporte = reports_defense_service.get_reporte_detail(db, reporte_id)
    if str(reporte.estado).lower() in ["pendiente", "descartado"]:
        raise HTTPException(
            status_code=400, 
            detail="Este reporte fue escaneado por el bot y aún se encuentra en Fase 1 (Pendiente). Debe ser aprobado en la fase de investigación y contar con relevamiento de datos antes de poder ser exportado o impreso."
        )
    
    from models.perfil_investigacion import PerfilInvestigacion
    perfil = db.query(PerfilInvestigacion).filter(PerfilInvestigacion.reporte_id == reporte_id).first()
    
    pdf_buffer = generate_investigation_pdf(db, reporte, perfil)
    
    import uuid
    random_id = uuid.uuid4().hex[:6]
    platform_name = reporte.plataforma.lower()
    filename = f"rep_inv_{platform_name}_{random_id}.pdf"
    
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers=headers)

@router.get("/{reporte_id}/export/cbn-pdf")
def export_cbn_pdf(reporte_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    reporte = reports_defense_service.get_reporte_detail(db, reporte_id)
    if str(reporte.estado).lower() in ["pendiente", "descartado"]:
        raise HTTPException(
            status_code=400, 
            detail="El reporte oficial CBN requiere que el caso haya sido relevado a la fase de investigación y cuente con datos de identidad completados en Fase 2."
        )
    
    from models.perfil_investigacion import PerfilInvestigacion
    perfil = db.query(PerfilInvestigacion).filter(PerfilInvestigacion.reporte_id == reporte_id).first()
    
    pdf_buffer = generate_cbn_investigation_pdf(db, reporte, perfil)
    
    import uuid
    random_id = uuid.uuid4().hex[:6]
    platform_name = reporte.plataforma.lower()
    filename = f"cbn_report_{platform_name}_{random_id}.pdf"
    
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers=headers)

@router.get("/{reporte_id}/export/word")
def export_word(reporte_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    reporte = reports_defense_service.get_reporte_detail(db, reporte_id)
    if str(reporte.estado).lower() in ["pendiente", "descartado"]:
        raise HTTPException(
            status_code=400, 
            detail="Este reporte fue escaneado por el bot y aún se encuentra en Fase 1 (Pendiente). Debe ser aprobado en la fase de investigación y contar con relevamiento de datos antes de poder ser exportado o impreso."
        )
        
    from models.perfil_investigacion import PerfilInvestigacion
    perfil = db.query(PerfilInvestigacion).filter(PerfilInvestigacion.reporte_id == reporte_id).first()
        
    docx_buffer = generate_investigation_docx(db, reporte, perfil)
    
    import uuid
    random_id = uuid.uuid4().hex[:6]
    platform_name = reporte.plataforma.lower()
    filename = f"rep_inv_{platform_name}_{random_id}.docx"
    
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    return StreamingResponse(
        docx_buffer, 
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        headers=headers
    )

from services.export_service import generate_reportes_list_pdf, generate_reportes_list_docx

@router.get("/export/{format}")
def export_reportes_list(
    format: str,
    estado: str | None = Query(None),
    plataforma: str | None = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user)
):
    # Obtener reportes según filtros (sin paginación para exportar todos)
    res = reports_defense_service.get_reportes(db, estado, plataforma, skip=0, limit=1000)
    reportes = res["items"]
    
    if format == "pdf":
        buffer = generate_reportes_list_pdf(reportes)
        headers = {"Content-Disposition": "attachment; filename=Reportes_Brand_Defense.pdf"}
        return StreamingResponse(buffer, media_type="application/pdf", headers=headers)
    elif format == "word":
        buffer = generate_reportes_list_docx(reportes)
        headers = {"Content-Disposition": "attachment; filename=Reportes_Brand_Defense.docx"}
        return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers=headers)
    else:
        raise HTTPException(status_code=400, detail="Formato no soportado")

@router.post("/{reporte_id}/screenshot")
async def capture_reporte_screenshot(
    reporte_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user)
):
    """Captura una pantalla en vivo de la publicación (FB, IG, TikTok, ML) usando Playwright Stealth."""
    from models.reporte import ReporteBrandDefense
    from models.facebook_data import ReporteFacebookData
    from models.instagram_data import ReporteInstagramData
    from models.tiktok_data import ReporteTiktokData
    from models.mercadolibre_data import ReporteMercadoLibreData
    import json
    
    reporte = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.id == reporte_id).first()
    if not reporte:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")

    if not reporte.url_evidencia or not reporte.url_evidencia.startswith("http"):
        raise HTTPException(status_code=400, detail="El reporte no tiene una URL de evidencia válida para capturar")

    from services.screenshot_service import capture_post_screenshot
    screenshot_url = await capture_post_screenshot(reporte.url_evidencia, reporte.id)

    if not screenshot_url:
        raise HTTPException(status_code=500, detail="No se pudo capturar la pantalla de la publicación en este momento")

    # Guardar la screenshot en la tabla platform_data correspondiente
    screenshot_json = json.dumps([screenshot_url])
    plat = (reporte.plataforma or "").lower()
    
    if plat == "facebook":
        plat_row = db.query(ReporteFacebookData).filter(ReporteFacebookData.reporte_id == reporte_id).first()
        if plat_row:
            plat_row.image_urls = screenshot_json
        else:
            db.add(ReporteFacebookData(reporte_id=reporte_id, image_urls=screenshot_json))
    elif plat == "instagram":
        plat_row = db.query(ReporteInstagramData).filter(ReporteInstagramData.reporte_id == reporte_id).first()
        if plat_row:
            plat_row.image_urls = screenshot_json
        else:
            db.add(ReporteInstagramData(reporte_id=reporte_id, image_urls=screenshot_json))
    elif plat == "tiktok":
        plat_row = db.query(ReporteTiktokData).filter(ReporteTiktokData.reporte_id == reporte_id).first()
        if plat_row:
            plat_row.image_urls = screenshot_json
        else:
            db.add(ReporteTiktokData(reporte_id=reporte_id, image_urls=screenshot_json))
    elif plat == "mercadolibre":
        plat_row = db.query(ReporteMercadoLibreData).filter(ReporteMercadoLibreData.reporte_id == reporte_id).first()
        if plat_row:
            plat_row.image_urls = screenshot_json
        else:
            db.add(ReporteMercadoLibreData(reporte_id=reporte_id, image_urls=screenshot_json))
    
    db.commit()

    return {
        "status": "ok",
        "screenshot_url": screenshot_url,
        "reporte_id": reporte_id
    }

