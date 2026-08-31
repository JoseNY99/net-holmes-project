from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.reporte import ReporteBrandDefense

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    # Panel Top Stats
    analisis_pendientes = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.estado == "Pendiente").count()
    reportes_generados = db.query(ReporteBrandDefense).count()
    sospechosos_detectados = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.estado == "Sospechoso").count()

    # Timeline de recolección (últimos 7 días)
    # Agrupamos por fecha
    from sqlalchemy import func
    from datetime import datetime, timedelta, timezone
    
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    daily_stats = db.query(
        func.date(ReporteBrandDefense.created_at).label("fecha"),
        func.count(ReporteBrandDefense.id).label("cantidad")
    ).filter(
        ReporteBrandDefense.created_at >= seven_days_ago
    ).group_by(
        func.date(ReporteBrandDefense.created_at)
    ).order_by(
        func.date(ReporteBrandDefense.created_at)
    ).all()

    timeline = [{"name": str(r.fecha), "scans": r.cantidad} for r in daily_stats]

    # BarChart: Plataformas
    platform_stats = db.query(
        ReporteBrandDefense.plataforma,
        func.count(ReporteBrandDefense.id).label("cantidad")
    ).group_by(ReporteBrandDefense.plataforma).all()

    platforms = [{"name": r.plataforma, "value": r.cantidad} for r in platform_stats]

    # Recent Activity (Live Feed) - Últimas actividades considerando actualizaciones
    recent = db.query(ReporteBrandDefense).order_by(ReporteBrandDefense.updated_at.desc()).limit(15).all()
    recent_activity = [
        {
            "id": r.id,
            "plataforma": r.plataforma,
            "vendedor": r.titular_cuenta or "Desconocido",
            "marca": r.marca_afectada or "",
            "producto": r.producto_catalogo or "",
            "estado": r.estado,
            "time": r.updated_at.isoformat() if r.updated_at else r.created_at.isoformat()
        } for r in recent
    ]

    return {
        "analisis_pendientes": analisis_pendientes,
        "reportes_generados": reportes_generados,
        "sospechosos_detectados": sospechosos_detectados,
        "timeline": timeline,
        "platforms": platforms,
        "recent_activity": recent_activity
    }
