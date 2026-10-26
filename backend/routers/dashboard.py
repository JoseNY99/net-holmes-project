from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone

from database import get_db
from models.reporte import ReporteBrandDefense
from models.brand import Brand
from middleware.auth_middleware import get_current_user
from services.dashboard_scope import COUNTRIES, normalize_scope
from services.dashboard_search import dashboard_search, brand_snapshot

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


class DashboardSearchRequest(BaseModel):
    brand_ids: list[int] = Field(min_length=1, max_length=30)
    pais: str = "Argentina"
    provincias: list[str] = Field(default_factory=list, max_length=32)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    duration_minutes: int = Field(default=30, ge=5, le=60)
    plataformas: list[str] = Field(default_factory=lambda: ["facebook", "instagram", "tiktok", "mercadolibre"], min_length=1, max_length=4)
    proveedor: str = "google_meli_osint"

    @field_validator("plataformas")
    @classmethod
    def valid_platforms(cls, value):
        if any(platform not in {"facebook", "instagram", "tiktok", "mercadolibre"} for platform in value):
            raise ValueError("Selecciona plataformas válidas.")
        return list(dict.fromkeys(value))

    @field_validator("keywords")
    @classmethod
    def valid_keywords(cls, value):
        if any(len(keyword) > 200 for keyword in value):
            raise ValueError("Cada palabra clave admite hasta 200 caracteres.")
        return list(dict.fromkeys(keyword.strip() for keyword in value if keyword.strip()))

    @field_validator("proveedor")
    @classmethod
    def valid_provider(cls, value):
        if value != "google_meli_osint":
            raise ValueError("El dashboard utiliza google_meli_osint.")
        return value


@router.get("/search/locations")
def get_search_locations(current_user=Depends(get_current_user)):
    return [{"pais": name, "provincias": cfg["provincias"], "phone_format": cfg["phone_format"]} for name, cfg in COUNTRIES.items()]


@router.post("/search/start", status_code=202)
async def start_dashboard_search(req: DashboardSearchRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        country, provinces = normalize_scope(req.pais, req.provincias)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ids = set(req.brand_ids)
    brands = db.query(Brand).filter(Brand.id.in_(ids), func.lower(Brand.estado) == "activa").all()
    if len(brands) != len(ids):
        raise HTTPException(status_code=422, detail="Selecciona únicamente marcas activas.")
    options = req.model_dump()
    options.update(pais=country, provincias=provinces)
    try:
        return dashboard_search.start(current_user.id, options, [brand_snapshot(brand) for brand in brands])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/search/status")
async def get_dashboard_search_status(current_user=Depends(get_current_user)):
    return dashboard_search.status(current_user.id, current_user.rol in ("admin", "sup_admin"))


@router.post("/search/stop")
async def stop_dashboard_search(current_user=Depends(get_current_user)):
    admin = current_user.rol in ("admin", "sup_admin")
    if dashboard_search.state and dashboard_search.state["is_running"] and dashboard_search.state["owner_id"] != current_user.id and not admin:
        raise HTTPException(status_code=403, detail="Solo puedes detener tu propia búsqueda.")
    await dashboard_search.stop()
    return dashboard_search.status(current_user.id, admin)

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
