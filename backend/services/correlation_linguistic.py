from sqlalchemy.orm import Session
from models.reporte import ReporteBrandDefense
from typing import List, Dict, Any
import re
import math
from collections import Counter

# Jergas de venta informal en Argentina — SOLO términos que indican conexión real
# Se eliminaron: "talles", "importadas", "showroom", "sale con envio" (los usa TODO vendedor)
JERGA_ARGENTINA = [
    "g5", "calidad g5", "replica aaa", "triple a", "aaa", "calidad top", "1.1", "1 a 1", 
    "espejo", "calidad espejo", "clon", "clon exacto", "calidad original", "directo de fabrica", 
    "por mayor y menor", "x mayor", "trucho", "calidad premium", "imitacion", "no original", 
    "alternativa", "origen brasil", "origen vietnam", "calidad importada", "la salada", "salada", 
    "directo de taller", "por curva", "bulto cerrado", "precio x mayor", "efvo", "efectivo o transf",
    "contraentrega", "motomensajeria", "punto de encuentro", "zapas", "remera oversize", "buzo frizado"
]

def analyze_linguistic(db: Session, target_reporte: ReporteBrandDefense, all_reportes: List[ReporteBrandDefense]) -> List[Dict[str, Any]]:
    """
    Dimensión 2: Patrones Lingüísticos (Estilometría)
    - TF-IDF ligero local
    - Similitud de jerga/modismos
    - Preparado para Hook de IA (Cerebras/OpenAI)
    """
    links_found = []
    
    target_text = _extract_full_text(target_reporte).lower()
    if not target_text:
        return links_found
        
    target_jerga = _extract_jerga(target_text)
    target_words = _tokenize(target_text)
    
    for other in all_reportes:
        if other.id == target_reporte.id:
            continue
            
        other_text = _extract_full_text(other).lower()
        if not other_text:
            continue
            
        score = 0.0
        evidencias = []
        subtipo = ""
        
        # 1. Similitud de Jerga Argentina compartida (≥3 coincidencias para evitar falsos positivos)
        other_jerga = _extract_jerga(other_text)
        jerga_comun = set(target_jerga).intersection(set(other_jerga))
        
        if len(jerga_comun) >= 4:
            score = max(score, 0.85)
            evidencias.append(f"Jerga fuerte en común ({len(jerga_comun)}): {', '.join(jerga_comun)}")
            subtipo = "jerga_compartida"
        elif len(jerga_comun) >= 3:
            score = max(score, 0.75)
            evidencias.append(f"Jerga en común ({len(jerga_comun)}): {', '.join(jerga_comun)}")
            subtipo = "jerga_compartida"
            # ≤2 coincidencias ya NO generan correlación (demasiado genérico)
            
        # 2. TF-IDF / Cosine Similarity ligero
        other_words = _tokenize(other_text)
        cosine_sim = _calculate_cosine_similarity(target_words, other_words)
        
        if cosine_sim > 0.8:
            score = max(score, 0.85)
            evidencias.append(f"Alta similitud de vocabulario (Cosine: {cosine_sim:.2f})")
            subtipo = "vocabulario_similar"
            
        if score >= 0.7:
            links_found.append({
                "reporte_a_id": target_reporte.id,
                "reporte_b_id": other.id,
                "tipo_correlacion": "linguistico",
                "subtipo": subtipo,
                "score": score,
                "evidencia": {"detalles": evidencias}
            })
            
    return links_found

def analyze_with_ai(text_a: str, text_b: str) -> float:
    """
    HOOK PARA IA FUTURA (Cerebras / OpenAI).
    Compara dos textos para determinar si fueron escritos por la misma persona.
    """
    # TODO: Implement API call to Cerebras / OpenAI when enabled.
    return 0.0

def _get_plat(reporte: ReporteBrandDefense, attr: str):
    try:
        val = getattr(reporte, attr, None)
        if isinstance(val, list):
            return val[0] if len(val) > 0 else None
        return val
    except Exception:
        return None

def _extract_full_text(reporte: ReporteBrandDefense) -> str:
    text = []
    if reporte.producto_catalogo: text.append(reporte.producto_catalogo)
    if reporte.descripcion_post: text.append(reporte.descripcion_post)
    
    # Platform specific texts
    plat = (reporte.plataforma or "").lower()
    if plat == "instagram":
        ig = _get_plat(reporte, "instagram_data")
        if ig:
            if getattr(ig, "caption_full", None): text.append(ig.caption_full)
            if getattr(ig, "hashtags", None): text.append(ig.hashtags)
            if getattr(ig, "bio_text", None): text.append(ig.bio_text)
    elif plat == "facebook":
        fb = _get_plat(reporte, "facebook_data")
        if fb:
            if getattr(fb, "comments_text", None): text.append(fb.comments_text)
            if getattr(fb, "marketplace_category", None): text.append(fb.marketplace_category)
    elif plat == "tiktok":
        tt = _get_plat(reporte, "tiktok_data")
        if tt:
            if getattr(tt, "description_full", None): text.append(tt.description_full)
            if getattr(tt, "hashtags", None): text.append(tt.hashtags)
            if getattr(tt, "bio_text", None): text.append(tt.bio_text)
    elif plat == "mercadolibre":
        ml = _get_plat(reporte, "mercadolibre_data")
        if ml:
            if getattr(ml, "warranty_text", None): text.append(ml.warranty_text)
    
    return " ".join(text)

def _extract_jerga(text: str) -> List[str]:
    found = []
    for j in JERGA_ARGENTINA:
        if j in text:
            found.append(j)
    return found

def _tokenize(text: str) -> List[str]:
    # Basic tokenization, removing short stop words
    words = re.findall(r'\b[a-z]{4,}\b', text)
    return words

def _calculate_cosine_similarity(words_a: List[str], words_b: List[str]) -> float:
    if not words_a or not words_b: return 0.0
    
    counter_a = Counter(words_a)
    counter_b = Counter(words_b)
    
    words = list(set(counter_a.keys()).union(set(counter_b.keys())))
    
    dot_product = sum(counter_a.get(word, 0) * counter_b.get(word, 0) for word in words)
    magnitude_a = math.sqrt(sum(counter_a.get(word, 0)**2 for word in words))
    magnitude_b = math.sqrt(sum(counter_b.get(word, 0)**2 for word in words))
    
    if not magnitude_a or not magnitude_b:
        return 0.0
        
    return dot_product / (magnitude_a * magnitude_b)
