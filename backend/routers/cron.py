from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from services import cron_service
from schemas.cron_config import CronConfigUpdate, CronConfigResponse
from middleware.auth_middleware import require_admin
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
from pydantic import BaseModel
class ToggleRequest(BaseModel):
    is_active: Optional[bool] = None

@router.post('/toggle', response_model=CronConfigResponse)
def toggle_cron_state(req: Optional[ToggleRequest] = None, db: Session = Depends(get_db), admin=Depends(require_admin)):
    config = cron_service.get_cron_config(db)
    new_state = not config.is_active if (req is None or req.is_active is None) else req.is_active
    updated = cron_service.toggle_active(db, new_state)
    update_job_schedule(db)
    return updated

@router.post('/start')
async def start_cron_force(background_tasks: BackgroundTasks, db: Session = Depends(get_db), admin=Depends(require_admin)):
    from services.cron_logger import cron_logger
    from services.cron_manager import run_automatic_scan
    from services import cron_service

    cron_service.set_running(db, True)
    cron_logger.reset()
    cron_logger.log("🚀 [Manual] Escaneo forzado inmediato solicitado por el analista.")
    background_tasks.add_task(run_automatic_scan)
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
    
    apify_status_state["logs"] = [] # Clear previous logs
    background_tasks.add_task(run_apify_task, req.keyword, req.plataformas, req.provincias, req.limite)
    return {"msg": "Escaneo de Apify iniciado en background."}

@router.get('/apify-status')
def get_apify_status(admin=Depends(require_admin)):
    return apify_status_state
