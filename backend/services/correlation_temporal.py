from sqlalchemy.orm import Session
from models.reporte import ReporteBrandDefense
from typing import List, Dict, Any
from datetime import timedelta
import json

def analyze_temporal(db: Session, target_reporte: ReporteBrandDefense, all_reportes: List[ReporteBrandDefense]) -> List[Dict[str, Any]]:
    """
    Dimensión Temporal: Busca simultaneidad REAL de publicaciones.
    Solo usa post_date de plataforma. NO usa fecha_captura (causa falsos
    positivos masivos cuando el cron ingesta en batch).
    Umbral mínimo: 0.70 (elimina franja_coincidente de 4h que no aporta valor).
    """
    links_found = []
    
    target_date = _extract_post_date(target_reporte)
    if not target_date:
        return links_found
        
    for other in all_reportes:
        if other.id == target_reporte.id:
            continue
            
        other_date = _extract_post_date(other)
        if not other_date:
            continue
            
        # Calculate time difference
        diff = abs((target_date - other_date).total_seconds())
        
        score = 0.0
        evidencias = []
        subtipo = ""
        
        # If posted within 15 minutes of each other
        if diff <= 900:  # 15 mins
            score = 0.85
            evidencias.append(f"Publicaciones simultáneas (diferencia: {diff/60:.1f} mins)")
            subtipo = "simultaneidad_cruzada"
            
        # If posted within 1 hour
        elif diff <= 3600:  # 1 hour
            score = 0.70
            evidencias.append(f"Publicaciones en la misma hora (diferencia: {diff/60:.1f} mins)")
            subtipo = "horario_coincidente"

        # franja_coincidente (4h) ELIMINADA — generaba demasiados falsos positivos

        if score >= 0.70:
            links_found.append({
                "reporte_a_id": target_reporte.id,
                "reporte_b_id": other.id,
                "tipo_correlacion": "temporal",
                "subtipo": subtipo,
                "score": score,
                "evidencia": {"detalles": evidencias}
            })
            
    return links_found

def _extract_post_date(reporte: ReporteBrandDefense):
    """
    Extraer fecha de publicación REAL de la plataforma.
    NO usa fecha_captura como fallback para evitar falsos positivos
    cuando el cron ingesta múltiples items en el mismo minuto.
    """
    try:
        plat = (reporte.plataforma or "").lower()
        if plat == "facebook":
            data = getattr(reporte, "facebook_data", None)
            if isinstance(data, list):
                data = data[0] if data else None
            if data and getattr(data, "post_date", None):
                return data.post_date
        elif plat == "instagram":
            data = getattr(reporte, "instagram_data", None)
            if isinstance(data, list):
                data = data[0] if data else None
            if data and getattr(data, "post_date", None):
                return data.post_date
        elif plat == "tiktok":
            data = getattr(reporte, "tiktok_data", None)
            if isinstance(data, list):
                data = data[0] if data else None
            if data and getattr(data, "post_date", None):
                return data.post_date
        elif plat == "mercadolibre":
            data = getattr(reporte, "mercadolibre_data", None)
            if isinstance(data, list):
                data = data[0] if data else None
            if data and getattr(data, "post_date", None):
                return data.post_date
    except Exception:
        pass
        
    # NO fallback a fecha_captura — retornar None para ignorar este reporte
    return None
