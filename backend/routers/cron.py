from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from database import get_db
from services import cron_service
from schemas.cron_config import CronConfigUpdate, CronConfigResponse
from middleware.auth_middleware import get_current_user, require_admin
from models.brand import Brand
from config import PROVINCIAS_AR
from services.cron_manager import update_job_schedule, trigger_manual_scan
import json

router = APIRouter(prefix="/api/cron", tags=["cron"])

@router.get('/status')
def get_cron_status(db: Session = Depends(get_db)):
    """Estado en tiempo real del cron con logs y progreso detallado."""
    from services.cron_logger import cron_logger
    config = cron_service.get_cron_config(db)
    return {
        'is_running': config.is_running,
        'last_run': config.last_run,
        'last_run_status': config.last_run_status,
        'logs': cron_logger.get_logs(last_n=50),
        'progress': cron_logger.get_progress(),
    }

@router.get('/config', response_model=CronConfigResponse)
def get_config(db: Session = Depends(get_db), admin=Depends(require_admin)):
    config = cron_service.get_cron_config(db)
    return config

@router.put('/config', response_model=CronConfigResponse)
def update_config(data: CronConfigUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    updated = cron_service.update_cron_config(db, data)
    update_job_schedule(db)
    return updated

from typing import Optional
class ToggleRequest(BaseModel):
    is_active: Optional[bool] = None

@router.post('/toggle', response_model=CronConfigResponse)
def toggle_cron_state(req: Optional[ToggleRequest] = None, db: Session = Depends(get_db), admin=Depends(require_admin)):
    config = cron_service.get_cron_config(db)
    new_state = not config.is_active if (req is None or req.is_active is None) else req.is_active
    updated = cron_service.toggle_active(db, new_state)
    update_job_schedule(db)
    return updated

class DashboardSearchRequest(BaseModel):
    brand_ids: list[int] = Field(min_length=1, max_length=30)
    provincias: list[str] = Field(min_length=1, max_length=24)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    duration_minutes: int = Field(default=30, ge=5, le=60)

@router.post('/start')
async def start_cron_force(
    background_tasks: BackgroundTasks,
    req: DashboardSearchRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from services.cron_logger import cron_logger
    from services.cron_manager import run_automatic_scan
    from services import cron_service
    from sqlalchemy import func

    search_options = None
    if req is not None:
        ids = set(req.brand_ids)
        selected_brands = db.query(Brand).filter(
            Brand.id.in_(ids), func.lower(Brand.estado) == 'activa'
        ).all()
        if len(selected_brands) != len(ids):
            raise HTTPException(status_code=400, detail="Selecciona únicamente marcas activas.")

        allowed_locations = {"argentina", *(province["name"].casefold() for province in PROVINCIAS_AR)}
        locations = [location.strip() for location in req.provincias]
        if any(location.casefold() not in allowed_locations for location in locations):
            raise HTTPException(status_code=400, detail="El alcance geográfico debe estar dentro de Argentina.")

        search_options = {
            "brand_ids": list(ids),
            "provincias": locations,
            "keywords": [keyword.strip() for keyword in req.keywords if keyword.strip()],
            "duration_minutes": req.duration_minutes,
        }
    elif current_user.rol not in ("admin", "sup_admin"):
        raise HTTPException(status_code=422, detail="Selecciona marcas y provincias para iniciar la búsqueda.")

    config = cron_service.get_cron_config(db)
    if config.is_running:
        raise HTTPException(status_code=409, detail="Ya hay una búsqueda en ejecución.")

    cron_service.set_running(db, True)
    cron_logger.reset()
    cron_logger.log("Búsqueda inmediata iniciada desde el dashboard.")
    background_tasks.add_task(run_automatic_scan, search_options)
    return {"msg": "Escaneo forzado iniciado exitosamente en background"}

@router.post('/stop')
def stop_cron_force(db: Session = Depends(get_db), admin=Depends(require_admin)):
    from services.cron_manager import request_stop
    request_stop()
    cron_service.set_running(db, False)
    return {"msg": "Detención de emergencia ejecutada exitosamente"}

# --- Apify Fase 2 Endpoints ---

class ApifyScanRequest(BaseModel):
    keyword: str
    plataformas: list[str]
    provincias: list[str]
    limite: int = 5

# Estado global simple en memoria para Apify (se podría mover a DB si se necesita persistencia profunda)
apify_status_state = {
    "is_running": False,
    "last_run": None,
    "logs": []
}

async def run_apify_task(keyword: str, plataformas: list[str], provincias: list[str], limite: int):
    from scrapers.apify_motor import ApifyMotorFase2
    from services.reports_defense_service import process_and_save_single_result
    from database import SessionLocal
    from datetime import datetime, timezone

    apify_status_state["is_running"] = True
    apify_status_state["last_run"] = datetime.now(timezone.utc).isoformat()
    apify_status_state["logs"].append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Iniciando Apify Fase 2...")
    
    motor = ApifyMotorFase2()
    db = SessionLocal()
    try:
        async for item in motor.execute(keyword, plataformas, provincias, limite):
            process_and_save_single_result(db, item, None)
            apify_status_state["logs"].append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Guardado: {item.get('title', 'Sin titulo')[:30]}...")
            if len(apify_status_state["logs"]) > 100:
                apify_status_state["logs"] = apify_status_state["logs"][-100:]
        apify_status_state["logs"].append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Escaneo Apify Finalizado exitosamente.")
    except Exception as e:
        apify_status_state["logs"].append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Error en Apify: {str(e)}")
    finally:
        db.close()
        apify_status_state["is_running"] = False

@router.post('/apify-scan')
def start_apify_scan(req: ApifyScanRequest, background_tasks: BackgroundTasks, admin=Depends(require_admin)):
    if apify_status_state["is_running"]:
        return {"msg": "Ya hay un escaneo de Apify en ejecución."}

    allowed_locations = {"argentina", *(province["name"].casefold() for province in PROVINCIAS_AR)}
    if any(location.strip().casefold() not in allowed_locations for location in req.provincias):
        raise HTTPException(status_code=400, detail="El alcance geográfico debe estar dentro de Argentina.")
    
    apify_status_state["logs"] = [] # Clear previous logs
    background_tasks.add_task(run_apify_task, req.keyword, req.plataformas, req.provincias, req.limite)
    return {"msg": "Escaneo de Apify iniciado en background."}

@router.get('/apify-status')
def get_apify_status(admin=Depends(require_admin)):
    return apify_status_state
