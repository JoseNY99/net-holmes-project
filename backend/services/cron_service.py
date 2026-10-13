"""Servicio para configuración del Cron."""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from models.cron_config import CronConfig
from schemas.cron_config import CronConfigUpdate
from services.argentina_scope import normalize_argentina_locations
import json

def get_cron_config(db: Session) -> CronConfig:
    config = db.query(CronConfig).first()
    if not config:
        config = CronConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

def update_cron_config(db: Session, config_data: CronConfigUpdate) -> CronConfig:
    config = get_cron_config(db)
    update_fields = config_data.model_dump(exclude_unset=True)
    if "provincias_seleccionadas" in update_fields:
        try:
            locations = json.loads(update_fields["provincias_seleccionadas"])
        except (TypeError, json.JSONDecodeError):
            locations = []
        update_fields["provincias_seleccionadas"] = json.dumps(
            normalize_argentina_locations(locations), ensure_ascii=False
        )
    for key, value in update_fields.items():
        setattr(config, key, value)
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)
    return config

def set_running(db: Session, is_running: bool):
    config = get_cron_config(db)
    config.is_running = is_running
    config.updated_at = datetime.now(timezone.utc)
    db.commit()

def toggle_active(db: Session, is_active: bool):
    config = get_cron_config(db)
    config.is_active = is_active
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    return config

def record_run(db: Session, status_str: str):
    config = get_cron_config(db)
    config.last_run = datetime.now(timezone.utc)
    config.last_run_status = status_str
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
