from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone

from database import get_db
from models.reporte import ReporteBrandDefense

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    try:
        # Panel Top Stats
        analisis_pendientes = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.estado == "Pendiente").count()
        reportes_generados = db.query(ReporteBrandDefense).count()
        sospechosos_detectados = db.query(ReporteBrandDefense).filter(ReporteBrandDefense.estado == "Sospechoso").count()

        # Timeline de recolección (últimos 7 días)
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        daily_stats = db.query(
            func.date(ReporteBrandDefense.created_at).label("fecha"),
            func.count(ReporteBrandDefense.id).label("cantidad")
        ).filter(
            ReporteBrandDefense.created_at.isnot(None),
            ReporteBrandDefense.created_at >= seven_days_ago
        ).group_by(
            func.date(ReporteBrandDefense.created_at)
        ).order_by(
            func.date(ReporteBrandDefense.created_at)
        ).all()

        timeline = [{"name": str(r.fecha) if r.fecha else "Hoy", "scans": r.cantidad} for r in daily_stats]

        # BarChart: Plataformas
        platform_stats = db.query(
            ReporteBrandDefense.plataforma,
            func.count(ReporteBrandDefense.id).label("cantidad")
        ).group_by(ReporteBrandDefense.plataforma).all()

        platforms = [{"name": r.plataforma or "Otro", "value": r.cantidad} for r in platform_stats]

        # Recent Activity (Live Feed)
        recent = db.query(ReporteBrandDefense).order_by(ReporteBrandDefense.id.desc()).limit(15).all()
        recent_activity = []
        for r in recent:
            t = r.updated_at or r.created_at or datetime.now(timezone.utc)
            time_iso = t.isoformat() if hasattr(t, "isoformat") else str(t)
            recent_activity.append({
                "id": r.id,
                "plataforma": r.plataforma or "web",
                "vendedor": r.titular_cuenta or "Desconocido",
                "marca": r.marca_afectada or "",
                "producto": r.producto_catalogo or "",
                "estado": r.estado or "Pendiente",
                "time": time_iso
            })

        return {
            "analisis_pendientes": analisis_pendientes,
            "reportes_generados": reportes_generados,
            "sospechosos_detectados": sospechosos_detectados,
            "timeline": timeline,
            "platforms": platforms,
            "recent_activity": recent_activity
        }
    except Exception as e:
        print(f"Error in get_dashboard_stats: {e}")
        return {
            "analisis_pendientes": 0,
            "reportes_generados": 0,
            "sospechosos_detectados": 0,
            "timeline": [],
            "platforms": [],
            "recent_activity": []
        }
