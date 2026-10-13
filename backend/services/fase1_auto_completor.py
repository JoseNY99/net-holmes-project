"""
Auto-completador de Fase 1: Recolecta datos automáticamente y avanza a Fase 2 (Investigación).
Sin intervención manual del analista.
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from models.reporte import ReporteBrandDefense
from models.perfil_investigacion import PerfilInvestigacion
from services.completitud_evaluator import EvaluadorCompletitud
from services.cron_logger import cron_logger


class Fase1AutoCompletor:
    """Completa automáticamente Fase 1 (Relevamiento) y avanza a Fase 2."""
    
    @staticmethod
    def auto_completar_reporte(
        db: Session,
        reporte_id: int,
        datos_extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Auto-completa Fase 1 e inicia Fase 2 automáticamente.
        
        Args:
            db: Sesión SQLAlchemy
            reporte_id: ID del reporte a auto-completar
            datos_extra: Datos adicionales para completitud (opcional)
        
        Returns:
            Dict con estado de completación y perfil de investigación creado
        """
        
        reporte = db.query(ReporteBrandDefense).filter(
            ReporteBrandDefense.id == reporte_id
        ).first()
        
        if not reporte:
            cron_logger.log(f"❌ [Fase1 Auto] Reporte {reporte_id} no encontrado")
            return {"success": False, "error": "Reporte no encontrado"}
        
        try:
            # 1. Evaluar completitud de datos
            evaluador = EvaluadorCompletitud()
            completitud_info = evaluador.evaluar_publicacion({
                "titulo": reporte.producto_catalogo,
                "descripcion": reporte.descripcion_post or "",
                "ubicacion": reporte.direccion_publica or "",
                "precio": reporte.precio_publico or 0,
                "moneda": reporte.moneda,
                "telefono": reporte.telefono_publico or "",
                "vendedor": reporte.titular_cuenta,
                "url": reporte.url_evidencia,
                "plataforma": reporte.plataforma,
                "seguidores": reporte.seguidores_infractor or 0
            })
            
            completitud_porcentaje = completitud_info.get("completitud_porcentaje", 0)
            estado_completitud = completitud_info.get("estado", "INCOMPLETO")
            
            cron_logger.log(
                f"✅ [Fase1 Auto] Reporte {reporte.referencia_interna} "
                f"→ Completitud: {completitud_porcentaje}% ({estado_completitud})"
            )
            
            # 2. Determinar si avanza a Investigación automáticamente
            # Criterio: Si tiene ≥60% de datos críticos, avanza
            debe_avanzar = completitud_porcentaje >= 60
            
            if debe_avanzar:
                # 3. Crear Perfil de Investigación (Fase 2)
                perfil_existente = db.query(PerfilInvestigacion).filter(
                    PerfilInvestigacion.reporte_id == reporte.id
                ).first()
                
                if not perfil_existente:
                    perfil = PerfilInvestigacion(
                        reporte_id=reporte.id,
                        estado="Investigando",
                        completitud_actual=completitud_porcentaje,
                        metadatos={
                            "auto_completado": True,
                            "fecha_auto_completacion": datetime.now(timezone.utc).isoformat(),
                            "completitud_inicial": completitud_porcentaje,
                            "estado_inicial": estado_completitud
                        }
                    )
                    db.add(perfil)
                    cron_logger.log(
                        f"✅ [Fase1→2] Perfil de Investigación creado automáticamente "
                        f"para {reporte.referencia_interna}"
                    )
                else:
                    perfil_existente.estado = "Investigando"
                    perfil_existente.completitud_actual = completitud_porcentaje
                    cron_logger.log(
                        f"✅ [Fase1→2] Perfil existente actualizado "
                        f"para {reporte.referencia_interna}"
                    )
                    perfil = perfil_existente
                
                # 4. Actualizar estado del reporte
                reporte.estado = "Investigando"
                reporte.updated_at = datetime.now(timezone.utc)
                
                db.commit()
                
                return {
                    "success": True,
                    "accion": "auto_completado",
                    "reporte_id": reporte.id,
                    "referencia": reporte.referencia_interna,
                    "completitud": completitud_porcentaje,
                    "estado": estado_completitud,
                    "perfil_id": perfil.id,
                    "mensaje": f"Fase 1 completada automáticamente ({completitud_porcentaje}%). Avanzando a Investigación."
                }
            else:
                # No tiene suficientes datos, mantener en Pendiente
                cron_logger.log(
                    f"⚠️  [Fase1 Auto] Reporte {reporte.referencia_interna} "
                    f"con completitud {completitud_porcentaje}% (< 60%), mantenido en Pendiente"
                )
                
                return {
                    "success": True,
                    "accion": "pendiente",
                    "reporte_id": reporte.id,
                    "referencia": reporte.referencia_interna,
                    "completitud": completitud_porcentaje,
                    "estado": estado_completitud,
                    "perfil_id": None,
                    "mensaje": f"Datos insuficientes ({completitud_porcentaje}%). Reporte en espera de más información."
                }
        
        except Exception as e:
            cron_logger.log(f"❌ [Fase1 Auto] Error: {str(e)}")
            db.rollback()
            return {
                "success": False,
                "error": str(e),
                "reporte_id": reporte_id
            }
    
    @staticmethod
    def auto_completar_batch(
        db: Session,
        reporte_ids: list,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Auto-completa múltiples reportes en lote.
        
        Args:
            db: Sesión SQLAlchemy
            reporte_ids: Lista de IDs de reportes
            verbose: Mostrar detalles
        
        Returns:
            Resumen de completaciones
        """
        resultados = {
            "total": len(reporte_ids),
            "completados": 0,
            "pendientes": 0,
            "errores": 0,
            "detalles": []
        }
        
        for rid in reporte_ids:
            resultado = Fase1AutoCompletor.auto_completar_reporte(db, rid)
            resultados["detalles"].append(resultado)
            
            if resultado.get("success"):
                if resultado.get("accion") == "auto_completado":
                    resultados["completados"] += 1
                elif resultado.get("accion") == "pendiente":
                    resultados["pendientes"] += 1
            else:
                resultados["errores"] += 1
        
        if verbose:
            cron_logger.log(
                f"✅ [Batch Fase1→2] Completados: {resultados['completados']}, "
                f"Pendientes: {resultados['pendientes']}, Errores: {resultados['errores']}"
            )
        
        return resultados
