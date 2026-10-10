from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from models.perfil_investigacion import PerfilInvestigacion
from models.audit_log import AuditLog
from schemas.perfil_investigacion import PerfilUpdate
from models.user import User

def get_or_create_perfil(db: Session, reporte_id: int) -> PerfilInvestigacion:
    perfil = db.query(PerfilInvestigacion).filter(PerfilInvestigacion.reporte_id == reporte_id).first()
    if not perfil:
        perfil = PerfilInvestigacion(reporte_id=reporte_id)
        db.add(perfil)
        db.commit()
        db.refresh(perfil)
    return perfil

def update_perfil(db: Session, reporte_id: int, user_id: int, data: PerfilUpdate) -> PerfilInvestigacion:
    perfil = get_or_create_perfil(db, reporte_id)
    update_data = data.model_dump(exclude_unset=True)
    
    # Mapear alias legados
    if "telefono_confirmado" in update_data and update_data["telefono_confirmado"] and not update_data.get("telefono_privado"):
        update_data["telefono_privado"] = update_data.pop("telefono_confirmado")
    if "precio_final" in update_data and update_data["precio_final"] and not update_data.get("precio_final_cotizado"):
        update_data["precio_final_cotizado"] = update_data.pop("precio_final")
        
    valid_fields = [
        "dni_cedula", "cuit_cuil_ruc", "banco", "alias_bancario",
        "cvu_cbu", "email", "direccion_exacta", "telefono_privado",
        "precio_final_cotizado"
    ]
    
    for campo in valid_fields:
        if campo in update_data:
            valor_nuevo = update_data[campo]
            valor_anterior = getattr(perfil, campo, None)
            if str(valor_nuevo or '') != str(valor_anterior or ''):
                try:
                    audit = AuditLog(
                        reporte_id=reporte_id, 
                        user_id=user_id,
                        campo=campo, 
                        valor_anterior=str(valor_anterior) if valor_anterior is not None else None,
                        valor_nuevo=str(valor_nuevo) if valor_nuevo is not None else None
                    )
                    db.add(audit)
                except Exception:
                    pass
                setattr(perfil, campo, valor_nuevo)
            
    perfil.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(perfil)
    return perfil

def get_audit_logs(db: Session, reporte_id: int):
    logs = db.query(AuditLog).filter(AuditLog.reporte_id == reporte_id).order_by(AuditLog.created_at.desc()).all()
    # Populate user_nombre manually since schemas don't automatically extract from the relationship
    # unless configured with nested schemas, but we're doing a flat response.
    for log in logs:
        log.user_nombre = f"{log.user.nombre} {log.user.apellido}" if log.user else "Desconocido"
    return logs
