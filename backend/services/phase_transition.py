from enums import EstadoReporte
from models.perfil_investigacion import PerfilInvestigacion


def start_phase_two_automatically(db, reporte) -> bool:
    estado_actual = getattr(reporte.estado, "value", reporte.estado)
    if estado_actual != EstadoReporte.PENDIENTE.value:
        return False

    reporte.estado = EstadoReporte.INVESTIGANDO
    perfil = (
        db.query(PerfilInvestigacion)
        .filter(PerfilInvestigacion.reporte_id == reporte.id)
        .first()
    )
    if not perfil:
        db.add(PerfilInvestigacion(reporte_id=reporte.id))
    return True