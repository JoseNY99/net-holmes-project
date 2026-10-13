"""
Sistema de generación de informes ÚNICOS con cálculo de completitud de datos.
Antes: 2 informes (Fase 1 + Fase 2)
Ahora: 1 solo informe cuando tiene 80% de datos
"""

from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum


class EstadoCompletitud(Enum):
    """Estados de completitud de datos en investigación"""
    INCOMPLETO = "incompleto"      # < 40%
    PARCIAL = "parcial"            # 40-79%
    SUFICIENTE = "suficiente"      # >= 80%
    COMPLETO = "completo"          # 100%


class EvaluadorCompletitud:
    """Evalúa el porcentaje de datos obtenidos en una investigación."""
    
    # Datos críticos que debe obtener en Fase 2
    DATOS_CRITICOS = {
        "alias_cbu": 25,           # Alias bancario o CBU
        "ubicacion": 20,           # Ubicación del vendedor
        "precio": 15,              # Precio del producto
        "nombre_vendedor": 15,     # Nombre real (si se obtiene)
        "metodo_envio": 10,        # Método de envío mencionado
        "telefono_contacto": 15,   # Teléfono o contacto
    }
    
    @staticmethod
    def evaluar_publicacion(datos_fase2: Dict) -> tuple:
        """
        Evalúa el porcentaje de completitud de datos obtenidos.
        
        Args:
            datos_fase2: Dict con los datos obtenidos en Fase 2
            
        Returns:
            (porcentaje: int, estado: EstadoCompletitud, detalles: Dict)
        """
        detalles = {}
        total_puntos = 0
        puntos_obtenidos = 0
        
        # Evaluar cada dato crítico
        for dato, puntos in EvaluadorCompletitud.DATOS_CRITICOS.items():
            total_puntos += puntos
            
            # Verificar si el dato fue obtenido
            tiene_dato = False
            
            if dato == "alias_cbu":
                tiene_dato = bool(
                    (datos_fase2.get("alias") and datos_fase2["alias"].strip()) or
                    (datos_fase2.get("cbu") and datos_fase2["cbu"].strip())
                )
            elif dato == "ubicacion":
                tiene_dato = bool(
                    (datos_fase2.get("ubicacion") and datos_fase2["ubicacion"].strip()) or
                    (datos_fase2.get("provincia") and datos_fase2["provincia"].strip())
                )
            elif dato == "precio":
                tiene_dato = bool(datos_fase2.get("precio"))
            elif dato == "nombre_vendedor":
                tiene_dato = bool(datos_fase2.get("nombre_vendedor") and datos_fase2["nombre_vendedor"].strip())
            elif dato == "metodo_envio":
                tiene_dato = bool(datos_fase2.get("metodo_envio") and datos_fase2["metodo_envio"].strip())
            elif dato == "telefono_contacto":
                tiene_dato = bool(
                    (datos_fase2.get("telefono") and datos_fase2["telefono"].strip()) or
                    (datos_fase2.get("whatsapp") and datos_fase2["whatsapp"].strip())
                )
            
            if tiene_dato:
                puntos_obtenidos += puntos
            
            detalles[dato] = tiene_dato
        
        # Calcular porcentaje
        porcentaje = int((puntos_obtenidos / total_puntos) * 100) if total_puntos > 0 else 0
        
        # Determinar estado
        if porcentaje < 40:
            estado = EstadoCompletitud.INCOMPLETO
        elif porcentaje < 80:
            estado = EstadoCompletitud.PARCIAL
        elif porcentaje < 100:
            estado = EstadoCompletitud.SUFICIENTE
        else:
            estado = EstadoCompletitud.COMPLETO
        
        return porcentaje, estado, detalles
    
    @staticmethod
    def generar_lista_datos_faltantes(detalles: Dict) -> List[str]:
        """Genera lista de datos que faltan obtener."""
        faltantes = []
        
        etiquetas = {
            "alias_cbu": "Alias bancario o CBU",
            "ubicacion": "Ubicación exacta",
            "precio": "Precio confirmado",
            "nombre_vendedor": "Nombre real del vendedor",
            "metodo_envio": "Método de envío",
            "telefono_contacto": "Teléfono o WhatsApp",
        }
        
        for dato, obtenido in detalles.items():
            if not obtenido:
                faltantes.append(etiquetas.get(dato, dato))
        
        return faltantes


class GeneradorInformeUnico:
    """Genera UN SOLO informe final cuando tiene 80%+ de datos."""
    
    @staticmethod
    def debe_generar_informe(porcentaje_completitud: int) -> bool:
        """
        Determina si se debe generar el informe final.
        
        Args:
            porcentaje_completitud: Porcentaje de datos obtenidos (0-100)
            
        Returns:
            True si porcentaje >= 80
        """
        return porcentaje_completitud >= 80
    
    @staticmethod
    async def generar_informe_final(
        publicacion: Dict,
        datos_fase2: Optional[Dict] = None,
        porcentaje_completitud: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Genera el informe final ÚNICO.
        
        Args:
            publicacion: Datos de la Fase 1 (screenshot, link, descripción)
            datos_fase2: Datos obtenidos del bot honeypot
            porcentaje_completitud: Porcentaje de completitud
            
        Returns:
            Dict con el informe final, o None si no tiene suficientes datos
        """
        
        if datos_fase2 is None:
            datos_fase2 = {}
        
        # Evaluar completitud
        if porcentaje_completitud is None:
            porcentaje_completitud, estado, detalles = EvaluadorCompletitud.evaluar_publicacion(datos_fase2)
        else:
            _, estado, detalles = EvaluadorCompletitud.evaluar_publicacion(datos_fase2)
        
        # Si no tiene 80%+, NO generar informe
        if not GeneradorInformeUnico.debe_generar_informe(porcentaje_completitud):
            return None
        
        # Construir informe ÚNICO final
        faltantes = EvaluadorCompletitud.generar_lista_datos_faltantes(detalles)
        
        informe_final = {
            "id": publicacion.get("id"),
            "fecha_generacion": datetime.now().isoformat(),
            "titulo": f"Informe Final - {publicacion.get('vendedor', 'Desconocido')}",
            "completitud_porcentaje": porcentaje_completitud,
            "estado_completitud": estado.value,
            
            # Datos de Fase 1 (Scraping)
            "fase_1": {
                "url": publicacion.get("url"),
                "plataforma": publicacion.get("plataforma"),
                "fecha_hallazgo": publicacion.get("fecha"),
                "descripcion": publicacion.get("descripcion"),
                "precio_publicado": publicacion.get("precio"),
                "vendedor": publicacion.get("vendedor"),
                "ubicacion_publicada": publicacion.get("ubicacion"),
            },
            
            # Datos de Fase 2 (Bot honeypot)
            "fase_2": {
                "alias_cbu": datos_fase2.get("alias") or datos_fase2.get("cbu"),
                "nombre_vendedor": datos_fase2.get("nombre_vendedor"),
                "ubicacion_confirmada": datos_fase2.get("ubicacion"),
                "provincia_confirmada": datos_fase2.get("provincia"),
                "precio_negociado": datos_fase2.get("precio"),
                "metodo_envio": datos_fase2.get("metodo_envio"),
                "telefono": datos_fase2.get("telefono") or datos_fase2.get("whatsapp"),
                "notas_conversacion": datos_fase2.get("notas"),
            },
            
            # Análisis de falsificación
            "evaluacion_falsificacion": {
                "es_falsificacion": publicacion.get("es_falsificacion", False),
                "motivo": publicacion.get("motivo_falsificacion"),
                "es_argentina": publicacion.get("es_argentina", True),
                "confianza": publicacion.get("confianza_porcentaje", 0),
            },
            
            # Alertas al analista
            "alertas": {
                "datos_faltantes": faltantes if faltantes else ["Todos los datos obtenidos"],
                "requiere_revision_manual": porcentaje_completitud < 100,
            },
            
            # Estado del caso
            "recomendacion": GeneradorInformeUnico._generar_recomendacion(
                porcentaje_completitud, 
                publicacion.get("es_falsificacion")
            ),
        }
        
        return informe_final
    
    @staticmethod
    def _generar_recomendacion(porcentaje: int, es_falsificacion: bool) -> str:
        """Genera recomendación basada en completitud y falsificación."""
        
        if not es_falsificacion:
            return "DESCARTADO: No se detectó falsificación."
        
        if porcentaje >= 95:
            return "PROCEDER CON ACCION LEGAL: Informe completo y verificado."
        elif porcentaje >= 80:
            return "CONTACTAR VENDEDOR: Faltan detalles menores, pero hay suficiente evidencia."
        elif porcentaje >= 60:
            return "INVESTIGACION ADICIONAL: Se necesitan más datos del vendedor."
        else:
            return "INCOMPLETO: Requiere intervención manual del analista."


class NotificadorCompletitud:
    """Notifica al analista sobre el estado de completitud."""
    
    @staticmethod
    async def notificar_estado(
        publicacion_id: int,
        porcentaje_completitud: int,
        estado: EstadoCompletitud
    ) -> Dict:
        """
        Genera notificación para el analista.
        
        Args:
            publicacion_id: ID de la publicación
            porcentaje_completitud: Porcentaje de datos (0-100)
            estado: Estado actual
            
        Returns:
            Dict con la notificación
        """
        
        if porcentaje_completitud >= 80:
            nivel = "success"
            titulo = "Informe Listo"
            mensaje = f"Investigación #{publicacion_id} completada al {porcentaje_completitud}%"
        elif porcentaje_completitud >= 60:
            nivel = "warning"
            titulo = "Fase 2 Parcial"
            mensaje = f"Bot obtuvo {porcentaje_completitud}% de datos. Revisar manualmente datos faltantes."
        else:
            nivel = "error"
            titulo = "Fase 2 Incompleta"
            mensaje = f"Bot no pudo obtener suficientes datos ({porcentaje_completitud}%). Requiere acción manual."
        
        notificacion = {
            "id": publicacion_id,
            "timestamp": datetime.now().isoformat(),
            "nivel": nivel,
            "titulo": titulo,
            "mensaje": mensaje,
            "porcentaje": porcentaje_completitud,
            "estado": estado.value,
        }
        
        return notificacion


# Ejemplos de uso
if __name__ == "__main__":
    import asyncio
    
    # Test 1: Evaluar completitud
    print("Test 1: Evaluar Completitud")
    datos_fase2 = {
        "alias": "mi.alias",
        "ubicacion": "Buenos Aires",
        "precio": 1500,
        "nombre_vendedor": "Juan García",
        "metodo_envio": "A domicilio",
        # falta: telefono_contacto
    }
    
    porcentaje, estado, detalles = EvaluadorCompletitud.evaluar_publicacion(datos_fase2)
    print(f"Completitud: {porcentaje}%")
    print(f"Estado: {estado.value}")
    print(f"Detalles: {detalles}")
    
    # Test 2: Generar informe
    print("\nTest 2: Generar Informe (si >= 80%)")
    
    publicacion = {
        "id": 123,
        "vendedor": "Juan García",
        "url": "https://instagram.com/...",
        "plataforma": "instagram",
        "descripcion": "Nike zapatillas replica",
        "es_falsificacion": True,
    }
    
    async def test_informe():
        if EvaluadorCompletitud.debe_generar_informe(porcentaje_completitud=85):
            print("✓ Se generará informe único final")
        else:
            print("✗ Faltan datos, no se genera informe aún")
    
    # Test 3: Datos faltantes
    print("\nTest 3: Datos Faltantes")
    faltantes = EvaluadorCompletitud.generar_lista_datos_faltantes(detalles)
    print(f"Datos faltantes: {faltantes}")
