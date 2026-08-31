from sqlalchemy.orm import Session
from models.reporte import ReporteBrandDefense
from models.perfil_investigacion import PerfilInvestigacion
from typing import List, Dict, Any
import re

def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def _get_plat(reporte: ReporteBrandDefense, attr: str):
    try:
        val = getattr(reporte, attr, None)
        if isinstance(val, list):
            return val[0] if len(val) > 0 else None
        return val
    except Exception:
        return None

def _extract_bio_links(reporte: ReporteBrandDefense) -> str | None:
    ig = _get_plat(reporte, "instagram_data")
    if ig and getattr(ig, "bio_links", None):
        return ig.bio_links
    tt = _get_plat(reporte, "tiktok_data")
    if tt and getattr(tt, "bio_links", None):
        return tt.bio_links
    return None

GENERIC_USERNAMES_FILTER = {
    "desconocido", "vendedor marketplace", "vendedor mp", "vendedor no identificado",
    "anonimo", "anonymous", "usuario", "user", "admin", "null", "none", "n/a",
    "tienda oficial", "tienda online", "showroom", "calzados", "indumentaria", "ventas"
}

def is_generic_username(username: str) -> bool:
    if not username:
        return True
    u = username.lower().strip().replace("@", "")
    if len(u) < 4:
        return True
    for g in ["vendedor mp", "vendedor marketplace", "desconocido", "no identificado", "anonimo"]:
        if g in u:
            return True
    return u in GENERIC_USERNAMES_FILTER

def analyze_identifiers(db: Session, target_reporte: ReporteBrandDefense, all_reportes: List[ReporteBrandDefense]) -> List[Dict[str, Any]]:
    """
    Dimensión 4: Identificadores Directos
    Busca coincidencias exactas o de alta similitud en identificadores clave:
    - Usernames (Levenshtein y variantes)
    - Teléfonos, CUITs, DNIs
    - Enlaces en biografías
    """
    links_found = []
    
    target_perfil = target_reporte.perfil
    target_username = target_reporte.titular_cuenta.lower().strip()
    
    target_phones = []
    target_cuits = []
    target_dnis = []
    if target_perfil:
        if target_perfil.telefono_privado: target_phones.append(target_perfil.telefono_privado)
        if target_perfil.cuit_cuil_ruc: target_cuits.append(target_perfil.cuit_cuil_ruc)
        if target_perfil.dni_cedula: target_dnis.append(target_perfil.dni_cedula)
    
    # Also grab public phone from reporte
    if target_reporte.telefono_publico:
        target_phones.append(target_reporte.telefono_publico)
        
    for other in all_reportes:
        if other.id == target_reporte.id:
            continue
            
        score = 0.0
        evidencias = []
        subtipo = ""
        
        # 1. Exact or high similarity username (ignoring generic placeholders)
        other_username = other.titular_cuenta.lower().strip()
        if not is_generic_username(target_username) and not is_generic_username(other_username):
            if target_username == other_username:
                score = max(score, 0.95)
                evidencias.append(f"Mismo username exacto: {target_username}")
                subtipo = "username_exacto"
            else:
                # Levenshtein distance
                if len(target_username) > 5 and len(other_username) > 5:
                    dist = _levenshtein_distance(target_username, other_username)
                    max_len = max(len(target_username), len(other_username))
                    sim_ratio = 1 - (dist / max_len)
                    if sim_ratio > 0.88:
                        score = max(score, 0.8)
                        evidencias.append(f"Username muy similar: {target_username} / {other_username}")
                        subtipo = "username_similar"

        # 2. Check private identifiers if available
        other_perfil = other.perfil
        if other_perfil:
            if target_perfil and target_perfil.telefono_privado and other_perfil.telefono_privado:
                if clean_phone(target_perfil.telefono_privado) == clean_phone(other_perfil.telefono_privado):
                    score = 1.0
                    evidencias.append(f"Mismo teléfono privado: {target_perfil.telefono_privado}")
                    subtipo = "mismo_telefono"
            
            if target_perfil and target_perfil.cuit_cuil_ruc and other_perfil.cuit_cuil_ruc:
                if clean_cuit(target_perfil.cuit_cuil_ruc) == clean_cuit(other_perfil.cuit_cuil_ruc):
                    score = 1.0
                    evidencias.append(f"Mismo CUIT/CUIL: {target_perfil.cuit_cuil_ruc}")
                    subtipo = "mismo_cuit"

        # 3. Check public phone matching
        other_phones = []
        if other.telefono_publico: other_phones.append(other.telefono_publico)
        if other_perfil and other_perfil.telefono_privado: other_phones.append(other_perfil.telefono_privado)
        
        for t_phone in target_phones:
            for o_phone in other_phones:
                if clean_phone(t_phone) == clean_phone(o_phone) and len(clean_phone(t_phone)) > 6:
                    score = 1.0
                    evidencias.append(f"Teléfono coincidente: {t_phone}")
                    subtipo = "mismo_telefono"
                    break

        # 4. Check email matching
        if target_perfil and target_perfil.email and other_perfil and other_perfil.email:
            if target_perfil.email.lower().strip() == other_perfil.email.lower().strip():
                score = 1.0
                evidencias.append(f"Email idéntico: {target_perfil.email}")
                subtipo = "mismo_email"
                
        # 5. Check bio links matching (Instagram/TikTok often use Linktree)
        t_bio_links = _extract_bio_links(target_reporte)
        o_bio_links = _extract_bio_links(other)
        
        if t_bio_links and o_bio_links and t_bio_links != "[]" and o_bio_links != "[]":
            if t_bio_links == o_bio_links:
                score = 1.0
                evidencias.append(f"Enlace en bio idéntico: {t_bio_links}")
                subtipo = "mismo_enlace_bio"

        if score >= 0.7:
            links_found.append({
                "reporte_a_id": target_reporte.id,
                "reporte_b_id": other.id,
                "tipo_correlacion": "identificador",
                "subtipo": subtipo,
                "score": score,
                "evidencia": {"detalles": evidencias}
            })
            
    return links_found

def clean_phone(phone: str) -> str:
    if not phone: return ""
    return re.sub(r'\D', '', phone)[-10:] # Last 10 digits to avoid country code issues

def clean_cuit(cuit: str) -> str:
    if not cuit: return ""
    return re.sub(r'\D', '', cuit)
