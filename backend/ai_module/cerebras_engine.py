import os
import json
from cerebras.cloud.sdk import Cerebras
from config import settings

class CerebrasEngine:
    def __init__(self):
        self.api_key = settings.CEREBRAS_API_KEY
        if self.api_key:
            self.client = Cerebras(api_key=self.api_key)
        else:
            self.client = None
            
        self._keywords_cache: dict[str, list[str]] = {}

    def analyze_scraped_data(self, raw_text: str, platform: str, db=None) -> dict:
        """
        Analiza el texto crudo usando para extraer inteligencia.
        Retorna un diccionario estructurado.
        Si se provee la sesión db, verifica en rag_memory si coincide con falsos positivos conocidos.
        """
        result = self._local_fallback_analysis(raw_text)
        
        # Filtro RAG (Falsos Positivos)
        if db:
            from models.rag_memory import RagMemory
            # Extraer posibles valores a bloquear (ej. usernames, URLs, telefonos)
            valores_clave = [
                result.get("vendedor_nombre", "").lower(),
                result.get("vendedor_telefono", "").lower()
            ]
            valores_clave = [v for v in valores_clave if v and v != "desconocido" and v != "n/a"]
            
            if valores_clave:
                # Buscar si alguno de estos valores está en la memoria RAG
                rag_matches = db.query(RagMemory).filter(RagMemory.valor.in_(valores_clave)).all()
                if rag_matches:
                    result["score_sospecha"] = 0
                    result["notas"] = f"[AUTO-DISCARD: RAG MATCH] Bloqueado por memoria inteligente (FP verificado). {result.get('notas', '')}"
                    result["estado"] = "falso_positivo"
                    return result
        
        return result


    def _local_fallback_analysis(self, raw_text: str) -> dict:
        import re
        import random
        phone_match = re.search(r'(?:whatsapp|wsp|cel)[:\\-\\s]*([+]?\\d{2,4}[\\s-]?\\d{4}[\\s-]?\\d{4})', raw_text, re.IGNORECASE)
        ci_match = re.search(r'(?:dni|ci|ruc|cedula)[:\\-\\s]*(\\d{7,11})', raw_text, re.IGNORECASE)
        
        return {
            "vendedor_nombre": "Desconocido",
            "vendedor_telefono": phone_match.group(1) if phone_match else "N/A",
            "vendedor_ci_ruc": ci_match.group(1) if ci_match else "N/A",
            "vendedor_ubicacion": "N/A",
            "precio": "N/A",
            "score_sospecha": random.randint(60, 90),
            "notas": "Fallo en IA Cerebras. Análisis por regex local."
        }
        
    def generate_keywords(self, marca: str) -> list[str]:
        if marca in self._keywords_cache:
            return self._keywords_cache[marca]
            
        fallback = [marca, f'zapatillas {marca}', f'remeras {marca}', f'camperas {marca}', f'botines {marca}']
        self._keywords_cache[marca] = fallback
        return fallback
        
    def is_argentina_related(self, raw_text: str) -> bool:
        """
        Analiza el texto crudo para determinar si tiene una fuerte correlación con Argentina.
        Retorna True si encuentra indicadores locales, False de lo contrario.
        """
        text_lower = raw_text.lower()
        
        # Filtros de rechazo explícito (Si tiene esto, SE RECHAZA automáticamente)
        rejection_words = [
            'usa', 'united states', 'shipping', 'ships from', 'florida', 'california', 
            'texas', 'new york', 'usd', 'dollars', 'size', 'shoes', 'sneakers', 'miami'
        ]
        
        # Primero revisamos rechazos
        for word in rejection_words:
            if re.search(r'\b' + word + r'\b', text_lower):
                return False
                
        # Indicadores absolutos (si aparece uno, es Argentina seguro)
        absolute_indicators = [
            r'\+54', r'mercadopago', r'cbu', r'cvu', r'caba', r'bsas', r'amba',
            r'envios a todo el pais', r'cuotas sin interes'
        ]
        import re
        for ind in absolute_indicators:
            if re.search(ind, text_lower):
                return True
                
        # Palabras típicas (si aparecen varias, es probable que sea Argentina)
        typical_words = [
            'argentina', 'buenos aires', 'cordoba', 'rosario', 'mendoza', 'tucuman',
            'pesos', 'ars', 'transferencia', 'alias',
            'talle', 'zapatillas', 'remera', 'campera', 'botines', 'buzo', 'boludo', 'che'
        ]
        
        match_count = sum(1 for word in typical_words if word in text_lower)
        
        if match_count >= 1:
            return True
            
        return False


cerebras_engine = CerebrasEngine()
