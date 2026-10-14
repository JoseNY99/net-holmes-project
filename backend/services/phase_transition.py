from sqlalchemy.orm import Session
from models.reporte import ReporteBrandDefense
from models.perfil_investigacion import PerfilInvestigacion
from services.cron_logger import cron_logger


def start_phase_two_automatically(db: Session, reporte: ReporteBrandDefense):
    """
    Promueve el reporte a Investigación y crea su perfil de Fase 2 en la misma
    transacción que guarda el reporte.
    """
    if reporte.estado != "Investigando":
        reporte.estado = "Investigando"

    perfil = (
        db.query(PerfilInvestigacion)
        .filter(PerfilInvestigacion.reporte_id == reporte.id)
        .first()
    )
    if perfil is None:
        db.add(PerfilInvestigacion(reporte_id=reporte.id))

    db.flush()
    cron_logger.log(
        f"🔄 [Fase 2] Reporte {reporte.id} promovido a Investigando "
        "y perfil de investigación creado."
    )