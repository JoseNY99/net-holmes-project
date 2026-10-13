import time
import random
import requests
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class ChillModeScraper:
    """
    Motor base de extracción ("Chill Mode")
    
    Estrategia General:
    - Volumen Máximo: 50 peticiones exitosas por ejecución/red social.
    - Pausas Humanas: time.sleep(random.randint(15, 45)) entre peticiones.
    """
    def __init__(self, platform_name: str, ingest_url: str = "http://localhost:8000/api/reports_defense/ingest"):
        self.platform_name = platform_name
        self.ingest_url = ingest_url
        self.max_items = 50
        self.collected_items = []
        
    def human_pause(self):
        """Pausa aleatoria para evadir detección antibot."""
        delay = random.randint(15, 45)
        logging.info(f"[{self.platform_name}] Pausa humana: {delay} segundos...")
        time.sleep(delay)
        
    def add_report(self, pais: str, producto: str, marca: str, titular: str, url: str, desc: str = "", precio: float = None):
        """Añade un reporte a la memoria temporal antes de la ingesta."""
        if len(self.collected_items) >= self.max_items:
            logging.warning(f"[{self.platform_name}] Límite máximo de {self.max_items} alcanzado.")
            return False
            
        report = {
            "pais": pais,
            "producto_catalogo": producto,
            "marca_afectada": marca,
            "plataforma": self.platform_name,
            "titular_cuenta": titular,
            "url_evidencia": url,
            "descripcion_post": desc,
            "precio_publico": precio,
            "estado": "Pendiente"
        }
        self.collected_items.append(report)
        return True
        
    def send_to_ingest(self):
        """Envía el lote recolectado a la API principal de Antigravity (Fase 1 Triage)"""
        if not self.collected_items:
            logging.info(f"[{self.platform_name}] No hay items para ingestar.")
            return
            
        logging.info(f"[{self.platform_name}] Enviando {len(self.collected_items)} reportes a {self.ingest_url}...")
        try:
            response = requests.post(self.ingest_url, json=self.collected_items)
            response.raise_for_status()
            logging.info(f"[{self.platform_name}] Ingesta exitosa: {response.json()}")
            self.collected_items = [] # clear after success
        except Exception as e:
            logging.error(f"[{self.platform_name}] Error en ingesta: {str(e)}")
