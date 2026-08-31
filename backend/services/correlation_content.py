from sqlalchemy.orm import Session
from models.reporte import ReporteBrandDefense
from typing import List, Dict, Any
import json

def analyze_content(db: Session, target_reporte: ReporteBrandDefense, all_reportes: List[ReporteBrandDefense]) -> List[Dict[str, Any]]:
    """
    Dimensión 3: Patrones de Contenido
    - Imágenes cruzadas (Hashes perceptuales)
    - Mismo precio exacto y producto
    - Mismos links en biografías
    """
    links_found = []
    
    target_hashes = _extract_image_hashes(target_reporte)
    target_price = target_reporte.precio_publico
    target_product = target_reporte.producto_catalogo.lower()
    
    for other in all_reportes:
        if other.id == target_reporte.id:
            continue
            
        score = 0.0
        evidencias = []
        subtipo = ""
        
        # 1. Image Hashes Match
        other_hashes = _extract_image_hashes(other)
        hash_match = False
        if target_hashes and other_hashes:
            for th in target_hashes:
                if th in other_hashes:
                    hash_match = True
                    break
        
        if hash_match:
            score = max(score, 0.9)
            evidencias.append("Imágenes idénticas encontradas (Hashes coincidentes)")
            subtipo = "imagenes_cruzadas"
            
        # 2. Exact same specific product and exact price ACROSS DIFFERENT platforms
        t_price_num = _extract_number(target_price) if target_price else None
        o_price_num = _extract_number(other.precio_publico) if other.precio_publico else None
        
        if t_price_num is not None and o_price_num is not None and t_price_num == o_price_num and t_price_num > 1000:
            # Solo si el producto no es genéricamente solo el nombre de la marca
            is_generic_brand = len(target_product) < 8 and target_product in ["adidas", "nike", "puma", "reebok", "gucci"]
            if not is_generic_brand and target_product == other.producto_catalogo.lower():
                if (target_reporte.plataforma or "").lower() != (other.plataforma or "").lower():
                    score = max(score, 0.75)
                    evidencias.append(f"Mismo producto específico y precio exacto en plataformas distintas: ${target_price}")
                    if not subtipo: subtipo = "mismo_precio_producto"

        if score >= 0.7:
            links_found.append({
                "reporte_a_id": target_reporte.id,
                "reporte_b_id": other.id,
                "tipo_correlacion": "contenido",
                "subtipo": subtipo,
                "score": score,
                "evidencia": {"detalles": evidencias}
            })
            
    return links_found

def _get_plat(reporte: ReporteBrandDefense, attr: str):
    try:
        val = getattr(reporte, attr, None)
        if isinstance(val, list):
            return val[0] if len(val) > 0 else None
        return val
    except Exception:
        return None

def _extract_image_hashes(reporte: ReporteBrandDefense) -> List[str]:
    hashes = []
    plat = (reporte.plataforma or "").lower()
    if plat == "facebook":
        fb = _get_plat(reporte, "facebook_data")
        if fb and getattr(fb, "image_hashes", None):
            hashes = _safe_json_load(fb.image_hashes)
    elif plat == "instagram":
        ig = _get_plat(reporte, "instagram_data")
        if ig and getattr(ig, "image_hashes", None):
            hashes = _safe_json_load(ig.image_hashes)
    elif plat == "tiktok":
        tt = _get_plat(reporte, "tiktok_data")
        if tt and getattr(tt, "image_hashes", None):
            hashes = _safe_json_load(tt.image_hashes)
    elif plat == "mercadolibre":
        ml = _get_plat(reporte, "mercadolibre_data")
        if ml and getattr(ml, "image_hashes", None):
            hashes = _safe_json_load(ml.image_hashes)
    return hashes if isinstance(hashes, list) else []

def _safe_json_load(data: str) -> List[Any]:
    try:
        return json.loads(data)
    except:
        return []

import re
def _extract_number(val) -> float:
    if val is None: return None
    if isinstance(val, (int, float)): return float(val)
    from decimal import Decimal
    if isinstance(val, Decimal): return float(val)
    
    nums = re.findall(r'\d+', str(val).replace('.', '').replace(',', ''))
    if nums:
        return float(nums[0])
    return None
