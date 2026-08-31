import re
from typing import Dict, List, Any

# Expresiones Regulares para Patrones de OSINT
REGEX_PATTERNS = {
    "DNI": r"\b\d{1,2}\.?\d{3}\.?\d{3}\b",
    "CUIT_CUIL": r"\b(20|23|24|27|30|33|34)-?\d{8}-?\d\b",
    "PATENTE_VIEJA": r"\b[A-Z]{3}\s?\d{3}\b",
    "PATENTE_NUEVA": r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    "CBU_CVU": r"\b\d{22}\b",
    "ALIAS_BANCARIO": r"\b[a-zA-Z0-9]+\.[a-zA-Z0-9]+\.[a-zA-Z0-9]+\b", # Alias tradicional de 3 palabras
    "DIRECCION": r"\b(calle|av|avenida|ruta)\s+[a-zA-Z\s]+(?:[0-9]+)?\b",
    "URL_SOSPECHOSA": r"https?:\/\/(?!www\.facebook\.com|www\.instagram\.com|www\.tiktok\.com|www\.mercadolibre\.com\.ar)[^\s]+",
    "TELEFONO_WPP": r"(?:(?:00)?549?)?0?(11|[2368]\d)\d{8}"
}

def analyze_text(text: str) -> Dict[str, List[str]]:
    """
    Analiza un texto y extrae entidades basadas en heurísticas locales (Regex).
    Retorna un diccionario con las entidades encontradas.
    """
    if not text:
        return {}

    results = {}
    
    for entity_type, pattern in REGEX_PATTERNS.items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        found = [match.group(0).strip() for match in matches]
        # Limpieza y deduplicación
        found = list(set([f.lower() for f in found if len(f) > 3]))
        
        # Filtro especial para Alias (evitar falsos positivos con URLs)
        if entity_type == "ALIAS_BANCARIO":
            found = [f for f in found if not f.startswith("http") and not f.startswith("www")]

        if found:
            results[entity_type] = found

    return results

def extract_correlations(item: Dict[str, Any]) -> str:
    """
    Extrae patrones de correlación de un item (ScanResult dict representation o direct scrape item)
    y los devuelve como string JSON.
    """
    import json
    
    # Construir el texto combinado
    title = item.get("title", item.get("titulo_publicacion", ""))
    desc = item.get("description", item.get("descripcion_completa", ""))
    seller_name = item.get("seller_profile", {}).get("name", item.get("vendedor_nombre", ""))
    raw_data = item.get("raw_data", item.get("datos_raw", ""))
    comments = item.get("comments_audit", [])
    
    combined_text = f"{title} | {desc} | {seller_name} | {raw_data} | {' | '.join(comments)}"
    
    extracted_entities = analyze_text(combined_text)
    
    return json.dumps(extracted_entities)
