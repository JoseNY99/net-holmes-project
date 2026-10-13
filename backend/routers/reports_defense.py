import logging
import math
from io import BytesIO

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from database import get_db
from models.user import User
from models.reporte import ReporteBrandDefense
from models.reporte_final import ReporteFinal
from schemas.reporte import ReporteResponse, ReporteCreate, ReporteUpdate, ReporteDetail, PaginatedReportes, ReporteQuickEdit
from schemas.perfil_investigacion import PerfilUpdate, PerfilResponse
from schemas.audit_log import AuditLogResponse

from services import reports_defense_service, perfil_service
from middleware.auth_middleware import get_current_user, require_admin
from services.report_completion import RECOLECCION_FIELDS, calculate_completion_percentage, get_missing_recollection_fields

router = APIRouter(prefix="/api/reports_defense", tags=["Reportes Defense"])
analyst_alert_logger = logging.getLogger("analyst.alerts")
FINAL_REPORT_COMPLETION_THRESHOLD = 80
AUTOMATIC_PHASE_TWO_STATES = {"Sospechoso", "Investigando"}


def _reject_manual_phase_two_transition(estado):
    state_value = getattr(estado, "value", estado)
    if state_value in AUTOMATIC_PHASE_TWO_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La Fase 2 se inicia automáticamente al ingresar un hallazgo elegible.",
        )


def _require_report_completion(reporte, perfil, analyst: User) -> float:
    percentage = calculate_completion_percentage({"perfil": perfil})
    if percentage < FINAL_REPORT_COMPLETION_THRESHOLD:
        missing_fields = get_missing_recollection_fields({"perfil": perfil})
        required_fields = math.ceil(len(RECOLECCION_FIELDS) * FINAL_REPORT_COMPLETION_THRESHOLD / 100)
        completed_count = len(RECOLECCION_FIELDS) - len(missing_fields)
        remaining_count = max(0, required_fields - completed_count)
        analyst_alert_logger.warning(
            "Alerta para analista: el reporte final no se emitió; "
            "reporte_id=%s referencia=%s porcentaje=%s umbral=%s "
            "analyst_user_id=%s analyst_email=%s",
            reporte.id,
            reporte.referencia_interna,
            percentage,
            FINAL_REPORT_COMPLETION_THRESHOLD,
            analyst.id,
            analyst.correo,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede generar el reporte final: relevamiento completado "
                f"al {percentage}% ({completed_count}/9 datos). Se requieren al menos "
                f"{required_fields}/9; completa {remaining_count} más. Campos pendientes: "
                f"{', '.join(missing_fields)}. Se notificó al analista."
            ),
        )
    return percentage

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
    _reject_manual_phase_two_transition(data.estado)
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

@router.patch("/{reporte_id}/quick-edit", response_model=ReporteResponse)
def quick_edit_reporte(reporte_id: int, data: ReporteQuickEdit, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Permite editar campos de Fase 1 (precio, moneda, teléfono, calle, notas) sin cambiar de fase."""
    update_data = data.model_dump(exclude_unset=True)
    _reject_manual_phase_two_transition(update_data.get("estado"))
    result = reports_defense_service.quick_update_reporte(db, reporte_id, update_data)
    return result

class ManualScanRequest(BaseModel):
    url: str
    plataforma: str
    brand_id: int | str

@router.post("/scan/manual")
async def scan_manual_url(req: ManualScanRequest, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
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
from services.export_service import (
    generate_cbn_investigation_pdf,
    generate_investigation_pdf,
    generate_investigation_docx,
)


def _get_final_report_data(reporte_id: int, db: Session, current_user: User):
    reporte = reports_defense_service.get_reporte_detail(db, reporte_id)
    from models.perfil_investigacion import PerfilInvestigacion
    perfil = db.query(PerfilInvestigacion).filter(PerfilInvestigacion.reporte_id == reporte_id).first()
    completion_percentage = _require_report_completion(reporte, perfil, current_user)
    estado = getattr(reporte.estado, "value", reporte.estado)
    if str(estado).lower() in {"pendiente", "descartado"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El informe final requiere un caso en Fase 2 de relevamiento.",
        )
    return reporte, perfil, completion_percentage


@router.get("/{reporte_id}/export/pdf")
def export_pdf(reporte_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reporte, perfil, _ = _get_final_report_data(reporte_id, db, current_user)
    pdf_buffer = generate_investigation_pdf(db, reporte, perfil)
    filename = f"reporte_final_{reporte_id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{reporte_id}/export/word")
def export_word(reporte_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reporte, perfil, _ = _get_final_report_data(reporte_id, db, current_user)
    docx_buffer = generate_investigation_docx(db, reporte, perfil)
    filename = f"reporte_final_{reporte_id}.docx"
    return StreamingResponse(
        docx_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@router.get("/{reporte_id}/export/cbn-pdf")
def export_cbn_pdf(reporte_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reporte = (
        db.query(ReporteBrandDefense)
        .filter(ReporteBrandDefense.id == reporte_id)
        .with_for_update(of=ReporteBrandDefense)
        .first()
    )
    if not reporte:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")

    from models.perfil_investigacion import PerfilInvestigacion
    perfil = db.query(PerfilInvestigacion).filter(PerfilInvestigacion.reporte_id == reporte_id).first()
    completion_percentage = _require_report_completion(reporte, perfil, current_user)
    estado = getattr(reporte.estado, "value", reporte.estado)
    if str(estado).lower() in {"pendiente", "descartado"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El informe final requiere un caso en Fase 2 de relevamiento.",
        )

    pdf_data = generate_cbn_investigation_pdf(db, reporte, perfil).getvalue()
    reporte_final = db.query(ReporteFinal).filter(ReporteFinal.reporte_id == reporte_id).first()
    if reporte_final:
        reporte_final.completion_percentage = completion_percentage
        reporte_final.pdf_data = pdf_data
        reporte_final.generated_by_user_id = current_user.id
    else:
        db.add(ReporteFinal(
            reporte_id=reporte_id,
            completion_percentage=completion_percentage,
            pdf_data=pdf_data,
            generated_by_user_id=current_user.id,
        ))
    db.commit()

    platform_name = (reporte.plataforma or "reporte").lower()
    filename = f"reporte_final_{reporte_id}_{platform_name}.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(BytesIO(pdf_data), media_type="application/pdf", headers=headers)


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

