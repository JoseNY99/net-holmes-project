"""
Filtro Geográfico Centralizado: Rechaza items de fuera de Argentina.
Se usa en TODOS los scrapers (Playwright, Apify, Google Serper, etc.)
"""

import re
from typing import Dict, Any


class FiltroGeografico:
    """Detecta y rechaza items de países extranjeros."""
    
    # Patrones que indican país extranjero
    PATRONES_EXTRANJEROS = [
        # Nombres de países
        r'\bbrasil\b', r'\bbrazil\b', r'\beeuu\b', r'\bestados unidos\b', r'\bunited states\b',
        r'\bchile\b', r'\buruguay\b', r'\bmexico\b', r'\bespaña\b', r'\bcolombia\b',
        r'\bperu\b', r'\becuador\b', r'\bvenezuela\b', r'\bparaguay\b', r'\bbolivia\b',
        r'\bguatemala\b', r'\bcosta rica\b', r'\bpanama\b', r'\bhonduras\b', r'\bel salvador\b',
        r'\bnicaragua\b', r'\brepublica dominicana\b', r'\bpuerto rico\b',
        
        # Ciudades/regiones extranjeras
        r'\bmiami\b', r'\borlando\b', r'\bflorida\b', r'\bcalifornia\b', r'\btexas\b',
        r'\bnew york\b', r'\blos angeles\b', r'\bnew mexico\b', r'\bsanta fe,?\s*(?:new mexico|nm)\b',
        r'\bmadrid\b', r'\bbarcelona\b', r'\bbogota\b', r'\blima\b',
        r'\bsantiago de chile\b', r'\bmontevideo\b', r'\basuncion\b',
        
        # Códigos de país
        r'\bpy\b',  # Paraguay
        r'\bco\b',  # Colombia
        r'\bmx\b',  # México
        r'\bcl\b',  # Chile
        r'\bpe\b',  # Perú
        r'\busa\b',  # USA (con word boundary)
        
        # Monedas extranjeras
        r'\bgs\b',  # Guaraní Paraguayo
        r'\busd\b', r'\bdollar\b',  # USD
        r'\beuro\b', r'\beur\b',  # EUR
        r'\bclp\b', r'\bcop\b', r'\bpen\b',  # Otras monedas
        
        # Números telefónicos extranjeros
        r'\(\d{4}\)\s+\d{3}[\s-]?\d{3}',  # Formato (0982) 610-944 (Paraguay)
        r'\+595[\s-]?\d{1,2}[\s-]?\d{3,4}[\s-]?\d{3,4}',  # +595-982-XXXX (Paraguay)
        r'\+1[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{4}',  # +1-XXX-XXX-XXXX (USA)
        r'\+\d{2,3}[\s-]?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}',  # Formato internacional genérico
    ]
    
    # Patrones que indican Argentina (WHITELIST)
    PATRONES_ARGENTINA = [
        r'\bargentina\b', r'\bar\b',  # País
        r'\b(?:buenos aires|caba|córdoba|santa fe|mendoza|rosario|la plata|mar del plata|tucumán|bahía blanca|salta|jujuy|misiones|corrientes)\b',  # Provincias
        r'\bards?\b', r'\bpesos?\b', r'\b\$\s*\d+',  # Moneda ARS
        r'(?:\+54|0054|0)[\s-]?(?:11|9|2)[\s-]?\d{4}[\s-]?\d{4}',  # Teléfono Argentina
    ]
    
    @staticmethod
    def es_de_argentina(combined_text: str) -> bool:
        """Verifica si el item parece ser de Argentina."""
        combined_text_lower = combined_text.lower()
        
        # Si menciona Argentina explícitamente, es de Argentina
        if any(re.search(pat, combined_text_lower) for pat in FiltroGeografico.PATRONES_ARGENTINA):
            return True
        
        # Si tiene teléfono Argentina +54, es de Argentina
        if re.search(r'\+54[\s-]?(?:11|9|2)[\s-]?\d{4}[\s-]?\d{4}', combined_text_lower):
            return True
        
        return False
    
    @staticmethod
    def es_extranjero(combined_text: str) -> bool:
        """Verifica si el item parece ser de un país extranjero."""
        combined_text_lower = combined_text.lower()
        
        # Buscar patrones extranjeros
        if any(re.search(pat, combined_text_lower, re.IGNORECASE) for pat in FiltroGeografico.PATRONES_EXTRANJEROS):
            return True
        
        return False
    
    @staticmethod
    def filtrar_item(item: Dict[str, Any]) -> tuple[bool, str]:
        """
        Filtra un item por ubicación geográfica.
        
        Args:
            item: Dict con título, descripción, ubicación, teléfono, etc.
        
        Returns:
            (debe_aceptar: bool, motivo: str)
        """
        title = item.get("title", "").lower()
        desc = item.get("description", "").lower()
        location = str(item.get("location", "")).lower()
        phone = str(item.get("phone", "")).lower() or str(item.get("telefono", "")).lower()
        price_text = str(item.get("price", "")).lower()
        
        combined = f"{title} {desc} {location} {phone} {price_text}"
        
        # 1. Verificar si es extranjero
        if FiltroGeografico.es_extranjero(combined):
            return False, "Ubicación extranjera detectada"
        
        # 2. Verificar si es de Argentina (whitelist)
        if FiltroGeografico.es_de_argentina(combined):
            return True, "OK - Argentina"
        
        # 3. Si no es claramente extranjero ni claramente Argentina, ser leniente
        # (podría ser un seller sin info geográfica clara)
        return True, "OK - Sin información geográfica clara (asumiendo Argentina)"
    
    @staticmethod
    def aplicar_filtro_a_lote(items: list) -> list:
        """Filtra un lote de items rechazando extranjeros."""
        resultado = []
        for item in items:
            debe_aceptar, motivo = FiltroGeografico.filtrar_item(item)
            if debe_aceptar:
                resultado.append(item)
        return resultado
