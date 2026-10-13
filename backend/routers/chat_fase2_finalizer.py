"""
Endpoint para finalizar Fase 2 y generar informe ÚNICO (cuando tiene 80%+ datos)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from services.completitud_evaluator import (
    EvaluadorCompletitud, 
    GeneradorInformeUnico, 
    NotificadorCompletitud
)
from database import get_db
from middleware.auth_middleware import get_current_user
from services.cron_logger import cron_logger

router = APIRouter(prefix="/api/chat", tags=["Chat - Fase 2"])


@router.post("/{reporte_id}/finalizar-fase2")
async def finalizar_fase_2(
    reporte_id: int,
    datos_vendedor: dict = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Finaliza Fase 2 (Bot honeypot) y genera informe ÚNICO si tiene 80%+ datos.
    
    ANTES: Generaba 2 informes (uno en Fase 1, otro en Fase 2)
    AHORA: Genera 1 solo informe final cuando tiene 80% de datos
    
    Args:
        reporte_id: ID de la publicación/reporte
        datos_vendedor: Dict con datos obtenidos en Fase 2:
            {
                "alias": "mi.alias",
                "cbu": "xxx-xxx-xxx-xxx",
                "nombre_vendedor": "Juan García",
                "ubicacion": "Av. Corrientes 1234",
                "provincia": "Buenos Aires",
                "precio": 1500,
                "metodo_envio": "A domicilio",
                "telefono": "+54 9 11 1234-5678",
                "whatsapp": "+54 9 11 1234-5678",
                "notas": "Vendedor confirmó que es importado"
            }
    """
    
    try:
        # Buscar la publicación
        from models.instagram_data import InstagramData
        from models.tiktok_data import TiktokData
        from models.facebook_data import FacebookData
        from models.mercadolibre_data import MercadoLibreData
        
        pub = db.query(InstagramData).filter(InstagramData.id == reporte_id).first() or \
              db.query(TiktokData).filter(TiktokData.id == reporte_id).first() or \
              db.query(FacebookData).filter(FacebookData.id == reporte_id).first() or \
              db.query(MercadoLibreData).filter(MercadoLibreData.id == reporte_id).first()
        
        if not pub:
            raise HTTPException(status_code=404, detail="Publicación no encontrada")
        
        # Datos de Fase 1 (scraping)
        datos_fase1 = {
            "id": pub.id,
            "vendedor": pub.vendedor,
            "url": getattr(pub, "url", ""),
            "plataforma": pub.red_social if hasattr(pub, "red_social") else "instagram",
            "fecha": pub.fecha_recoleccion,
            "descripcion": pub.descripcion[:200] if pub.descripcion else "",
            "precio": pub.precio,
            "ubicacion": pub.ubicacion if hasattr(pub, "ubicacion") else "",
            "es_falsificacion": pub.es_falsificacion,
            "motivo_falsificacion": pub.motivo_falsificacion,
            "confianza_porcentaje": pub.confianza,
        }
        
        # Datos de Fase 2 (bot honeypot)
        datos_fase2 = datos_vendedor or {}
        
        # EVALUAR COMPLETITUD
        porcentaje, estado, detalles = EvaluadorCompletitud.evaluar_publicacion(datos_fase2)
        
        cron_logger.log(
            f"[Fase 2 - Reporte #{reporte_id}] "
            f"Completitud: {porcentaje}% ({estado.value})"
        )
        
        # GENERAR INFORME ÚNICO (solo si >= 80%)
        informe_final = None
        informe_generado = False
        
        if GeneradorInformeUnico.debe_generar_informe(porcentaje):
            informe_final = await GeneradorInformeUnico.generar_informe_final(
                publicacion=datos_fase1,
                datos_fase2=datos_fase2,
                porcentaje_completitud=porcentaje
            )
            
            if informe_final:
                informe_generado = True
                
                # Guardar informe en BD
                from models.reporte import Reporte
                reporte = db.query(Reporte).filter(Reporte.publicacion_id == reporte_id).first()
                
                if reporte:
                    reporte.datos_fase2 = datos_fase2
                    reporte.porcentaje_completitud = porcentaje
                    reporte.estado_completitud = estado.value
                    reporte.estado = "completado"
                    db.commit()
                
                cron_logger.log(f"[Informe Único] Generado para reporte #{reporte_id}")
        
        # NOTIFICAR ANALISTA
        notificacion = await NotificadorCompletitud.notificar_estado(
            publicacion_id=reporte_id,
            porcentaje_completitud=porcentaje,
            estado=estado
        )
        
        return {
            "success": True,
            "reporte_id": reporte_id,
            "completitud": {
                "porcentaje": porcentaje,
                "estado": estado.value,
                "detalles": detalles,
            },
            "informe_generado": informe_generado,
            "informe_final": informe_final,
            "notificacion": notificacion,
            "datos_faltantes": EvaluadorCompletitud.generar_lista_datos_faltantes(detalles) 
                                if porcentaje < 100 else [],
        }
    
    except Exception as e:
        cron_logger.log(f"[Fase 2 Error] Reporte #{reporte_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error finalizando Fase 2: {str(e)}")


@router.get("/{reporte_id}/completitud")
def obtener_completitud(
    reporte_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Obtiene el estado actual de completitud de una investigación."""
    
    try:
        from models.reporte import Reporte
        
        reporte = db.query(Reporte).filter(Reporte.publicacion_id == reporte_id).first()
        
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        
        porcentaje = getattr(reporte, "porcentaje_completitud", 0)
        estado = getattr(reporte, "estado_completitud", "incompleto")
        datos_fase2 = getattr(reporte, "datos_fase2", {})
        
        # Evaluar datos faltantes
        _, _, detalles = EvaluadorCompletitud.evaluar_publicacion(datos_fase2)
        faltantes = EvaluadorCompletitud.generar_lista_datos_faltantes(detalles)
        
        return {
            "reporte_id": reporte_id,
            "completitud": {
                "porcentaje": porcentaje,
                "estado": estado,
                "puede_generar_informe": porcentaje >= 80,
            },
            "datos_faltantes": faltantes,
            "recomendacion": GeneradorInformeUnico._generar_recomendacion(
                porcentaje, 
                reporte.es_falsificacion if hasattr(reporte, "es_falsificacion") else False
            ),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
