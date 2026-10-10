from sqlalchemy.orm import Session
from models.reporte import ReporteBrandDefense
from typing import List, Dict, Any, Set
import json
import re

def _get_plat(reporte: ReporteBrandDefense, attr: str):
    try:
        val = getattr(reporte, attr, None)
        if isinstance(val, list):
            return val[0] if len(val) > 0 else None
        return val
    except Exception:
        return None

GENERIC_STOP_ACCOUNTS = {
    "instagram", "facebook", "tiktok", "mercadolibre", "whatsapp", "meta", "google",
    "adidas", "nike", "puma", "reebok", "gucci", "zara", "louisvuitton", "jordan",
    "reels", "reel", "post", "video", "feed", "viral", "explore", "fyp", "parati",
    "argentina", "buenosaires", "caba", "cordoba", "rosario", "mendoza", "laplata",
    "showroom", "outlet", "indumentaria", "ropa", "moda", "zapatillas", "calzado",
    "ventas", "mayorista", "minorista", "envios", "contacto", "tienda", "local",
    "desconocido", "anonimo", "usuario", "user", "admin", "null", "none", "vendedor",
    "marketplace", "vendedor_mp", "comunidad", "oficial", "argentina_shoes"
}

def _extract_social_network_entities(reporte: ReporteBrandDefense) -> Set[str]:
    """
    Extrae entidades de interacción social (autores de comentarios, cuentas mencionadas)
    de forma segura desde el reporte y sus tablas de plataforma, excluyendo cuentas genéricas.
    """
    entities = set()
    
    # 1. Chequeo seguro por si existe campo dinámico o atributo comentarios_sospechosos
    raw_comments = getattr(reporte, "comentarios_sospechosos", None)
    if raw_comments:
        try:
            parsed = json.loads(raw_comments) if isinstance(raw_comments, str) else raw_comments
            if isinstance(parsed, list):
                for c in parsed:
                    if isinstance(c, dict) and c.get("author"):
                        entities.add(str(c.get("author")).lower().strip().replace("@", ""))
                    elif isinstance(c, str) and c.strip():
                        entities.add(c.lower().strip().replace("@", ""))
        except Exception:
            pass

    # 2. Extraer desde Facebook comments_text
    fb = _get_plat(reporte, "facebook_data")
    if fb and getattr(fb, "comments_text", None):
        try:
            fb_comments = json.loads(fb.comments_text) if isinstance(fb.comments_text, str) else fb.comments_text
            if isinstance(fb_comments, list):
                for c in fb_comments:
                    if isinstance(c, dict) and c.get("author"):
                        entities.add(str(c.get("author")).lower().strip().replace("@", ""))
                    elif isinstance(c, str):
                        for m in re.findall(r'@([a-zA-Z0-9._]+)', c):
                            entities.add(m.lower().strip())
        except Exception:
            pass

    # 3. Extraer desde Instagram mentioned_accounts y menciones en caption
    ig = _get_plat(reporte, "instagram_data")
    if ig:
        if getattr(ig, "mentioned_accounts", None):
            try:
                ig_mentions = json.loads(ig.mentioned_accounts) if isinstance(ig.mentioned_accounts, str) else ig.mentioned_accounts
                if isinstance(ig_mentions, list):
                    for a in ig_mentions:
                        if a:
                            entities.add(str(a).lower().strip().replace("@", ""))
            except Exception:
                pass
        if getattr(ig, "caption_full", None):
            for m in re.findall(r'@([a-zA-Z0-9._]+)', ig.caption_full):
                entities.add(m.lower().strip())

    # 4. Extraer desde TikTok mentioned_accounts y menciones en description
    tt = _get_plat(reporte, "tiktok_data")
    if tt:
        if getattr(tt, "mentioned_accounts", None):
            try:
                tt_mentions = json.loads(tt.mentioned_accounts) if isinstance(tt.mentioned_accounts, str) else tt.mentioned_accounts
                if isinstance(tt_mentions, list):
                    for a in tt_mentions:
                        if a:
                            entities.add(str(a).lower().strip().replace("@", ""))
            except Exception:
                pass
        if getattr(tt, "description_full", None):
            for m in re.findall(r'@([a-zA-Z0-9._]+)', tt.description_full):
                entities.add(m.lower().strip())

    # Filtrar entidades vacías, demasiado cortas (<= 3) o que pertenezcan a la lista de parada genérica
    clean_entities = set()
    for e in entities:
        if len(e) > 3 and e not in GENERIC_STOP_ACCOUNTS:
            clean_entities.add(e)
            
    return clean_entities

def analyze_social_graph(db: Session, target_reporte: ReporteBrandDefense, all_reportes: List[ReporteBrandDefense]) -> List[Dict[str, Any]]:
    """
    Dimensión 5: Patrones de Red (Grafo Social)
    Busca vínculos basados en interacciones (comentaristas comunes, cuentas mencionadas en común).
    """
    links_found = []
    
    target_users = _extract_social_network_entities(target_reporte)
    if not target_users:
        return links_found
        
    for other in all_reportes:
        if other.id == target_reporte.id:
            continue
            
        other_users = _extract_social_network_entities(other)
        if not other_users:
            continue
            
        common_users = target_users.intersection(other_users)
        if len(common_users) >= 2:
            # Score en escala 0.0-1.0 (float)
            score = min(len(common_users) * 0.20, 0.80)
            links_found.append({
                "reporte_a_id": target_reporte.id,
                "reporte_b_id": other.id,
                "tipo_correlacion": "grafo_social",
                "subtipo": "comentaristas_comunes",
                "score": score,
                "evidencia": {"comunes": list(common_users)}
            })
            
    return links_found
