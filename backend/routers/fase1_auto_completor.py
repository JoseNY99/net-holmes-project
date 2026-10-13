"""
Rutas para auto-completación de Fase 1 e inicio de Fase 2 (Investigación).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from services.fase1_auto_completor import Fase1AutoCompletor
from services.cron_logger import cron_logger

router = APIRouter(prefix="/api/fase1", tags=["Fase 1 Auto-Completación"])


@router.post("/auto-completar/{reporte_id}")
async def auto_completar_reporte(
    reporte_id: int,
    db: Session = Depends(get_db)
):
    """
    Auto-completa un reporte de Fase 1 e inicia Fase 2 automáticamente.
    
    - Si completitud >= 60%, pasa a "Investigando"
    - Si completitud < 60%, permanece en "Pendiente"
    """
    resultado = Fase1AutoCompletor.auto_completar_reporte(db, reporte_id)
    
    if not resultado.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resultado.get("error", "Error en auto-completación")
        )
    
    return {
        "status": "success",
        "data": resultado
    }


@router.post("/auto-completar-batch")
async def auto_completar_batch(
    reporte_ids: list[int],
    db: Session = Depends(get_db)
):
    """
    Auto-completa múltiples reportes en lote e inicia Fase 2 automáticamente.
    
    Body:
    ```json
    {
        "reporte_ids": [1, 2, 3, 4, 5]
    }
    ```
    """
    if not reporte_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lista de reporte_ids vacía"
        )
    
    resultado = Fase1AutoCompletor.auto_completar_batch(
        db, 
        reporte_ids, 
        verbose=True
    )
    
    return {
        "status": "success",
        "resumen": {
            "total": resultado["total"],
            "completados": resultado["completados"],
            "pendientes": resultado["pendientes"],
            "errores": resultado["errores"]
        },
        "data": resultado
    }


@router.post("/auto-completar-todos")
async def auto_completar_todos_pendientes(
    db: Session = Depends(get_db)
):
    """
    Auto-completa TODOS los reportes en estado "Pendiente" (Fase 1).
    Uno a uno, avanzando a Investigación si tienen >=60% de datos.
    """
    from models.reporte import ReporteBrandDefense
    
    reportes_pendientes = db.query(ReporteBrandDefense).filter(
        ReporteBrandDefense.estado == "Pendiente"
    ).all()
    
    if not reportes_pendientes:
        return {
            "status": "info",
            "mensaje": "No hay reportes en Pendiente para auto-completar",
            "total": 0
        }
    
    ids_pendientes = [r.id for r in reportes_pendientes]
    
    cron_logger.log(
        f"🚀 [Fase1→2 AUTO] Iniciando auto-completación de {len(ids_pendientes)} reportes pendientes"
    )
    
    resultado = Fase1AutoCompletor.auto_completar_batch(
        db,
        ids_pendientes,
        verbose=True
    )
    
    return {
        "status": "success",
        "resumen": {
            "total": resultado["total"],
            "completados": resultado["completados"],
            "pendientes": resultado["pendientes"],
            "errores": resultado["errores"],
            "mensaje": f"{resultado['completados']} reportes avanzaron a Investigación automáticamente"
        }
    }
